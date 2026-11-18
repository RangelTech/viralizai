"""Fila do Viralizaí (spec 47 §8): invisível para o usuário, justa e à prova de pedaço com problema.

- Pedido (trabalho) de cortes: análise do vídeo (cache, 1 por vídeo mesmo com 50 pedidos iguais) e depois UMA TAREFA
  DE MONTAGEM POR CORTE, com k = posição do corte no pedido.
- Os workers pegam primeiro as tarefas k=1 de todo mundo, depois as análises novas, depois k=2, k=3...: todo mundo recebe o
  1º corte antes de alguém receber o 3º. Dentro do mesmo k, manda a prioridade do plano e a ordem de chegada.
- Cada corte aparece no pedido assim que fica pronto. Corte que falha tenta de novo 1 vez e, se falhar, só ele fica de
  fora: o pedido nunca cai inteiro por um pedaço.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
import uuid
from pathlib import Path

from app import avisos, planos
from app.config import Config
from app.db import Banco, agora

log = logging.getLogger("viralizai.fila")
K_BASE = 99  # tarefa de fundo: prévia da vitrine (sem marca), depois de todo o resto


class ErroUsuario(Exception):
    """Erro mostrável ao cliente como está."""


def pasta_trabalho(cfg: Config, tid: str) -> Path:
    return Path(cfg.dados) / "trabalhos" / tid


def criar(db: Banco, usuario: int, tipo: str, entrada: dict, prioridade: int = 5, fonte: str | None = None) -> str:
    tid = uuid.uuid4().hex[:16]
    db.exec("INSERT INTO trabalhos(id,usuario,tipo,entrada,criado,prioridade,fonte) VALUES(?,?,?,?,?,?,?)",
            (tid, usuario, tipo, json.dumps(entrada, ensure_ascii=False), agora(), prioridade, fonte))
    return tid


# ---------------------------------------------------------------- escolha do próximo
def _pegar(db: Banco) -> tuple[str, dict] | None:
    with db.tx() as c:
        r = c.execute("SELECT * FROM tarefas WHERE estado='fila' AND k=1 ORDER BY prioridade, criado LIMIT 1").fetchone()
        if r:
            c.execute("UPDATE tarefas SET estado='rodando' WHERE id=?", (r["id"],))
            return "tarefa", dict(r)
        r = c.execute("SELECT * FROM trabalhos WHERE estado='fila' ORDER BY prioridade, criado LIMIT 1").fetchone()
        if r:
            c.execute("UPDATE trabalhos SET estado='rodando', etapa='Começando', progresso=0.02 WHERE id=?", (r["id"],))
            return "trabalho", dict(r)
        # corte 2, 3... de um pedido só depois do 1º dele ficar pronto: o 1º corte de cada um sai com a CPU toda
        # prévia da vitrine (k=99) só depois de TODOS os cortes do cliente: nunca disputa CPU com quem está esperando
        r = c.execute("""SELECT f.* FROM tarefas f WHERE f.estado='fila' AND (
                           f.k=1
                           OR (f.k<99 AND NOT EXISTS (SELECT 1 FROM tarefas p WHERE p.trabalho=f.trabalho AND p.k=1 AND p.estado IN ('fila','rodando')))
                           OR (f.k>=99 AND NOT EXISTS (SELECT 1 FROM tarefas p WHERE p.trabalho=f.trabalho AND p.k<99 AND p.estado IN ('fila','rodando'))))
                         ORDER BY f.k, f.prioridade, f.criado LIMIT 1""").fetchone()
        if r:
            c.execute("UPDATE tarefas SET estado='rodando' WHERE id=?", (r["id"],))
            return "tarefa", dict(r)
    return None


# ---------------------------------------------------------------- resultado do pedido (lido e gravado com trava)
def _mexer_resultado(db: Banco, tid: str, f) -> dict:
    with db.tx() as c:
        r = c.execute("SELECT resultado FROM trabalhos WHERE id=?", (tid,)).fetchone()
        res = json.loads(r["resultado"]) if r and r["resultado"] else {}
        f(res)
        c.execute("UPDATE trabalhos SET resultado=? WHERE id=?", (json.dumps(res, ensure_ascii=False), tid))
    return res


def _fechar_se_acabou(db: Banco, cfg: Config, tid: str) -> None:
    abertas = db.um("SELECT COUNT(*) n FROM tarefas WHERE trabalho=? AND k<? AND estado IN ('fila','rodando')", (tid, K_BASE))["n"]
    if abertas:
        return
    t = db.um("SELECT * FROM trabalhos WHERE id=?", (tid,))
    if not t or t["estado"] in ("pronto", "erro"):
        return
    res = json.loads(t["resultado"] or "{}")
    ok = [c for c in res.get("cortes", []) if c.get("estado") == "pronto"]
    if ok:
        db.exec("UPDATE trabalhos SET estado='pronto', etapa='Pronto', progresso=1, fim=? WHERE id=?", (agora(), tid))
        avisos.pronto(db, cfg, t, len(ok), (res.get("video") or {}).get("titulo") or "")
    else:
        db.exec("UPDATE trabalhos SET estado='erro', etapa='Não deu certo', erro=?, fim=? WHERE id=?",
                ("Não consegui montar os cortes desse vídeo. Esse pedido não conta no seu limite; tente de novo.", agora(), tid))


# ---------------------------------------------------------------- pedidos
def _rodar_trabalho(db: Banco, cfg: Config, t: dict) -> None:
    tid = t["id"]
    entrada = json.loads(t["entrada"])

    def avisar(etapa: str, prog: float) -> None:
        db.exec("UPDATE trabalhos SET etapa=?, progresso=? WHERE id=?", (etapa, round(prog, 3), tid))

    try:
        if t["tipo"] == "cortes":
            _analisar_e_dividir(db, cfg, t, entrada, avisar)
            return
        if t["tipo"] == "vitrine":
            _dividir_vitrine(db, t, entrada)
            return
        pasta = pasta_trabalho(cfg, tid)
        if t["tipo"] == "animacao":
            from app.animacao_v2 import fazer
            res = fazer(entrada, pasta, cfg, avisar)
        elif t["tipo"] == "video_ia":
            from app.video_ia import fazer
            res = fazer(db, t, entrada, pasta, cfg, avisar)
        elif t["tipo"] == "editar":
            from app.editor import fazer
            res = fazer(entrada, pasta, cfg, avisar)
        else:
            raise ErroUsuario("Esse tipo de pedido ainda não está disponível.")
        db.exec("UPDATE trabalhos SET estado='pronto', etapa='Pronto', progresso=1, resultado=?, fim=? WHERE id=?",
                (json.dumps(res, ensure_ascii=False), agora(), tid))
        avisos.pronto(db, cfg, t, len(res.get("cortes") or []), res.get("titulo") or "")
    except Exception as e:  # noqa: BLE001
        from app.motor.fonte import ErroFonte
        mostravel = isinstance(e, (ErroUsuario, ErroFonte))
        if not mostravel:
            log.exception("trabalho %s falhou", tid)
        msg = str(e) if mostravel else "Algo deu errado do nosso lado. Esse pedido não conta no seu limite; tente de novo."
        db.exec("UPDATE trabalhos SET estado='erro', etapa='Não deu certo', erro=?, fim=? WHERE id=?", (msg, agora(), tid))
        if not mostravel:
            db.exec("UPDATE trabalhos SET entrada=json_set(entrada,'$.falha_tecnica',?) WHERE id=?", (str(e)[:500], tid))
        if t["tipo"] == "video_ia":
            from app.video_ia import devolver
            devolver(db, t)


def _analisar_e_dividir(db: Banco, cfg: Config, t: dict, entrada: dict, avisar) -> None:
    from app.motor import analise, juiz
    from app.motor.fonte import contexto
    chave = t["fonte"]
    pf = analise.pasta_fonte(cfg.dados, chave)
    local = Path(entrada["upload"]) if entrada.get("upload") else None
    with analise.trava(chave):  # o mesmo vídeo pedido por 2 pessoas: a 2ª espera e pega do cache
        s = analise.coletar_sinais(entrada.get("url") or "", pf, cfg, avisar, arquivo_local=local)
        if local and not s.get("arquivo_local"):
            s["arquivo_local"] = str(local)
            analise._salvar(pf / "sinais.json", s)
        julgados = analise.julgar(s, pf, entrada.get("objetivo") or "tiktok", int(entrada.get("quantos") or 3), cfg, avisar)
    ctx = s["ctx"]
    db.exec("UPDATE fontes SET titulo=?, canal=?, duracao=?, capa=?, tipo=?, plataforma=?, estado='pronta', analisada=? WHERE chave=?",
            (ctx["titulo"], ctx["canal"], ctx["duracao"], ctx["capa"], julgados[0].get("tipo") if julgados else None, ctx["plataforma"], agora(), chave))
    # "mais cortes": não repete trecho que o cliente já recebeu desse vídeo
    ja = {(round(c["inicio"]), round(c["fim"])) for c in entrada.get("ja_recebidos") or []}
    restantes = [c for c in julgados if (round(c["inicio"]), round(c["fim"])) not in ja]
    escolhidos = juiz.variados(restantes, int(entrada.get("quantos") or 3))
    if not escolhidos:
        raise ErroUsuario("Já te mandei todos os bons momentos desse vídeo. Tenta outro link!")
    publica = db.um("SELECT publica FROM fontes WHERE chave=?", (chave,))["publica"]
    cortes = []
    with db.tx() as c:
        for k, cj in enumerate(escolhidos, 1):
            c.execute("""INSERT OR IGNORE INTO cortes_base(fonte,objetivo,inicio,fim,nota,porque,gancho,titulo,legenda,hashtags,assunto,tipo,tema,publico,criado)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (chave, entrada.get("objetivo") or "tiktok", cj["inicio"], cj["fim"], cj["nota"], cj.get("porque"), cj.get("gancho"), cj.get("titulo"),
                       cj.get("legenda"), json.dumps(cj.get("hashtags") or [], ensure_ascii=False), cj.get("assunto"), cj.get("tipo"),
                       tema_de(ctx), publica, agora()))
            bid = c.execute("SELECT id FROM cortes_base WHERE fonte=? AND inicio=? AND fim=?", (chave, cj["inicio"], cj["fim"])).fetchone()["id"]
            c.execute("INSERT INTO tarefas(trabalho,k,corte_base,dados,prioridade,criado) VALUES(?,?,?,?,?,?)",
                      (t["id"], k, bid, json.dumps({"corte": cj, "livre": True}, ensure_ascii=False), t["prioridade"], agora()))
            c.execute("INSERT INTO tarefas(trabalho,k,corte_base,dados,prioridade,criado) VALUES(?,?,?,?,?,?)",
                      (t["id"], K_BASE, bid, json.dumps({"base": True, "corte": cj}, ensure_ascii=False), 9, agora()))
            cortes.append({"k": k, "estado": "montando", "nota": cj["nota"], "gancho": cj.get("gancho"), "porque": cj.get("porque"),
                           "titulo": cj.get("titulo"), "corte_base": bid, "duracao": round(cj["fim"] - cj["inicio"], 1)})
    res = {"video": {k: ctx.get(k) for k in ("titulo", "canal", "duracao", "url", "plataforma", "capa")}, "cortes": cortes,
           "objetivo": entrada.get("objetivo") or "tiktok", "previa": bool(entrada.get("teste"))}
    db.exec("UPDATE trabalhos SET estado='montando', etapa='Montando seus cortes', progresso=0.6, resultado=? WHERE id=?",
            (json.dumps(res, ensure_ascii=False), t["id"]))


