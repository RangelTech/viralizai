"""Postar sozinho (spec 47 §4/§11): mesma mecânica do Posta AI. As contas do TikTok/Instagram do cliente entram pelo
perfil-navegador (sessão cifrada lá; aqui só a chave "viralizai:<id>"), e um laço publica cada post na hora marcada,
com novas tentativas em espera crescente. Sessão derrubada pela rede = conta 'caiu' + aviso para reconectar."""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path

from app import avisos
from app.db import Banco, agora
from app.pn import PN, PNErro

log = logging.getLogger("viralizai.postar")
REDES = {"tiktok": {"nome": "TikTok", "pn": "tiktok", "login": "qr", "limite_legenda": 2000},
         "instagram": {"nome": "Instagram", "pn": "instagram", "login": "senha", "limite_legenda": 2200}}
ESPERA_REENVIO_S = [120, 600, 1800]


def chave_pn(conta_id: int) -> str:
    return f"viralizai:{conta_id}"


def cliente(cfg) -> PN:
    return PN(cfg.pn_url, cfg.pn_token)


def contas_ativas(db: Banco, uid: int) -> list[dict]:
    return db.todos("SELECT id, rede, rotulo, estado, criado FROM contas WHERE usuario=? AND estado!='desconectada' ORDER BY criado", (uid,))


def vista_login(db: Banco, k: dict, r: dict) -> dict:
    passo = r.get("passo") or {}
    if passo.get("tipo") == "conectado":
        db.exec("UPDATE contas SET estado='conectada', atualizado=?, login_id=NULL WHERE id=?", (agora(), k["id"]))
    elif passo.get("tipo") == "erro":
        db.exec("UPDATE contas SET estado='desconectada', atualizado=?, login_id=NULL WHERE id=?", (agora(), k["id"]))
    return {"conta": k["id"], "passo": passo}


def pasta_posts(cfg, uid: int) -> Path:
    p = Path(cfg.dados) / "posts" / str(uid)
    p.mkdir(parents=True, exist_ok=True)
    return p


