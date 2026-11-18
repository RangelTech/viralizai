"""Caçador (busca sozinho) e Piloto Automático (spec 47 §11): todo dia, no horário que o cliente escolheu, a IA busca no
YouTube os vídeos mais vistos da semana sobre os temas dele, corta os melhores (pedido normal, entra na fila justa) e,
com "postar sozinho" ligado, agenda 1 corte por dia em cada rede conectada. Nunca repete vídeo nem corte."""
from __future__ import annotations

import datetime as dt
import json
import re
import logging
import threading
import urllib.parse

from app import avisos, planos
from app.db import Banco, agora

log = logging.getLogger("viralizai.cacador")
BRT = dt.timezone(dt.timedelta(hours=-3))
FILTRO_SEMANA = "EgQIAxAB"  # YouTube: enviados nesta semana, só vídeo


def pode_usar(u: dict) -> bool:
    if planos.plano_ativo(u, agora()) == "piloto":
        return True
    ad = json.loads(u.get("adicionais") or "{}")
    return float(ad.get("cacador") or 0) > agora()


def limite_posts_dia(u: dict) -> int:
    """Posts por dia em cada rede: Piloto Automático até 5; adicional Caçador até 2."""
    return 5 if planos.plano_ativo(u, agora()) == "piloto" else 2


def config(db: Banco, uid: int) -> dict:
    c = db.um("SELECT * FROM cacador WHERE usuario=?", (uid,))
    if not c:
        return {"ativo": False, "temas": [], "hora": "09:00", "videos_dia": 1, "cortes_video": 3, "objetivo": "tiktok", "postar": False, "hora_post": "19:00",
                "posts_dia": 1, "ultimo_dia": None}
    c["temas"] = json.loads(c["temas"])
    c["ativo"], c["postar"] = bool(c["ativo"]), bool(c["postar"])
    return c


def salvar(db: Banco, uid: int, b: dict) -> dict:
    atual = config(db, uid)
    u = db.um("SELECT * FROM usuarios WHERE id=?", (uid,)) or {}
    posts_dia = max(1, min(limite_posts_dia(u), int(b.get("posts_dia") or atual.get("posts_dia") or 1)))
    temas = [str(t).strip()[:40] for t in (b.get("temas") if b.get("temas") is not None else atual["temas"]) if str(t).strip()][:6]
    hora = str(b.get("hora") or atual["hora"])[:5]
    hora_post = str(b.get("hora_post") or atual["hora_post"])[:5]
    for h in (hora, hora_post):
        try:
            dt.datetime.strptime(h, "%H:%M")
        except ValueError:
            raise ValueError("Horário inválido (use 09:00).")
    db.exec("""INSERT INTO cacador(usuario,ativo,temas,hora,videos_dia,cortes_video,objetivo,postar,hora_post,atualizado,posts_dia) VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(usuario) DO UPDATE SET ativo=excluded.ativo, temas=excluded.temas, hora=excluded.hora, videos_dia=excluded.videos_dia,
               cortes_video=excluded.cortes_video, objetivo=excluded.objetivo, postar=excluded.postar, hora_post=excluded.hora_post,
               atualizado=excluded.atualizado, posts_dia=excluded.posts_dia""",
            (uid, 1 if b.get("ativo", atual["ativo"]) else 0, json.dumps(temas, ensure_ascii=False), hora,
             max(1, min(5, int(b.get("videos_dia") or atual["videos_dia"]))), max(1, min(5, int(b.get("cortes_video") or atual["cortes_video"]))),
             b.get("objetivo") if b.get("objetivo") in ("tiktok", "viral", "reels") else atual["objetivo"],
             1 if b.get("postar", atual["postar"]) else 0, hora_post, agora(), posts_dia))
    hoje_br = dt.datetime.now(BRT)
    if hora <= hoje_br.strftime("%H:%M"):
        db.exec("UPDATE cacador SET ultimo_dia=? WHERE usuario=? AND (ultimo_dia IS NULL OR ultimo_dia<?)",
                (hoje_br.strftime("%Y-%m-%d"),) * 1 + (uid, hoje_br.strftime("%Y-%m-%d")))
    return config(db, uid)