def _dividir_vitrine(db: Banco, t: dict, entrada: dict) -> None:
    b = db.um("SELECT * FROM cortes_base WHERE id=?", (entrada["corte_base"],))
    if not b:
        raise ErroUsuario("Esse corte não está mais disponível.")
    f = db.um("SELECT * FROM fontes WHERE chave=?", (b["fonte"],))
    corte = {k: b[k] for k in ("inicio", "fim", "nota", "porque", "gancho", "titulo", "legenda", "assunto", "tipo")}
    corte["hashtags"] = json.loads(b["hashtags"] or "[]")
    db.exec("INSERT INTO tarefas(trabalho,k,corte_base,dados,prioridade,criado) VALUES(?,?,?,?,?,?)",
            (t["id"], 1, b["id"], json.dumps({"corte": corte, "livre": False}, ensure_ascii=False), t["prioridade"], agora()))
    res = {"video": {"titulo": f["titulo"] if f else "", "canal": f["canal"] if f else "", "url": f["url"] if f else "", "capa": f["capa"] if f else ""},
           "cortes": [{"k": 1, "estado": "montando", "nota": b["nota"], "gancho": b["gancho"], "porque": b["porque"], "titulo": b["titulo"],
                       "corte_base": b["id"], "duracao": round(b["fim"] - b["inicio"], 1)}], "objetivo": b["objetivo"]}
    db.exec("UPDATE trabalhos SET estado='montando', etapa='Montando seu corte', progresso=0.6, resultado=? WHERE id=?",
            (json.dumps(res, ensure_ascii=False), t["id"]))