def agendar(db: Banco, cfg, uid: int, conta: int, arquivo: Path, legenda: str, quando: float, pedido: str | None = None, k: int | None = None,
            capa: Path | None = None, origem: str = "manual") -> int:
    """Copia o vídeo para a pasta de posts (o pedido some em 30 dias; o post agendado não pode perder o arquivo)."""
    from app.fila import espelho
    dest = pasta_posts(cfg, uid) / f"{int(time.time() * 1000)}_{arquivo.name}"
    shutil.copy(espelho(cfg).garantir(arquivo), dest)
    espelho(cfg).guardar(dest)
    capa_dest = None
    if capa and espelho(cfg).garantir(capa).exists():
        capa_dest = dest.with_suffix(".jpg")
        shutil.copy(capa, capa_dest)
        espelho(cfg).guardar(capa_dest)
    lim = REDES.get((db.um("SELECT rede FROM contas WHERE id=?", (conta,)) or {}).get("rede") or "tiktok", REDES["tiktok"])["limite_legenda"]
    cur = db.exec("INSERT INTO posts(usuario,conta,pedido,k,arquivo,capa,legenda,quando,origem,criado) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (uid, conta, pedido, k, str(dest), str(capa_dest) if capa_dest else None, (legenda or "")[:lim], quando, origem, agora()))
    return cur.lastrowid


def publicar_um(db: Banco, cfg, p: dict, pn: PN | None = None) -> None:
    pn = pn or cliente(cfg)
    k = db.um("SELECT * FROM contas WHERE id=?", (p["conta"],))
    if not k or k["estado"] != "conectada":
        db.exec("UPDATE posts SET estado='falhou', erro=? WHERE id=?", ("A conta não está conectada. Conecta de novo e toca em tentar de novo.", p["id"]))
        return
    try:
        from app.fila import espelho
        espelho(cfg).garantir(Path(p["arquivo"]))
        r = pn.publicar(chave_pn(k["id"]), "video", p["legenda"] or "", [p["arquivo"]])
        db.exec("UPDATE posts SET estado='publicado', link=?, publicado=?, erro=NULL WHERE id=?", (r.get("link"), agora(), p["id"]))
        avisos.novo(db, p["usuario"], f"Seu vídeo saiu no {REDES.get(k['rede'], {}).get('nome', k['rede'])} ✓", "/app#/postagens")
        return
    except PNErro as e:
        if e.status == 409:  # a rede derrubou a sessão
            db.exec("UPDATE contas SET estado='caiu', atualizado=? WHERE id=?", (agora(), k["id"]))
            db.exec("UPDATE posts SET estado='falhou', erro=? WHERE id=?", ("A rede pediu pra entrar de novo. Reconecta a conta.", p["id"]))
            avisos.novo(db, p["usuario"], f"O {REDES.get(k['rede'], {}).get('nome', k['rede'])} pediu pra conectar de novo", "/app#/postagens")
            return
        erro = e.mensagem
    except Exception as e:  # noqa: BLE001
        erro = f"falha inesperada ({type(e).__name__})"
    t = p["tentativas"] + 1
    if t <= len(ESPERA_REENVIO_S):
        db.exec("UPDATE posts SET estado='agendado', tentativas=?, proxima=?, erro=? WHERE id=?", (t, agora() + ESPERA_REENVIO_S[t - 1], erro, p["id"]))
    else:
        db.exec("UPDATE posts SET estado='falhou', tentativas=?, erro=? WHERE id=?", (t, erro, p["id"]))
        avisos.novo(db, p["usuario"], "Um post não saiu. Toca pra ver e tentar de novo.", "/app#/postagens")


def rodar_fila(db: Banco, cfg, limite: int = 5, pn: PN | None = None) -> int:
    n = 0
    for p in db.todos("SELECT * FROM posts WHERE estado='agendado' AND quando<=? AND (proxima IS NULL OR proxima<=?) ORDER BY quando LIMIT ?",
                      (agora(), agora(), limite)):
        if db.exec("UPDATE posts SET estado='publicando' WHERE id=? AND estado='agendado'", (p["id"],)).rowcount != 1:
            continue
        publicar_um(db, cfg, p, pn)
        n += 1
    return n


def iniciar(db: Banco, cfg, parar: threading.Event) -> None:
    db.exec("UPDATE posts SET estado='agendado' WHERE estado='publicando'")  # reinício no meio de uma publicação

    def laco():
        while not parar.wait(20):
            try:
                rodar_fila(db, cfg)
            except Exception:  # noqa: BLE001
                log.exception("fila de posts")
    threading.Thread(target=laco, daemon=True, name="fila-posts").start()


def posts_publicos(db: Banco, uid: int) -> list[dict]:
    out = []
    for p in db.todos("""SELECT p.*, c.rede, c.rotulo FROM posts p LEFT JOIN contas c ON c.id=p.conta WHERE p.usuario=? AND p.estado!='cancelado'
                         ORDER BY CASE WHEN p.estado IN ('agendado','publicando') THEN 0 ELSE 1 END, p.quando DESC LIMIT 80""", (uid,)):
        out.append({"id": p["id"], "rede": p["rede"], "conta": p["rotulo"], "estado": p["estado"], "quando": p["quando"], "legenda": (p["legenda"] or "")[:200],
                    "erro": p["erro"], "link": p["link"], "origem": p["origem"], "capa_url": f"/api/posts/{p['id']}/capa.jpg" if p["capa"] else None,
                    "pedido": p["pedido"], "k": p["k"]})
    return out


def legenda_pronta(c: dict) -> str:
    partes = [c.get("legenda") or c.get("titulo") or "", " ".join(c.get("hashtags") or [])]
    return "\n\n".join(x for x in partes if x).strip()


__all__ = ["REDES", "agendar", "rodar_fila", "iniciar", "posts_publicos", "contas_ativas", "vista_login", "chave_pn", "cliente", "legenda_pronta", "json"]