def buscar(tema: str, cfg, quantos: int = 15) -> list[dict]:
    """Vídeos da semana sobre o tema (YouTube), já filtrados: gravado (não ao vivo), de 5 min até o limite, com público."""
    import yt_dlp
    from app.motor.fonte import _opcoes
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote(tema) + "&sp=" + urllib.parse.quote(FILTRO_SEMANA)
           + "&hl=pt-BR&gl=BR")
    o = {**_opcoes(cfg), "extract_flat": "in_playlist", "playlistend": quantos,
         "http_headers": {"Accept-Language": "pt-BR,pt;q=0.9"}, "extractor_args": {"youtube": {"lang": ["pt-BR"]}}}
    with yt_dlp.YoutubeDL(o) as y:
        i = y.extract_info(url, download=False)
    out = []
    for e in i.get("entries") or []:
        dur, views = float(e.get("duration") or 0), int(e.get("view_count") or 0)
        if e.get("live_status") in ("is_live", "is_upcoming") or not e.get("id"):
            continue
        if dur < 300 or dur > cfg.max_duracao_s or views < 5000:
            continue
        if not _parece_pt(e.get("title") or ""):
            continue
        out.append({"id": e["id"], "url": f"https://www.youtube.com/watch?v={e['id']}", "titulo": e.get("title") or "", "views": views, "duracao": dur,
                    "canal": e.get("channel") or e.get("uploader") or ""})
    return sorted(out, key=lambda x: -x["views"])


_PT = re.compile(r"[ãõçêéáíóúâô]|\b(de|do|da|dos|das|que|não|nao|com|pra|para|no|na|ao|vivo|jogando|gameplay|live|meu|minha|eu|você|voce|isso|muito|o|os|inicio|início|parte|zerando|mano|galera|ele|ela|cara)\b", re.I)


def _parece_pt(titulo: str) -> bool:
    """Público do Viralizaí é brasileiro: só vídeo com cara de português (palavra/acento comum) ou de jogo/live."""
    return bool(_PT.search(titulo or ""))


def rodar(db: Banco, cfg, uid: int, criar_pedido) -> dict:
    """Uma rodada: busca, escolhe vídeos nunca usados por esse cliente e manda cortar. `criar_pedido(u, url, entrada) -> pedido`."""
    u = db.um("SELECT * FROM usuarios WHERE id=?", (uid,))
    c = config(db, uid)
    resumo = {"quando": agora(), "temas": c["temas"], "achados": 0, "pedidos": [], "erro": None}
    if not u or not pode_usar(u):
        resumo["erro"] = "O Caçador é do plano Piloto Automático (ou do adicional Caçador)."
    elif not c["temas"]:
        resumo["erro"] = "Escolha pelo menos um tema."
    else:
        vistos = {r["fonte"] for r in db.todos("SELECT fonte FROM cacador_vistos WHERE usuario=?", (uid,))}
        candidatos: list[dict] = []
        for t in c["temas"]:
            try:
                candidatos += [x for x in buscar(t, cfg) if f"yt:{x['id']}" not in vistos]
            except Exception as e:  # noqa: BLE001  um tema que falha não derruba os outros
                log.warning("caçador busca %s: %s", t, e)
        unicos = {x["id"]: x for x in sorted(candidatos, key=lambda x: -x["views"])}
        resumo["achados"] = len(unicos)
        for x in list(unicos.values())[: c["videos_dia"]]:
            try:
                p = criar_pedido(u, x["url"], {"objetivo": c["objetivo"], "quantos": c["cortes_video"], "cacador": True,
                                                 "postar_auto": c["postar"], "hora_post": c["hora_post"], "posts_dia": c.get("posts_dia") or 1})
                db.exec("INSERT OR IGNORE INTO cacador_vistos(usuario,fonte,quando) VALUES(?,?,?)", (uid, f"yt:{x['id']}", agora()))
                resumo["pedidos"].append({"id": p["id"], "titulo": x["titulo"][:90], "canal": x["canal"], "views": x["views"]})
            except Exception as e:  # noqa: BLE001
                resumo["erro"] = str(getattr(e, "detail", e))[:200]
                break
        if resumo["pedidos"]:
            avisos.novo(db, uid, f"O Caçador achou {len(resumo['pedidos'])} vídeo(s) do seu tema e já está cortando 🎯", "/app#/videos")
    db.exec("INSERT INTO cacador_rodadas(usuario,quando,resumo) VALUES(?,?,?)", (uid, agora(), json.dumps(resumo, ensure_ascii=False)))
    return resumo


def rodadas(db: Banco, uid: int) -> list[dict]:
    return [json.loads(r["resumo"]) for r in db.todos("SELECT resumo FROM cacador_rodadas WHERE usuario=? ORDER BY quando DESC LIMIT 10", (uid,))]