def tema_de(ctx: dict) -> str:
    txt = (ctx.get("titulo", "") + " " + " ".join(ctx.get("tags", []))).lower()
    for tema, chaves in (("gta", ("gta", "cidade alta", "rp ")), ("futebol", ("futebol", "gol", "neymar", "flamengo", "corinthians")),
                         ("podcast", ("podcast", "flow", "cast", "entrevista")), ("humor", ("kkk", "humor", "pegadinha", "zoeira")),
                         ("games", ("minecraft", "free fire", "fortnite", "valorant", "cs2", "gameplay"))):
        if any(k in txt for k in chaves):
            return tema
    return "outros"


# ---------------------------------------------------------------- montagem
def _rodar_tarefa(db: Banco, cfg: Config, tf: dict) -> None:
    from app.motor import analise, montar
    t = db.um("SELECT * FROM trabalhos WHERE id=?", (tf["trabalho"],))
    dados = json.loads(tf["dados"])
    b = db.um("SELECT * FROM cortes_base WHERE id=?", (tf["corte_base"],))
    if not t or not b:
        db.exec("UPDATE tarefas SET estado='erro' WHERE id=?", (tf["id"],))
        return
    pf = analise.pasta_fonte(cfg.dados, b["fonte"])
    s = analise._ler(pf / "sinais.json") or {}
    try:
        if dados.get("base"):  # prévia sem marca para a vitrine (só fonte pública)
            if b["publico"]:
                feito = montar.base(s, pf, dados["corte"], cfg)
                db.exec("UPDATE cortes_base SET capa=?, previa=? WHERE id=?", (feito["capa"], feito["base"], b["id"]))
            db.exec("UPDATE tarefas SET estado='pronto' WHERE id=?", (tf["id"],))
            return
        entrada = json.loads(t["entrada"])
        livre = dados.get("livre", True)
        var = montar.variacao(f"{t['usuario']}:{b['id']}:{dt.date.today()}", livre)
        feito = montar.personalizado(s, pf, dados["corte"], entrada.get("perfil") or {}, pasta_trabalho(cfg, t["id"]), f"corte{tf['k']}", cfg, var)
        if not livre:
            db.exec("INSERT INTO usos(corte_base,usuario,quando) VALUES(?,?,?)", (b["id"], t["usuario"], agora()))
            db.exec("UPDATE cortes_base SET usos=usos+1 WHERE id=?", (b["id"],))
        c = dados["corte"]

        def por(res):
            for x in res.get("cortes", []):
                if x["k"] == tf["k"]:
                    x.update({"estado": "pronto", **feito, "legenda": c.get("legenda"), "hashtags": c.get("hashtags") or [],
                              "titulo": c.get("titulo"), "gancho": c.get("gancho"), "porque": c.get("porque"), "nota": c.get("nota"),
                              "origem": {"inicio": c["inicio"], "fim": c["fim"]}})
            prontos = sum(1 for x in res.get("cortes", []) if x.get("estado") == "pronto")
            res["prontos"] = prontos
        res = _mexer_resultado(db, t["id"], por)
        total = max(1, len(res.get("cortes", [])))
        db.exec("UPDATE trabalhos SET etapa=?, progresso=? WHERE id=? AND estado='montando'",
                (f"{res['prontos']} de {total} prontos", round(0.6 + 0.4 * res["prontos"] / total, 3), t["id"]))
        db.exec("UPDATE tarefas SET estado='pronto' WHERE id=?", (tf["id"],))
    except Exception as e:  # noqa: BLE001
        log.exception("tarefa %s falhou", tf["id"])
        try:  # o trecho em cache pode ser a causa: a nova tentativa baixa de novo
            montar.invalidar_trecho(pf, dados["corte"]["inicio"], dados["corte"]["fim"])
        except Exception:  # noqa: BLE001
            pass
        if tf["tentativas"] < 1:
            db.exec("UPDATE tarefas SET estado='fila', tentativas=tentativas+1, criado=? WHERE id=?", (agora(), tf["id"]))
            return
        db.exec("UPDATE tarefas SET estado='erro' WHERE id=?", (tf["id"],))
        if not dados.get("base"):
            def falhou(res):
                for x in res.get("cortes", []):
                    if x["k"] == tf["k"]:
                        x.update({"estado": "erro", "erro": "Esse corte não ficou bom, pulei ele."})
            _mexer_resultado(db, t["id"], falhou)
            log.warning("corte %s/%s pulado: %s", t["id"], tf["k"], e)
    finally:
        if not dados.get("base"):
            _fechar_se_acabou(db, cfg, t["id"])


