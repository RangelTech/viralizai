"""Viralizaí (spec 47): cortes de live, animação, vídeo com IA e editor num app só. API + páginas no mesmo serviço."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app import admin, auth, avisos, fila, mailer, planos, senha_rotas  # noqa: F401
from produtos_core import acesso
from app.config import Config, carregar
from app.db import Banco, agora

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
ESTATICO = Path(__file__).resolve().parent.parent / "static"
COOKIE = "viralizai_s"
RE_URL = re.compile(r"^https?://[^\s]{6,500}$")
RE_FONTE = re.compile(r"(youtube\.com|youtu\.be|twitch\.tv|kick\.com)", re.I)
COR_PADRAO = "#ff2d95"
MOLDURAS = {"neon": "#ff2d95", "fogo": "#ff6a00", "rosa": "#ff3d6e", "ouro": "#ffc53d", "gelo": "#3dd6ff", "roxo": "#9b5cff"}


def criar_app(cfg: Config | None = None, iniciar_fila: bool = True) -> FastAPI:
    cfg = cfg or carregar()
    Path(cfg.dados).mkdir(parents=True, exist_ok=True)
    db = Banco(os.path.join(cfg.dados, "viralizai.db"))
    admin.preparar(db)
    app = FastAPI(title="Viralizaí", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg, app.state.db = cfg, db
    if cfg.demo_email:  # conta de demonstração: Piloto Automático sempre ativo
        u = auth.usuario_por_email(db, cfg.demo_email.lower())
        db.exec("UPDATE usuarios SET plano='piloto', ativo_ate=?, onboarding=1, moedas=MAX(moedas,10), nome=COALESCE(nome,'Demo'), "
                "estilo=COALESCE(estilo,?) WHERE id=?", (agora() + 3650 * 86400, json.dumps({"redes": ["tiktok"], "arroba": "viralizai", "cor": COR_PADRAO}), u["id"]))
    if iniciar_fila:
        app.state.parar = fila.iniciar(db, cfg)

    # ------------------------------------------------ helpers
    def usuario(request: Request, obrigatorio: bool = True) -> dict | None:
        u = auth.usuario_da_sessao(db, cfg.segredo_sessao, request.cookies.get(COOKIE))
        if not u and obrigatorio:
            raise HTTPException(401, "entre na sua conta")
        return u

    def estilo_de(u: dict) -> dict:
        e = json.loads(u.get("estilo") or "{}") or {}
        e.setdefault("redes", ["tiktok"])
        e.setdefault("arroba", "")
        e.setdefault("cor", COR_PADRAO)
        e.setdefault("moldura", "neon")
        e.setdefault("legenda", True)
        e.setdefault("avisar_whatsapp", True)
        return e

    def perfil_montagem(u: dict) -> dict:
        e = estilo_de(u)
        return {"redes": e["redes"], "arroba": e.get("arroba") or "", "cor": e.get("cor") or COR_PADRAO, "legenda": e.get("legenda", True)}

    def conta_de(u: dict) -> dict:
        plano = planos.plano_ativo(u, agora())
        lim = planos.limites(plano)
        uso = fila.uso_mes(db, u["id"])
        restam_cortes = (1 - int(u.get("teste_usado") or 0)) if plano == "teste" else max(0, lim["cortes_mes"] - uso["cortes"])
        nao_lidos = db.um("SELECT COUNT(*) n FROM avisos WHERE usuario=? AND lido=0", (u["id"],))["n"]
        return {"id": u["id"], "email": u["email"], "nome": u.get("nome") or "", "whatsapp": u.get("whatsapp") or "", "plano": plano,
                "plano_nome": planos.PLANOS.get(plano, {}).get("nome", "Teste grátis"), "ativo_ate": u["ativo_ate"], "moedas": u.get("moedas") or 0,
                "uso": uso, "limites": lim, "restam_cortes": restam_cortes,
                "restam_animacoes": max(0, lim["animacoes_mes"] - uso["animacoes"]), "estilo": estilo_de(u),
                "onboarding": bool(u.get("onboarding")), "teste_usado": bool(u.get("teste_usado")), "avisos": nao_lidos,
                "temas": json.loads(u.get("temas") or "[]"), "google": False}

    def paywall(motivo: str, recurso: str = "cortes") -> HTTPException:
        return HTTPException(402, {"mensagem": motivo, "plano": planos.plano_minimo(recurso)})

    def login(u: dict, extra: dict | None = None) -> JSONResponse:
        token = auth.criar_sessao(db, cfg.segredo_sessao, u["id"])
        resp = JSONResponse({"ok": True, **(extra or {})})
        resp.set_cookie(COOKIE, token, max_age=auth.SESSAO_S, httponly=True, secure=not cfg.dev, samesite="lax", path="/")
        return resp

    def exigir_admin(request: Request):
        chave = request.headers.get("x-admin-key") or ""
        if not cfg.admin_key or not hmac.compare_digest(chave, cfg.admin_key):
            raise HTTPException(401, "chave de admin")

    @app.get("/health")
    def health():
        return {"ok": True, "versao": os.environ.get("GIT_COMMIT", "dev")}

    # ------------------------------------------------ cadastro e login
    def _campos(b: dict) -> tuple[str, str]:
        nome = re.sub(r"\s+", " ", str(b.get("nome") or "")).strip()[:60]
        zap = re.sub(r"\D", "", str(b.get("whatsapp") or ""))[:13]
        return nome, zap

    def _antes_cadastro(b: dict) -> None:
        nome, zap = _campos(b)
        if not nome:
            raise HTTPException(422, "Como você se chama?")
        if not auth.normalizar_email(b.get("email")):
            raise HTTPException(422, "Esse e-mail não parece certo.")
        if not b.get("aceite"):
            raise HTTPException(422, "Pra criar a conta, aceite os termos.")
        if zap and len(zap) < 10:
            raise HTTPException(422, "Confere o WhatsApp com DDD.")

    def _depois_cadastro(u: dict, b: dict, request: Request) -> None:
        nome, zap = _campos(b)
        if zap and len(zap) <= 11:
            zap = "55" + zap
        origem = "fael" if "fael" in (request.headers.get("referer") or "") else (b.get("origem") or "rangel")
        db.exec("UPDATE usuarios SET nome=?, whatsapp=?, origem=COALESCE(origem,?) WHERE id=?", (nome, zap or None, str(origem)[:10], u["id"]))

    # cadastro (com nome, WhatsApp e aceite), senha, entrar por link, esqueci a senha, captcha e limites: módulo comum (spec 57 §5A)
    acesso.registrar(app, db, enviar=lambda para, assunto, texto, html: mailer.enviar(cfg, para, assunto, texto, html),
                     login=login, usuario=usuario, criar_usuario=lambda email: auth.usuario_por_email(db, email),
                     produto="Viralizaí", base_url=cfg.base_url, destino="/app", cor="#ff2d95",
                     demo_email=lambda: cfg.demo_email, demo_senha=lambda: cfg.demo_senha, dev=cfg.dev,
                     antes_cadastro=_antes_cadastro, depois_cadastro=_depois_cadastro, pagina_entrar="/entrar")

    @app.post("/api/sair")
    def sair(request: Request):
        auth.encerrar_sessao(db, cfg.segredo_sessao, request.cookies.get(COOKIE))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ------------------------------------------------ conta, estilo, avisos
    @app.get("/api/conta")
    def conta(request: Request):
        return conta_de(usuario(request))

    @app.post("/api/conta")
    async def conta_salvar(request: Request):
        u = usuario(request)
        b = await request.json()
        if "nome" in b:
            db.exec("UPDATE usuarios SET nome=? WHERE id=?", (str(b["nome"] or "")[:60], u["id"]))
        if "whatsapp" in b:
            z = re.sub(r"\D", "", str(b["whatsapp"] or ""))[:13]
            db.exec("UPDATE usuarios SET whatsapp=? WHERE id=?", (("55" + z if z and len(z) <= 11 else z) or None, u["id"]))
        if "temas" in b and isinstance(b["temas"], list):
            db.exec("UPDATE usuarios SET temas=? WHERE id=?", (json.dumps([str(t)[:20] for t in b["temas"]][:10]), u["id"]))
        if b.get("onboarding"):
            db.exec("UPDATE usuarios SET onboarding=1 WHERE id=?", (u["id"],))
        return conta_de(db.um("SELECT * FROM usuarios WHERE id=?", (u["id"],)))

    @app.post("/api/estilo")
    async def estilo_salvar(request: Request):
        u = usuario(request)
        b = await request.json()
        e = estilo_de(u)
        if "redes" in b:
            redes = [r for r in (b.get("redes") or []) if r in ("tiktok", "instagram", "youtube")]
            if not redes:
                raise HTTPException(422, "Escolha pelo menos uma rede.")
            e["redes"] = redes
        if "arroba" in b:
            e["arroba"] = re.sub(r"[^A-Za-z0-9_.]", "", str(b.get("arroba") or "").strip().lstrip("@"))[:30]
        if "moldura" in b and b["moldura"] in MOLDURAS:
            e["moldura"], e["cor"] = b["moldura"], MOLDURAS[b["moldura"]]
        if "cor" in b and re.fullmatch(r"#[0-9a-fA-F]{6}", str(b.get("cor") or "")):
            e["cor"] = b["cor"]
        for k in ("legenda", "avisar_whatsapp"):
            if k in b:
                e[k] = bool(b[k])
        db.exec("UPDATE usuarios SET estilo=? WHERE id=?", (json.dumps(e, ensure_ascii=False), u["id"]))
        return conta_de(db.um("SELECT * FROM usuarios WHERE id=?", (u["id"],)))

    @app.get("/api/avisos")
    def avisos_lista(request: Request):
        u = usuario(request)
        itens = db.todos("SELECT id, texto, link, lido, quando FROM avisos WHERE usuario=? ORDER BY quando DESC LIMIT 30", (u["id"],))
        db.exec("UPDATE avisos SET lido=1 WHERE usuario=?", (u["id"],))
        return {"avisos": itens}

    @app.get("/api/planos")
    def planos_lista():
        return {"planos": [{"codigo": k, **v, "checkout": cfg.checkouts.get(k) or "", "lancamento_ate": cfg.lancamento_ate} for k, v in planos.PLANOS.items()],
                "adicionais": [{"codigo": k, **v, "checkout": cfg.checkouts.get(k) or ""} for k, v in planos.ADICIONAIS.items()],
                "moedas": [{"codigo": k, **v, "checkout": cfg.checkouts.get(k) or ""} for k, v in planos.PACOTES_MOEDAS.items()]}

    # ------------------------------------------------ cortar
    @app.post("/api/link")
    async def ver_link(request: Request):
        """Ao colar o link: capa + título + duração ("Live do Gaules · 4h02 ✓"), sem baixar nada."""
        usuario(request)
        b = await request.json()
        url = str(b.get("url") or "").strip()
        if not RE_URL.match(url) or not RE_FONTE.search(url):
            raise HTTPException(422, "Cola um link do YouTube, da Twitch ou da Kick.")
        from app.motor import fonte
        chave = fonte.chave_rapida(url)
        f = db.um("SELECT * FROM fontes WHERE chave=?", (chave,)) if chave else None
        if f and f.get("titulo"):
            return {"chave": chave, "titulo": f["titulo"], "canal": f["canal"], "duracao": f["duracao"], "capa": f["capa"], "ao_vivo": False, "pronta": f["estado"] == "pronta"}
        try:
            i = await run_in_threadpool(fonte.info, url, cfg)
        except fonte.ErroFonte as e:
            raise HTTPException(422, str(e))
        ctx = fonte.contexto(i)
        chave = chave or fonte.chave_de_info(i)
        db.exec("""INSERT INTO fontes(chave,url,titulo,canal,duracao,capa,plataforma,criado) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(chave) DO UPDATE SET titulo=excluded.titulo, canal=excluded.canal, duracao=excluded.duracao, capa=excluded.capa""",
                (chave, ctx["url"] or url, ctx["titulo"], ctx["canal"], ctx["duracao"], ctx["capa"], ctx["plataforma"], agora()))
        return {"chave": chave, "titulo": ctx["titulo"], "canal": ctx["canal"], "duracao": ctx["duracao"], "capa": ctx["capa"], "ao_vivo": ctx["ao_vivo"], "pronta": False}

    def checar_cota(u: dict, quantos: int) -> tuple[int, bool]:
        c = conta_de(u)
        if c["plano"] == "teste":
            if c["teste_usado"]:
                raise paywall("Sua prévia grátis já foi usada. Escolha um plano pra cortar à vontade 🔥")
            return 1, True
        if c["restam_cortes"] <= 0:
            raise paywall(f"Você usou seus {c['limites']['cortes_mes']} cortes do mês 🔥 Sobe de plano pra continuar.")
        if fila.abertos(db, u["id"]) >= 3:
            raise HTTPException(429, "Espera um dos seus pedidos terminar pra mandar outro.")
        return max(1, min(quantos, c["restam_cortes"], cfg.max_cortes)), False

    def novo_pedido_cortes(u: dict, chave: str, entrada: dict) -> dict:
        quantos, teste = checar_cota(u, int(entrada.get("quantos") or 3))
        entrada.update({"quantos": quantos, "teste": teste, "perfil": perfil_montagem(u)})
        if entrada.get("objetivo") not in ("tiktok", "viral", "reels"):
            entrada["objetivo"] = "tiktok"
        tid = fila.criar(db, u["id"], "cortes", entrada, fila.prioridade_de(u), chave)
        if teste:
            db.exec("UPDATE usuarios SET teste_usado=1 WHERE id=?", (u["id"],))
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    @app.post("/api/cortes")
    async def cortar(request: Request):
        u = usuario(request)
        b = await request.json()
        url = str(b.get("url") or "").strip()
        if not RE_URL.match(url) or not RE_FONTE.search(url):
            raise HTTPException(422, "Cola um link do YouTube, da Twitch ou da Kick (ou sobe o vídeo).")
        from app.motor import fonte
        chave = fonte.chave_rapida(url)
        if not chave:
            try:
                chave = fonte.chave_de_info(await run_in_threadpool(fonte.info, url, cfg))
            except fonte.ErroFonte as e:
                raise HTTPException(422, str(e))
        db.exec("INSERT OR IGNORE INTO fontes(chave,url,criado) VALUES(?,?,?)", (chave, url, agora()))
        return novo_pedido_cortes(u, chave, {"url": url, "objetivo": b.get("objetivo"), "quantos": b.get("quantos"), "layout": b.get("layout") or "auto"})

    @app.post("/api/cortes/upload")
    async def cortar_upload(request: Request):
        """Vídeo do celular (corpo cru, até 2 GB). Nunca vai para a vitrine."""
        u = usuario(request)
        checar_cota(u, 1)
        nome = request.headers.get("x-arquivo") or "video.mp4"
        ext = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ".mp4"
        if ext not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
            raise HTTPException(422, "Manda um vídeo MP4, MOV ou WEBM.")
        d = Path(cfg.dados) / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha256()
        tmp = d / f"novo_{secrets.token_hex(6)}{ext}"
        total = 0
        with open(tmp, "wb") as f:
            async for parte in request.stream():
                total += len(parte)
                if total > 2 * 1024**3:
                    f.close(); tmp.unlink(missing_ok=True)
                    raise HTTPException(413, "O vídeo passa de 2 GB.")
                h.update(parte)
                f.write(parte)
        if total < 10_000:
            tmp.unlink(missing_ok=True)
            raise HTTPException(422, "O arquivo chegou vazio; tenta de novo.")
        chave = f"up:{u['id']}-{h.hexdigest()[:16]}"
        final = d / f"{chave.replace(':', '_')}{ext}"
        tmp.replace(final)
        db.exec("INSERT OR IGNORE INTO fontes(chave,url,titulo,publica,criado) VALUES(?,?,?,0,?)", (chave, "upload", nome[:120], agora()))
        q = request.query_params
        return novo_pedido_cortes(u, chave, {"upload": str(final), "nome": nome[:120], "objetivo": q.get("objetivo"), "quantos": int(q.get("quantos") or 3)})

    @app.post("/api/pedidos/{tid}/mais")
    async def mais_cortes(tid: str, request: Request):
        """Quero mais cortes dessa live: reaproveita a análise, não repete trecho."""
        u = usuario(request)
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=? AND tipo='cortes'", (tid, u["id"]))
        if not t:
            raise HTTPException(404, "Pedido não encontrado.")
        e = json.loads(t["entrada"])
        ja = []
        for x in db.todos("SELECT resultado FROM trabalhos WHERE usuario=? AND fonte=? AND resultado IS NOT NULL", (u["id"], t["fonte"])):
            ja += [c.get("origem") for c in json.loads(x["resultado"]).get("cortes", []) if c.get("origem")]
        b = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
        return novo_pedido_cortes(u, t["fonte"], {k: e.get(k) for k in ("url", "upload", "objetivo", "layout")} | {"quantos": int(b.get("quantos") or 3), "ja_recebidos": ja})

    # ------------------------------------------------ pedidos e arquivos
    def pedido_publico(t: dict, u: dict | None = None) -> dict:
        res = json.loads(t["resultado"]) if t.get("resultado") else None
        entrada = json.loads(t["entrada"])
        apagado = bool(entrada.get("apagado"))
        base = f"/api/pedidos/{t['id']}/arquivo/"
        if res:
            for c in res.get("cortes", []):
                if c.get("estado") == "pronto" and not apagado:
                    c["url"] = base + c["arquivo"]
                    c["urls"] = {r: base + a for r, a in (c.get("arquivos") or {}).items()}
                    c["capa_url"] = base + c["capa"] if c.get("capa") else None
                c.pop("palavras", None)
                c.pop("variacao", None)
            if res.get("video", {}).get("capa") and not str(res["video"]["capa"]).startswith("http"):
                res["video"]["capa"] = None
            if res.get("arquivo") and not apagado:
                res["url"] = base + res["arquivo"]
        return {"id": t["id"], "tipo": t["tipo"], "estado": t["estado"], "etapa": t["etapa"], "progresso": t["progresso"],
                "entrada": {k: entrada.get(k) for k in ("url", "texto", "nome", "objetivo", "quantos", "teste")},
                "erro": t["erro"], "criado": t["criado"], "fim": t["fim"], "resultado": res, "apagado": apagado,
                "estimativa": estimativa(t)}

    def estimativa(t: dict) -> str:
        if t["estado"] in ("pronto", "erro"):
            return ""
        passou = agora() - t["criado"]
        if t["estado"] == "montando":
            return "quase lá…"
        return "uns 2 minutinhos" if passou < 120 else "mais um pouquinho"

    @app.get("/api/pedidos")
    def pedidos(request: Request, tipo: str = ""):
        u = usuario(request)
        sql, args = "SELECT * FROM trabalhos WHERE usuario=?", [u["id"]]
        if tipo:
            sql += " AND tipo=?"
            args.append(tipo)
        return {"pedidos": [pedido_publico(t, u) for t in db.todos(sql + " ORDER BY criado DESC LIMIT 60", tuple(args))]}

    @app.get("/api/pedidos/{tid}")
    def pedido(tid: str, request: Request):
        u = usuario(request)
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=?", (tid, u["id"]))
        if not t:
            raise HTTPException(404, "Não encontrado.")
        return pedido_publico(t, u)

    @app.delete("/api/pedidos/{tid}")
    def pedido_apagar(tid: str, request: Request):
        import shutil
        u = usuario(request)
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=?", (tid, u["id"]))
        if not t:
            raise HTTPException(404, "Não encontrado.")
        shutil.rmtree(fila.pasta_trabalho(cfg, tid), ignore_errors=True)
        db.exec("DELETE FROM trabalhos WHERE id=?", (tid,))
        return {"ok": True}

    @app.api_route("/api/pedidos/{tid}/arquivo/{nome}", methods=["GET", "HEAD"])
    def arquivo(tid: str, nome: str, request: Request, baixar: int = 0):
        u = usuario(request)
        if not re.fullmatch(r"[\w-]{1,60}\.(mp4|jpg|png|mp3)", nome):
            raise HTTPException(404, "Não encontrado.")
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=?", (tid, u["id"]))
        if not t:
            raise HTTPException(404, "Não encontrado.")
        if baixar and json.loads(t["entrada"]).get("teste") and planos.plano_ativo(u, agora()) == "teste":
            raise paywall("Gostou? Pra baixar e postar, escolha um plano 🔥", "baixar")
        p = fila.pasta_trabalho(cfg, tid) / nome
        if not p.exists():
            raise HTTPException(410, f"Esse arquivo já foi apagado (guardamos por {cfg.guardar_dias} dias).")
        mt = {"mp4": "video/mp4", "jpg": "image/jpeg", "png": "image/png", "mp3": "audio/mpeg"}[nome.rsplit(".", 1)[1]]
        return FileResponse(p, media_type=mt, filename=f"viralizai-{tid[:6]}-{nome}" if baixar else None)

    @app.post("/api/pedidos/{tid}/cortes/{k}/editar")
    async def editar_corte(tid: str, k: int, request: Request):
        """Editor simples: gancho, aparar início/fim, legenda ligada, @ e cor do estilo atual. Refaz a partir do trecho em cache."""
        from app.motor import analise, montar
        u = usuario(request)
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=?", (tid, u["id"]))
        if not t or t["tipo"] not in ("cortes", "vitrine"):
            raise HTTPException(404, "Corte não encontrado.")
        res = json.loads(t["resultado"] or "{}")
        c = next((x for x in res.get("cortes", []) if x["k"] == k and x.get("estado") == "pronto"), None)
        if not c:
            raise HTTPException(404, "Corte não encontrado.")
        b = await request.json()
        base = db.um("SELECT * FROM cortes_base WHERE id=?", (c["corte_base"],))
        pf = analise.pasta_fonte(cfg.dados, base["fonte"])
        s = analise._ler(pf / "sinais.json") or {}
        try:
            a = max(0.0, min(30.0, float(b.get("aparar_inicio") or 0)))
            z = max(0.0, min(30.0, float(b.get("aparar_fim") or 0)))
        except (TypeError, ValueError):
            raise HTTPException(422, "Valores de corte inválidos.")
        ini, fim = c["inicio"] + a, c["fim"] - z
        if fim - ini < 5:
            raise HTTPException(422, "O corte ficaria curto demais (mínimo 5 segundos).")
        corte = {"inicio": base["inicio"], "fim": base["fim"], "gancho": str(b.get("gancho") if b.get("gancho") is not None else c.get("gancho") or "")[:60],
                 "tipo": base["tipo"]}
        var = dict(c.get("variacao") or montar.variacao("", True))
        var["d_ini"], var["d_fim"] = ini - base["inicio"], fim - base["fim"]
        perfil = perfil_montagem(u)
        if "legenda" in b:
            perfil["legenda"] = bool(b["legenda"])
        n = int(time.time()) % 100000
        feito = await run_in_threadpool(montar.personalizado, s, pf, corte, perfil, fila.pasta_trabalho(cfg, tid), f"corte{k}_e{n}", cfg, var)

        def por(r):
            for x in r.get("cortes", []):
                if x["k"] == k:
                    x.update({**feito, "gancho": corte["gancho"].upper(), "editado": True})
        fila._mexer_resultado(db, tid, por)
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    # ------------------------------------------------ vitrine (Prontos pra postar)
    def base_publica(b: dict) -> dict:
        se = lambda x: re.sub("[🀀-🫿☀-➿⭐✅️]", "", x or "").strip()  # telas sem emoji
        return {"id": b["id"], "nota": b["nota"], "gancho": se(b["gancho"]), "titulo": se(b["titulo"]), "porque": se(b["porque"]), "tema": b["tema"],
                "duracao": round(b["fim"] - b["inicio"], 1), "canal": b.get("canal") or "", "usos": b["usos"],
                "capa_url": f"/api/vitrine/{b['id']}/capa.jpg" if b.get("capa") else None,
                "previa_url": f"/api/vitrine/{b['id']}/previa.mp4" if b.get("previa") else None, "criado": b["criado"]}

    def vitrine_sql(tema: str = "", q: str = "", limite: int = 30, ordem: str = "nota") -> list[dict]:
        hoje = agora() - 86400
        sql = f"""SELECT b.*, f.canal FROM cortes_base b JOIN fontes f ON f.chave=b.fonte
                  WHERE b.publico=1 AND b.oculto=0 AND b.previa IS NOT NULL AND f.publica=1
                  AND (SELECT COUNT(*) FROM usos s WHERE s.corte_base=b.id AND s.quando>?) < {planos.LIMITE_USOS_DIA}"""
        args: list = [hoje]
        if tema and tema not in ("alta", "novos"):
            sql += " AND b.tema=?"
            args.append(tema)
        if q:
            sql += " AND (b.titulo LIKE ? OR b.gancho LIKE ? OR f.titulo LIKE ?)"
            args += [f"%{q}%"] * 3
        sql += " ORDER BY " + ("b.criado DESC" if ordem == "novos" else "b.nota DESC, b.criado DESC") + " LIMIT ?"
        args.append(limite)
        return [base_publica(b) for b in db.todos(sql, tuple(args))]

    @app.get("/api/vitrine")
    def vitrine(request: Request, tema: str = "", q: str = ""):
        usuario(request)
        if tema or q:
            return {"itens": vitrine_sql(tema, q[:40], 60, "novos" if tema == "novos" else "nota")}
        temas = [r["tema"] for r in db.todos("SELECT tema, COUNT(*) n FROM cortes_base WHERE publico=1 AND oculto=0 AND previa IS NOT NULL GROUP BY tema ORDER BY n DESC")]
        return {"secoes": [{"tema": "alta", "titulo": "Em alta agora", "itens": vitrine_sql("", "", 12)}] +
                          [{"tema": t, "titulo": NOMES_TEMA.get(t, t.title()), "itens": vitrine_sql(t, "", 12)} for t in temas if t]}

    @app.get("/api/publico/vitrine")
    def vitrine_publica(tema: str = "", limite: int = 6):
        return {"itens": vitrine_sql(tema if tema in NOMES_TEMA else "", "", max(1, min(20, limite)))}

    def exemplos() -> list[dict]:
        f = Path(cfg.dados) / "exemplos" / "exemplos.json"
        try:
            return [e for e in json.loads(f.read_text(encoding="utf-8")) if (Path(cfg.dados) / "exemplos" / e["arquivo"]).exists()]
        except (OSError, ValueError, KeyError):
            return []

    @app.get("/api/publico/exemplos")
    def exemplos_publicos():
        return {"itens": [{"titulo": e.get("titulo"), "formato": e.get("formato"), "tema": e.get("tema"),
                           "url": f"/api/publico/exemplos/{e['arquivo']}", "capa_url": f"/api/publico/exemplos/{e['capa']}" if e.get("capa") else None}
                          for e in exemplos()]}

    @app.get("/api/publico/exemplos/{nome}")
    def exemplo_arquivo(nome: str):
        if not re.fullmatch(r"[\w-]{1,80}\.(mp4|jpg)", nome):
            raise HTTPException(404, "Não encontrado.")
        p = Path(cfg.dados) / "exemplos" / nome
        if not p.is_file():
            raise HTTPException(404, "Não encontrado.")
        return FileResponse(p, media_type="video/mp4" if nome.endswith(".mp4") else "image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/vitrine/{bid}/{nome}")
    def vitrine_arquivo(bid: int, nome: str):
        b = db.um("SELECT b.* FROM cortes_base b JOIN fontes f ON f.chave=b.fonte WHERE b.id=? AND b.publico=1 AND f.publica=1 AND b.oculto=0", (bid,))
        if not b or nome not in ("capa.jpg", "previa.mp4"):
            raise HTTPException(404, "Não encontrado.")
        p = Path(b["capa"] if nome == "capa.jpg" else b["previa"] or "")
        if not p.is_file():
            raise HTTPException(404, "Não encontrado.")
        return FileResponse(p, media_type="image/jpeg" if nome.endswith("jpg") else "video/mp4", headers={"Cache-Control": "public, max-age=3600"})

    @app.post("/api/vitrine/{bid}/usar")
    def vitrine_usar(bid: int, request: Request):
        u = usuario(request)
        if planos.plano_ativo(u, agora()) == "teste":
            raise paywall("Pra usar os cortes prontos com a sua cara, escolha um plano 🔥")
        checar_cota(u, 1)
        b = db.um("SELECT * FROM cortes_base WHERE id=? AND publico=1 AND oculto=0", (bid,))
        if not b:
            raise HTTPException(404, "Esse corte não está mais disponível.")
        if db.um("SELECT COUNT(*) n FROM usos WHERE corte_base=? AND quando>?", (bid, agora() - 86400))["n"] >= planos.LIMITE_USOS_DIA:
            raise HTTPException(409, "Esse corte bombou hoje e esgotou 🔥 Escolhe outro.")
        tid = fila.criar(db, u["id"], "vitrine", {"corte_base": bid, "perfil": perfil_montagem(u)}, fila.prioridade_de(u), b["fonte"])
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    # ------------------------------------------------ animação, vídeo com IA, editor
    @app.post("/api/animacao/roteiro")
    async def animacao_roteiro(request: Request):
        """Mostra o roteiro em cenas ANTES de gerar (sem custo, evita refazer)."""
        from app import animacao_v2
        u = usuario(request)
        b = await request.json()
        ideia = str(b.get("ideia") or "").strip()[:800]
        if len(ideia) < 6:
            raise HTTPException(422, "Conta em uma frase sobre o que é o vídeo.")
        try:
            return await run_in_threadpool(animacao_v2.roteiro, ideia, b.get("formato") or "auto", int(b.get("segundos") or 61), cfg)
        except Exception:  # noqa: BLE001
            raise HTTPException(503, "A IA está ocupada agora. Tenta de novo em 1 minuto.")

    @app.post("/api/animacao")
    async def animacao(request: Request):
        from app import animacao_v2
        u = usuario(request)
        c = conta_de(u)
        if c["limites"]["animacoes_mes"] == 0:
            raise paywall("Criar animação é do plano Corte + Animação ✨", "animacao")
        if c["restam_animacoes"] <= 0:
            raise paywall("Você usou as animações do mês. Sobe de plano pra continuar.", "animacao")
        b = await request.json()
        roteiro = b.get("roteiro")
        if not isinstance(roteiro, dict) or not roteiro.get("cenas"):
            raise HTTPException(422, "Gera o roteiro antes.")
        entrada = {"roteiro": animacao_v2.validar(roteiro), "voz": b.get("voz") or "masculina", "perfil": perfil_montagem(u)}
        tid = fila.criar(db, u["id"], "animacao", entrada, fila.prioridade_de(u))
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    @app.get("/api/animacao/formatos")
    def animacao_formatos():
        from app import animacao_v2
        return {"formatos": animacao_v2.FORMATOS_PUBLICOS, "vozes": animacao_v2.VOZES_PUBLICAS}

    @app.get("/api/video_ia/moldes")
    def video_ia_moldes():
        from app import video_ia
        return {"moldes": video_ia.MOLDES}

    @app.post("/api/video_ia/previa")
    async def video_ia_previa(request: Request):
        from app import video_ia
        u = usuario(request)
        b = await request.json()
        return await run_in_threadpool(video_ia.previa, db, u, str(b.get("pedido") or "")[:500], b.get("molde") or "livre", b.get("ajuste") or "", cfg)

    @app.get("/api/video_ia/previa/{nome}")
    def video_ia_previa_arquivo(nome: str, request: Request):
        u = usuario(request)
        if not re.fullmatch(rf"{u['id']}_[0-9a-f]{{12}}\.(jpg|png)", nome):
            raise HTTPException(404, "Não encontrado.")
        p = Path(cfg.dados) / "previas" / nome
        if not p.exists():
            raise HTTPException(404, "Não encontrado.")
        return FileResponse(p)

    @app.post("/api/video_ia")
    async def video_ia_gerar(request: Request):
        from app import video_ia
        u = usuario(request)
        b = await request.json()
        refazer = str(b.get("refazer") or "")
        tid = video_ia.pedir(db, u, b, refazer, fila.prioridade_de(u), perfil_montagem(u))
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    @app.post("/api/editar")
    async def editar_video(request: Request):
        """Editar meu vídeo: sobe um vídeo (corpo cru) com as opções na query; ou usa um vídeo pronto (?de=pedido&k=1)."""
        from app import editor
        u = usuario(request)
        q = dict(request.query_params)
        if q.get("de"):
            t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=?", (q["de"], u["id"]))
            if not t or t["estado"] != "pronto":
                raise HTTPException(404, "Vídeo não encontrado.")
            arq = editor.arquivo_do_pedido(fila.pasta_trabalho(cfg, t["id"]), json.loads(t["resultado"]), int(q.get("k") or 1))
        else:
            arq = await editor.receber(request, Path(cfg.dados) / "uploads", u["id"])
        entrada = {"arquivo": str(arq), "opcoes": editor.opcoes(q), "perfil": perfil_montagem(u)}
        tid = fila.criar(db, u["id"], "editar", entrada, fila.prioridade_de(u))
        return pedido_publico(db.um("SELECT * FROM trabalhos WHERE id=?", (tid,)), u)

    # ------------------------------------------------ postar sozinho (mesma mecânica do Posta AI, via perfil-navegador)
    from app import cacador, postar
    from app.pn import PNErro

    def erro_pn(e: PNErro):
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.mensagem)

    def pode_postar(u: dict) -> bool:
        return planos.limites(planos.plano_ativo(u, agora()))["postar"]

    @app.get("/api/postagens")
    def postagens(request: Request):
        u = usuario(request)
        return {"pode_postar": pode_postar(u), "contas": postar.contas_ativas(db, u["id"]), "posts": postar.posts_publicos(db, u["id"]),
                "cacador": {**cacador.config(db, u["id"]), "pode": cacador.pode_usar(u), "rodadas": cacador.rodadas(db, u["id"]),
                            "limite_posts_dia": cacador.limite_posts_dia(u) if cacador.pode_usar(u) else 1},
                "redes": {k: {"nome": v["nome"], "login": v["login"]} for k, v in postar.REDES.items()}}

    @app.post("/api/contas")
    async def conectar_conta(request: Request):
        u = usuario(request)
        if not pode_postar(u):
            raise paywall("Postar sozinho é do plano Viral 🚀", "postar")
        b = await request.json()
        rede = b.get("rede")
        if rede not in postar.REDES:
            raise HTTPException(422, "Escolha TikTok ou Instagram.")
        if not b.get("aceite"):
            raise HTTPException(422, "Marque o aceite pra continuar.")
        if len([k for k in postar.contas_ativas(db, u["id"]) if k["rede"] == rede]) >= 3:
            raise HTTPException(409, "Você já tem 3 contas dessa rede conectadas.")
        usuario_rede, senha = str(b.get("usuario") or "").strip()[:120], str(b.get("senha") or "")
        if postar.REDES[rede]["login"] == "senha" and (not usuario_rede or not senha):
            raise HTTPException(422, "Informe usuário e senha.")
        cur = db.exec("INSERT INTO contas(usuario,rede,rotulo,estado,criado,atualizado) VALUES(?,?,?,?,?,?)",
                      (u["id"], rede, usuario_rede or None, "conectando", agora(), agora()))
        k = db.um("SELECT * FROM contas WHERE id=?", (cur.lastrowid,))
        try:
            res = await run_in_threadpool(postar.cliente(cfg).login, postar.REDES[rede]["pn"], postar.chave_pn(k["id"]), usuario_rede, senha)
        except PNErro as e:
            db.exec("UPDATE contas SET estado='desconectada' WHERE id=?", (k["id"],))
            erro_pn(e)
        del senha
        db.exec("UPDATE contas SET login_id=? WHERE id=?", (res["id"], k["id"]))
        return postar.vista_login(db, k, res)

    def minha_conta(u: dict, cid: int) -> dict:
        k = db.um("SELECT * FROM contas WHERE id=? AND usuario=?", (cid, u["id"]))
        if not k:
            raise HTTPException(404, "Conta não encontrada.")
        return k

    @app.get("/api/contas/{cid}/login")
    async def conta_login_status(cid: int, request: Request):
        k = minha_conta(usuario(request), cid)
        if not k["login_id"]:
            return {"conta": cid, "passo": {"tipo": "conectado" if k["estado"] == "conectada" else "erro"}}
        try:
            return postar.vista_login(db, k, await run_in_threadpool(postar.cliente(cfg).login_status, k["login_id"]))
        except PNErro as e:
            erro_pn(e)

    @app.post("/api/contas/{cid}/login")
    async def conta_login_responder(cid: int, request: Request):
        k = minha_conta(usuario(request), cid)
        if not k["login_id"]:
            raise HTTPException(409, "Começa a conexão de novo.")
        valor = str((await request.json()).get("valor") or "")[:200]
        try:
            return postar.vista_login(db, k, await run_in_threadpool(postar.cliente(cfg).responder, k["login_id"], valor))
        except PNErro as e:
            erro_pn(e)

    @app.delete("/api/contas/{cid}")
    async def conta_desconectar(cid: int, request: Request):
        k = minha_conta(usuario(request), cid)
        pn = postar.cliente(cfg)
        try:
            if k["login_id"]:
                await run_in_threadpool(pn.cancelar, k["login_id"])
            await run_in_threadpool(pn.apagar, postar.chave_pn(cid))
        except PNErro:
            pass
        db.exec("UPDATE contas SET estado='desconectada', login_id=NULL WHERE id=?", (cid,))
        db.exec("UPDATE posts SET estado='cancelado' WHERE conta=? AND estado='agendado'", (cid,))
        return {"ok": True}

    @app.post("/api/posts")
    async def novo_post(request: Request):
        """Postar um vídeo pronto (corte, animação, IA, editado) agora ou num horário, numa ou mais contas."""
        u = usuario(request)
        if not pode_postar(u):
            raise paywall("Postar sozinho é do plano Viral 🚀", "postar")
        b = await request.json()
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=? AND estado='pronto'", (str(b.get("pedido") or ""), u["id"]))
        if not t:
            raise HTTPException(404, "Vídeo não encontrado.")
        c = next((x for x in json.loads(t["resultado"]).get("cortes", []) if x.get("k") == int(b.get("k") or 1) and x.get("estado") == "pronto"), None)
        if not c:
            raise HTTPException(404, "Vídeo não encontrado.")
        contas = [minha_conta(u, int(i)) for i in (b.get("contas") or [])]
        contas = [k for k in contas if k["estado"] == "conectada"]
        if not contas:
            raise HTTPException(422, "Escolha pelo menos uma conta conectada.")
        try:
            quando = float(b.get("quando") or 0) or agora()
        except (TypeError, ValueError):
            raise HTTPException(422, "Horário inválido.")
        if quando > agora() + 60 * 86400:
            raise HTTPException(422, "Dá pra agendar até 60 dias pra frente.")
        pasta = fila.pasta_trabalho(cfg, t["id"])
        legenda = str(b.get("legenda") if b.get("legenda") is not None else postar.legenda_pronta(c))
        ids = [postar.agendar(db, cfg, u["id"], k["id"], pasta / c["arquivo"], legenda, max(quando, agora()), t["id"], c["k"],
                              pasta / c["capa"] if c.get("capa") else None) for k in contas]
        return {"ok": True, "posts": ids}

    @app.post("/api/posts/{pid}/{acao}")
    def post_acao(pid: int, acao: str, request: Request):
        u = usuario(request)
        p = db.um("SELECT * FROM posts WHERE id=? AND usuario=?", (pid, u["id"]))
        if not p:
            raise HTTPException(404, "Post não encontrado.")
        if acao == "cancelar" and p["estado"] in ("agendado", "falhou"):
            db.exec("UPDATE posts SET estado='cancelado' WHERE id=?", (pid,))
        elif acao == "tentar" and p["estado"] == "falhou":
            db.exec("UPDATE posts SET estado='agendado', tentativas=0, proxima=NULL, erro=NULL, quando=? WHERE id=?", (agora(), pid))
        else:
            raise HTTPException(409, "Não dá pra fazer isso com esse post agora.")
        return {"ok": True}

    @app.get("/api/posts/{pid}/capa.jpg")
    def post_capa(pid: int, request: Request):
        u = usuario(request)
        p = db.um("SELECT capa FROM posts WHERE id=? AND usuario=?", (pid, u["id"]))
        if not p or not p["capa"] or not Path(p["capa"]).exists():
            raise HTTPException(404, "Sem capa.")
        return FileResponse(p["capa"], media_type="image/jpeg")

    # ------------------------------------------------ Caçador (busca sozinho)
    def pedido_cacador(u: dict, url: str, extras: dict) -> dict:
        from app.motor import fonte
        chave = fonte.chave_rapida(url)
        db.exec("INSERT OR IGNORE INTO fontes(chave,url,criado) VALUES(?,?,?)", (chave, url, agora()))
        return novo_pedido_cortes(u, chave, {"url": url, **extras})

    @app.post("/api/cacador")
    async def cacador_salvar(request: Request):
        u = usuario(request)
        b = await request.json()
        if b.get("ativo") and not cacador.pode_usar(u):
            raise paywall("O Caçador (a IA que busca vídeo sozinha) é do plano Piloto Automático 🎯", "piloto")
        if b.get("postar") and not pode_postar(u):
            raise paywall("Postar sozinho é do plano Viral 🚀", "postar")
        try:
            return cacador.salvar(db, u["id"], b)
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/cacador/rodar")
    async def cacador_rodar(request: Request):
        """Rodar agora (sem esperar o horário): mesma rodada do relógio."""
        u = usuario(request)
        if not cacador.pode_usar(u):
            raise paywall("O Caçador (a IA que busca vídeo sozinha) é do plano Piloto Automático 🎯", "piloto")
        return await run_in_threadpool(cacador.rodar, db, cfg, u["id"], pedido_cacador)

    if iniciar_fila:
        postar.iniciar(db, cfg, app.state.parar)
        cacador.iniciar(db, cfg, app.state.parar, pedido_cacador)

    # ------------------------------------------------ Cakto (planos e moedas)
    @app.post("/api/cakto")
    async def cakto(request: Request):
        cru = await request.body()
        try:
            b = json.loads(cru)
        except ValueError:
            raise HTTPException(400, "json")
        if not cfg.cakto_segredo or not hmac.compare_digest(str(b.get("secret") or ""), cfg.cakto_segredo):
            raise HTTPException(401, "segredo")
        evento = str(b.get("event") or "")
        dados = b.get("data") or {}
        if isinstance(dados, list):
            dados = dados[0] if dados else {}
        eid = str(dados.get("id") or hashlib.sha256(cru).hexdigest()[:24]) + ":" + evento
        if db.um("SELECT 1 FROM eventos_cakto WHERE id=?", (eid,)):
            return {"ok": True, "repetido": True}
        db.exec("INSERT INTO eventos_cakto(id,recebido,corpo) VALUES(?,?,?)", (eid, agora(), cru.decode("utf-8", "replace")[:20000]))
        email = auth.normalizar_email((dados.get("customer") or {}).get("email"))
        if not email:
            return {"ok": True, "ignorado": "sem email"}
        u = auth.usuario_por_email(db, email)
        produto = cfg.planos_por_produto.get(str((dados.get("product") or {}).get("id") or ""), "")
        if evento in ("purchase_approved", "subscription_renewed", "subscription_created"):
            if produto in planos.PACOTES_MOEDAS:
                n = planos.PACOTES_MOEDAS[produto]["moedas"]
                db.exec("UPDATE usuarios SET moedas=moedas+? WHERE id=?", (n, u["id"]))
                db.exec("INSERT INTO moedas_mov(usuario,delta,motivo,ref,quando) VALUES(?,?,?,?,?)", (u["id"], n, "compra", str(dados.get("id") or ""), agora()))
                avisos.novo(db, u["id"], f"Chegaram {n} moedas 🪙 Bora criar vídeo com IA!", "/app#/criar/ia")
                return {"ok": True, "moedas": n}
            if produto in planos.ADICIONAIS:
                ad = json.loads(u.get("adicionais") or "{}")
                ad[produto] = max(agora(), float(ad.get(produto) or 0)) + 32 * 86400
                db.exec("UPDATE usuarios SET adicionais=? WHERE id=?", (json.dumps(ad), u["id"]))
                return {"ok": True, "adicional": produto}
            plano = produto if produto in planos.PLANOS else "corte"
            base = max(agora(), u["ativo_ate"])
            db.exec("UPDATE usuarios SET plano=?, ativo_ate=?, pedido=? WHERE id=?", (plano, base + 32 * 86400, str(dados.get("id") or ""), u["id"]))
            avisos.novo(db, u["id"], f"Plano {planos.PLANOS[plano]['nome']} liberado 🔥", "/app")
            return {"ok": True, "liberado": email, "plano": plano}
        if evento in ("refund", "chargeback", "subscription_canceled", "subscription_cancelled"):
            if produto in planos.PACOTES_MOEDAS:
                return {"ok": True, "ignorado": "estorno de moedas tratado à mão"}
            db.exec("UPDATE usuarios SET ativo_ate=? WHERE id=?", (agora(), u["id"]))
            return {"ok": True, "revogado": email}
        return {"ok": True, "ignorado": evento}

    # ------------------------------------------------ admin
    @app.post("/api/admin/cortesia")
    async def admin_cortesia(request: Request):
        exigir_admin(request)
        b = await request.json()
        email = auth.normalizar_email(b.get("email"))
        if not email:
            raise HTTPException(422, "e-mail inválido")
        plano = b.get("plano") if b.get("plano") in planos.PLANOS else "viral"
        dias = max(0, min(400, int(32 if b.get("dias") is None else b.get("dias"))))
        u = auth.usuario_por_email(db, email)
        db.exec("UPDATE usuarios SET plano=?, ativo_ate=MAX(ativo_ate, ?), moedas=moedas+? WHERE id=?",
                (plano, agora() + dias * 86400, int(b.get("moedas") or 0), u["id"]))
        return {"ok": True, "email": email, "plano": plano}

    @app.get("/api/admin/resumo")
    def admin_resumo(request: Request):
        exigir_admin(request)
        ativos = db.todos("SELECT plano, COUNT(*) n FROM usuarios WHERE ativo_ate>? GROUP BY plano", (agora(),))
        receita = sum(r["n"] * planos.PLANOS.get(r["plano"], {"preco": 0})["preco"] for r in ativos)
        mes = agora() - 30 * 86400
        return {"produto": "viralizai", "nome": "Viralizaí", "url": cfg.base_url, "assinantes": sum(r["n"] for r in ativos),
                "por_plano": {r["plano"]: r["n"] for r in ativos}, "receita_mensal": round(receita, 2),
                "cadastros": db.um("SELECT COUNT(*) n FROM usuarios")["n"],
                "pedidos_30d": db.um("SELECT COUNT(*) n FROM trabalhos WHERE criado>?", (mes,))["n"],
                "erros_30d": db.um("SELECT COUNT(*) n FROM trabalhos WHERE criado>? AND estado='erro'", (mes,))["n"],
                "na_fila": db.um("SELECT COUNT(*) n FROM trabalhos WHERE estado IN ('fila','rodando','montando')")["n"],
                "tarefas_fila": db.um("SELECT COUNT(*) n FROM tarefas WHERE estado IN ('fila','rodando')")["n"],
                "fontes": db.um("SELECT COUNT(*) n FROM fontes WHERE estado='pronta'")["n"],
                "vitrine": db.um("SELECT COUNT(*) n FROM cortes_base WHERE publico=1 AND oculto=0 AND previa IS NOT NULL")["n"]}

    @app.get("/api/admin/assinantes")
    def admin_assinantes(request: Request):
        exigir_admin(request)
        mes = agora() - 30 * 86400
        linhas = db.todos("""SELECT u.id, u.email, u.nome, u.criado, u.plano, u.ativo_ate, u.moedas, u.origem,
                                    (SELECT COUNT(*) FROM trabalhos t WHERE t.usuario=u.id AND t.criado>?) pedidos_30d
                             FROM usuarios u ORDER BY u.ativo_ate DESC, u.criado DESC LIMIT 1000""", (mes,))
        for l in linhas:
            l["ativo"] = l["ativo_ate"] > agora()
        return {"assinantes": linhas}

    @app.post("/api/admin/vitrine/{bid}")
    async def admin_vitrine(bid: int, request: Request):
        exigir_admin(request)
        b = await request.json()
        db.exec("UPDATE cortes_base SET oculto=? WHERE id=?", (1 if b.get("oculto") else 0, bid))
        return {"ok": True}

    app.include_router(admin.rotas(db, cfg.segredo_sessao, """SELECT email, nome, criado, plano, ativo_ate, moedas, (ativo_ate > strftime('%s','now')) ativo
        FROM usuarios ORDER BY criado DESC""", seguro=not cfg.dev))

    # ------------------------------------------------ páginas
    def eh_fael(request: Request) -> bool:
        return "fael" in (request.headers.get("host") or "").lower() or request.query_params.get("fael") == "1"

    @app.get("/", response_class=HTMLResponse)
    def inicio(request: Request):
        return FileResponse(ESTATICO / ("fael.html" if eh_fael(request) else "index.html"))

    @app.get("/entrar", response_class=HTMLResponse)
    def entrar_pagina():
        return FileResponse(ESTATICO / "app.html")

    @app.get("/app", response_class=HTMLResponse)
    def app_pagina():
        return FileResponse(ESTATICO / "app.html", headers={"Cache-Control": "no-cache"})

    @app.get("/termos", response_class=HTMLResponse)
    def termos():
        return FileResponse(ESTATICO / "termos.html")

    @app.get("/admin", response_class=HTMLResponse)
    def pagina_admin():
        return FileResponse(ESTATICO / "admin.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(ESTATICO / "icone" / "favicon.ico", headers={"Cache-Control": "public, max-age=604800"})

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    def icone_apple():
        return FileResponse(ESTATICO / "icone" / "apple-touch-icon.png", headers={"Cache-Control": "public, max-age=604800"})

    from fastapi.staticfiles import StaticFiles
    app.mount("/s", StaticFiles(directory=ESTATICO), name="estatico")
    return app


NOMES_TEMA = {"gta": "GTA", "futebol": "Futebol", "podcast": "Podcasts", "humor": "Humor", "games": "Games", "outros": "Variados"}

app = criar_app() if os.environ.get("VIRALIZAI_SEM_APP") != "1" and os.environ.get("CORTAI_SEM_APP") != "1" else None