def proximo_horario(hora: str, base: dt.datetime | None = None) -> float:
    """Epoch do próximo hh:mm (horário de Brasília), hoje ou amanhã."""
    base = base or dt.datetime.now(BRT)
    h, m = map(int, hora.split(":"))
    alvo = base.replace(hour=h, minute=m, second=0, microsecond=0)
    if alvo <= base:
        alvo += dt.timedelta(days=1)
    return alvo.timestamp()


def iniciar(db: Banco, cfg, parar: threading.Event, criar_pedido) -> None:
    """Relógio do Caçador: a cada minuto, roda quem chegou no horário e ainda não rodou hoje (Brasília)."""
    def laco():
        while not parar.wait(60):
            try:
                agora_br = dt.datetime.now(BRT)
                hoje, hhmm = agora_br.strftime("%Y-%m-%d"), agora_br.strftime("%H:%M")
                for c in db.todos("SELECT usuario, hora FROM cacador WHERE ativo=1 AND (ultimo_dia IS NULL OR ultimo_dia<?) AND hora<=?", (hoje, hhmm)):
                    db.exec("UPDATE cacador SET ultimo_dia=? WHERE usuario=?", (hoje, c["usuario"]))
                    rodar(db, cfg, c["usuario"], criar_pedido)
            except Exception:  # noqa: BLE001
                log.exception("relógio do caçador")
    threading.Thread(target=laco, daemon=True, name="cacador").start()


def horarios_livres(db: Banco, conta: int, hora_post: str, posts_dia: int, quantos: int, base: dt.datetime | None = None) -> list[float]:
    """Próximos `quantos` horários livres da conta: até `posts_dia` por dia, espalhados a partir de `hora_post`
    (intervalo de 10 h / posts_dia, mínimo 1 h), pulando horários que já passaram ou já têm post."""
    base = base or dt.datetime.now(BRT)
    h, m = map(int, hora_post.split(":"))
    passo = max(3600, int(10 * 3600 / max(1, posts_dia)))
    ocupados = [r["quando"] for r in db.todos("SELECT quando FROM posts WHERE conta=? AND estado IN ('agendado','publicando') AND quando>=?",
                                             (conta, base.timestamp() - 3600))]
    out: list[float] = []
    dia = base.replace(hour=h, minute=m, second=0, microsecond=0)
    for _ in range(400):
        for i in range(posts_dia):
            t = (dia + dt.timedelta(seconds=i * passo)).timestamp()
            if t <= base.timestamp() + 120 or any(abs(t - o) < 600 for o in ocupados + out):
                continue
            out.append(t)
            if len(out) >= quantos:
                return out
        dia += dt.timedelta(days=1)
    return out


def agendar_posts_do_pedido(db: Banco, cfg, t: dict, res: dict) -> int:
    """Pedido do Caçador com "postar sozinho": os cortes (melhor nota primeiro) vão para cada rede conectada, até `posts_dia`
    por dia em cada uma, nos próximos horários livres. Se o vídeo rendeu menos cortes, posta só os que existem. Sem repetir."""
    from app import fila, postar
    entrada = json.loads(t["entrada"])
    if not entrada.get("postar_auto"):
        return 0
    contas = [k for k in postar.contas_ativas(db, t["usuario"]) if k["estado"] == "conectada"]
    if not contas:
        avisos.novo(db, t["usuario"], "Seus cortes do Caçador ficaram prontos, mas nenhuma rede está conectada pra postar sozinho.", "/app#/postagens")
        return 0
    cortes = sorted([c for c in res.get("cortes", []) if c.get("estado") == "pronto"], key=lambda c: -(c.get("nota") or 0))
    pasta = fila.pasta_trabalho(cfg, t["id"])
    n = 0
    for conta in contas:
        novos = [c for c in cortes if not db.um("SELECT 1 FROM posts WHERE conta=? AND pedido=? AND k=?", (conta["id"], t["id"], c["k"]))]
        horarios = horarios_livres(db, conta["id"], entrada.get("hora_post") or "19:00", int(entrada.get("posts_dia") or 1), len(novos))
        for c, quando in zip(novos, horarios):
            postar.agendar(db, cfg, t["usuario"], conta["id"], pasta / c["arquivo"], postar.legenda_pronta(c), quando, t["id"], c["k"],
                           pasta / c["capa"] if c.get("capa") else None, origem="cacador")
            n += 1
    if n:
        avisos.novo(db, t["usuario"], f"{n} post(s) agendado(s) sozinho(s) a partir do Caçador 🚀", "/app#/postagens")
    return n