# ---------------------------------------------------------------- laço
def _laco(db: Banco, cfg: Config, parar: threading.Event) -> None:
    while not parar.is_set():
        try:
            x = _pegar(db)
        except Exception:  # noqa: BLE001
            log.exception("fila: pegar falhou")
            parar.wait(2)
            continue
        if not x:
            parar.wait(1.5)
            continue
        tipo, item = x
        if tipo == "tarefa":
            _rodar_tarefa(db, cfg, item)
        else:
            _rodar_trabalho(db, cfg, item)


def iniciar(db: Banco, cfg: Config) -> threading.Event:
    # o que estava rodando quando o serviço caiu volta para a fila
    db.exec("UPDATE trabalhos SET estado='fila', etapa='', progresso=0 WHERE estado='rodando'")
    db.exec("UPDATE tarefas SET estado='fila' WHERE estado='rodando'")
    parar = threading.Event()
    for i in range(max(1, cfg.workers)):
        threading.Thread(target=_laco, args=(db, cfg, parar), name=f"fila-{i}", daemon=True).start()

    def faxina():
        while not parar.wait(3600):
            try:
                limpar_antigos(db, cfg)
            except Exception:  # noqa: BLE001
                log.exception("faxina falhou")
    threading.Thread(target=faxina, name="faxina", daemon=True).start()
    return parar


