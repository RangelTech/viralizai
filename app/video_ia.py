"""Vídeo com IA (spec 47 §10): moedas (1 = 1 vídeo de 10 s), prévia grátis em imagem, refazer grátis 1x,
erro do fornecedor devolve a moeda. Geração pelo Estúdio do llm-access (Runware); a chave da Runware nunca sai de lá."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx
from fastapi import HTTPException

from app import fila
from app.db import agora
from app.motor.juiz import _json

log = logging.getLogger("viralizai.video_ia")
SEGUNDOS = 10
PREVIAS_DIA = 25

MOLDES = [
    {"codigo": "bicho", "nome": "Bicho dançando", "exemplo": "um gato laranja dançando funk numa laje no Rio", "dica": "bicho + dança + lugar"},
    {"codigo": "cantando", "nome": "Objeto/bicho cantando", "exemplo": "uma coxinha cantando sertanejo num palco com luzes", "dica": "quem canta + estilo + palco"},
    {"codigo": "pegadinha", "nome": "Pegadinha", "exemplo": "um cachorro tomando susto com um pepino na cozinha", "dica": "quem + susto + com o quê"},
    {"codigo": "asmr", "nome": "ASMR", "exemplo": "faca cortando uma fruta de vidro colorida em câmera lenta", "dica": "o que corta/derrete + material"},
    {"codigo": "heroi", "nome": "Herói/vilão", "exemplo": "um capivara super-herói voando sobre São Paulo", "dica": "personagem + poder + cidade"},
    {"codigo": "bebe", "nome": "Bebê falando", "exemplo": "um bebê de terno dando bronca como chefe numa reunião", "dica": "bebê + profissão + situação"},
    {"codigo": "livre", "nome": "Livre", "exemplo": "um carro de GTA voando entre prédios ao pôr do sol", "dica": "descreva a cena"},
]

DIRETOR = """Reescreva o pedido do cliente como prompt para um modelo de VÍDEO de IA (10 segundos, vertical 9:16), em INGLÊS.
Molde: {molde}. Pedido: "{pedido}". Ajuste pedido agora: "{ajuste}".
Regras: 1 cena contínua, 1 ação clara e engraçada/impactante, câmera descrita (ex.: "handheld close-up", "slow dolly in"), luz e estilo
(ex.: "photorealistic, cinematic lighting"), sem texto escrito na tela, sem pessoas famosas reais, sem marcas registradas.
Também escreva "imagem": o prompt do PRIMEIRO QUADRO (mesma cena parada) para uma prévia, e "legenda": legenda curta do post em português com 3 hashtags.
Responda SÓ com JSON: {{"video": "...", "imagem": "...", "legenda": "..."}}"""


def _llm(cfg, prompt: str) -> dict:
    r = httpx.post(cfg.llm_base + "/chat/completions", headers={"Authorization": f"Bearer {cfg.llm_key}"}, timeout=120,
                   json={"model": cfg.llm_modelo, "temperature": 0.7, "max_tokens": 900, "response_format": {"type": "json_object"},
                         "chat_template_kwargs": {"enable_thinking": False}, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return _json(r.json()["choices"][0]["message"]["content"])


def previa(db, u: dict, pedido: str, molde: str, ajuste: str, cfg) -> dict:
    """Prévia grátis: o diretor reescreve o pedido e gera 1 imagem da cena (GPT, sem custo de moeda)."""
    if len(pedido.strip()) < 5:
        raise HTTPException(422, "Me conta o que você quer ver (uma frase já serve).")
    hoje = Path(cfg.dados) / "previas"
    hoje.mkdir(parents=True, exist_ok=True)
    feitas = len([p for p in hoje.glob(f"{u['id']}_*") if p.stat().st_mtime > time.time() - 86400])
    if feitas >= PREVIAS_DIA:
        raise HTTPException(429, "Você já fez muitas prévias hoje. Gera um vídeo com uma delas ou volta amanhã.")
    nome_molde = next((m["nome"] for m in MOLDES if m["codigo"] == molde), "Livre")
    try:
        d = _llm(cfg, DIRETOR.format(molde=nome_molde, pedido=pedido, ajuste=ajuste or "nenhum"))
    except Exception as e:  # noqa: BLE001
        log.warning("diretor video ia: %s", e)
        raise HTTPException(503, "A IA está ocupada agora. Tenta de novo em 1 minuto.")
    img = None
    try:
        r = httpx.post(cfg.llm_base + "/images/generations", headers={"Authorization": f"Bearer {cfg.llm_key}"}, timeout=180,
                       json={"model": cfg.imagem_modelo, "prompt": d.get("imagem") or d.get("video"), "size": "1024x1536", "n": 1})
        r.raise_for_status()
        item = r.json()["data"][0]
        dados = base64.b64decode(item["b64_json"]) if item.get("b64_json") else httpx.get(item["url"], timeout=60).content
        nome = f"{u['id']}_{hashlib.sha256(dados).hexdigest()[:12]}.jpg"
        (hoje / nome).write_bytes(dados)
        img = nome
    except Exception as e:  # noqa: BLE001  sem imagem a prévia ainda mostra o roteiro
        log.warning("previa imagem: %s", str(e)[:200])
    return {"pedido": pedido, "molde": molde, "prompt": d.get("video") or "", "legenda": d.get("legenda") or "",
            "imagem": img, "imagem_url": f"/api/video_ia/previa/{img}" if img else None, "moedas_custo": 1}


def pedir(db, u: dict, b: dict, refazer: str, prioridade: int, perfil: dict) -> str:
    prompt = str(b.get("prompt") or "").strip()[:1500]
    if len(prompt) < 10:
        raise HTTPException(422, "Gera a prévia antes.")
    gratis = False
    if refazer:  # "não ficou bom? refazer grátis" (1 vez por vídeo)
        t = db.um("SELECT * FROM trabalhos WHERE id=? AND usuario=? AND tipo='video_ia'", (refazer, u["id"]))
        if not t or json.loads(t["entrada"]).get("refazer_de") or db.um("SELECT 1 FROM trabalhos WHERE usuario=? AND entrada LIKE ?", (u["id"], f'%"refazer_de": "{refazer}"%')):
            raise HTTPException(409, "Esse vídeo já foi refeito uma vez.")
        gratis = True
    if not gratis:
        with db.tx() as c:
            n = c.execute("UPDATE usuarios SET moedas=moedas-1 WHERE id=? AND moedas>=1", (u["id"],)).rowcount
            if not n:
                raise HTTPException(402, {"mensagem": "Você está sem moedas 🪙 Pega um pacote e cria na hora.", "moedas": True})
            c.execute("INSERT INTO moedas_mov(usuario,delta,motivo,quando) VALUES(?,?,?,?)", (u["id"], -1, "video_ia", agora()))
    img = str(b.get("imagem") or "")
    entrada = {"prompt": prompt, "imagem": img if img.startswith(f"{u['id']}_") else "", "legenda": str(b.get("legenda") or "")[:400],
               "molde": b.get("molde") or "livre", "perfil": perfil, "cobrado": not gratis, **({"refazer_de": refazer} if refazer else {})}
    return fila.criar(db, u["id"], "video_ia", entrada, prioridade)


def devolver(db, t: dict) -> None:
    """Falhou do nosso lado ou do fornecedor: a moeda volta."""
    e = json.loads(t["entrada"])
    if e.get("cobrado") and not e.get("devolvido"):
        db.exec("UPDATE usuarios SET moedas=moedas+1 WHERE id=?", (t["usuario"],))
        db.exec("INSERT INTO moedas_mov(usuario,delta,motivo,ref,quando) VALUES(?,?,?,?,?)", (t["usuario"], 1, "devolucao", t["id"], agora()))
        db.exec("UPDATE trabalhos SET entrada=json_set(entrada,'$.devolvido',1) WHERE id=?", (t["id"],))


def fazer(db, t: dict, entrada: dict, pasta: Path, cfg, avisar) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    corpo = {"efeito": cfg.estudio_efeito, "prompt": entrada["prompt"], "duracao": SEGUNDOS, "segundos": SEGUNDOS, "largura": 480, "altura": 848}
    if entrada.get("imagem"):  # a prévia vira o primeiro quadro: sai como o cliente aprovou
        p = Path(cfg.dados) / "previas" / entrada["imagem"]
        if p.exists():
            corpo["inputs"] = {"frameImages": [{"inputImage": "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode(), "frame": "first"}]}
    h = {"Authorization": f"Bearer {cfg.llm_key}"}
    avisar("Criando seu vídeo", 0.1)
    r = httpx.post(cfg.estudio_base + "/estudio/gerar", headers=h, json=corpo, timeout=120)
    if r.status_code >= 400:
        log.warning("estudio gerar %s: %s", r.status_code, r.text[:300])
        raise fila.ErroUsuario("O criador de vídeo está fora do ar agora. Sua moeda foi devolvida.")
    job = r.json()
    ini = time.time()
    while job.get("status") == "running" and time.time() - ini < 900:
        time.sleep(4)
        avisar("Criando seu vídeo", min(0.85, 0.1 + (time.time() - ini) / max(60, job.get("tempo_estimado_s") or 90) * 0.7))
        job = httpx.get(cfg.estudio_base + f"/estudio/jobs/{job['id']}", headers=h, timeout=30).json()
    if job.get("status") != "done" or not job.get("url"):
        raise fila.ErroUsuario("Não deu certo criar esse vídeo. Sua moeda foi devolvida; tenta de novo.")
    bruto = pasta / "ia_bruto.mp4"
    with httpx.stream("GET", job["url"], timeout=120, follow_redirects=True) as s, open(bruto, "wb") as f:
        for parte in s.iter_bytes():
            f.write(parte)
    avisar("Colocando seu @", 0.92)
    from app import estilo
    from app.pipeline import duracao
    perfil = entrada.get("perfil") or {}
    final = pasta / "video_ia.mp4"
    import subprocess
    # 9:16 em 720x1280 + @ do cliente (sem legenda: não tem fala)
    a = pasta / "ia.ass"
    a.write_text(estilo.ass([], duracao(bruto), "", "tiktok", perfil.get("arroba") or "", perfil.get("cor") or estilo.COR_PADRAO, False), encoding="utf-8")
    rr = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(bruto), "-vf", f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,{estilo._filtro(a)}",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(final)],
                        capture_output=True, text=True)
    a.unlink(missing_ok=True)
    if rr.returncode != 0:
        final = bruto
    capa = pasta / "video_ia.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", str(final), "-frames:v", "1", "-vf", "scale=360:-2", str(capa)], check=False)
    return {"titulo": entrada.get("legenda")[:60] if entrada.get("legenda") else "Vídeo com IA", "custo_usd": job.get("custo_usd"),
            "cortes": [{"k": 1, "estado": "pronto", "arquivo": final.name, "arquivos": {"tiktok": final.name}, "capa": capa.name if capa.exists() else None,
                        "titulo": "Vídeo com IA", "legenda": entrada.get("legenda") or "", "hashtags": [], "duracao": round(duracao(final), 1),
                        "pode_refazer": not entrada.get("refazer_de")}]}