def limpar_antigos(db: Banco, cfg: Config) -> int:
    """Vídeos do cliente somem depois de N dias (aviso antes); o cache das fontes públicas fica (é a vitrine)."""
    import shutil
    limite = agora() - cfg.guardar_dias * 86400
    n = 0
    for t in db.todos("SELECT id FROM trabalhos WHERE fim IS NOT NULL AND fim<? AND entrada NOT LIKE '%\"apagado\"%'", (limite,)):
        shutil.rmtree(pasta_trabalho(cfg, t["id"]), ignore_errors=True)
        db.exec("UPDATE trabalhos SET entrada=json_set(entrada,'$.apagado',1) WHERE id=?", (t["id"],))
        n += 1
    return n


# ---------------------------------------------------------------- uso do plano
def uso_mes(db: Banco, usuario: int) -> dict:
    inicio = time.time() - 30 * 86400
    cortes = db.um("""SELECT COUNT(*) n FROM tarefas f JOIN trabalhos t ON t.id=f.trabalho
                      WHERE t.usuario=? AND t.criado>? AND f.k<? AND f.estado<>'erro'""", (usuario, inicio, K_BASE))["n"]
    anim = db.um("SELECT COUNT(*) n FROM trabalhos WHERE usuario=? AND tipo='animacao' AND criado>? AND estado<>'erro'", (usuario, inicio))["n"]
    return {"cortes": cortes, "animacoes": anim}


def abertos(db: Banco, usuario: int) -> int:
    return db.um("SELECT COUNT(*) n FROM trabalhos WHERE usuario=? AND estado IN ('fila','rodando','montando')", (usuario,))["n"]


def prioridade_de(u: dict) -> int:
    return planos.limites(planos.plano_ativo(u, agora()))["prioridade"]
