"""Testes do Viralizaí: motor (parse, sinais, candidatos, juiz sem IA), fila justa, API (cadastro, teste grátis, paywall,
isolamento, vitrine, Cakto) e validação dos roteiros de animação. Sem rede: nada de YouTube nem LLM de verdade."""
import json
import os
import time

import numpy as np
import pytest

os.environ["VIRALIZAI_SEM_APP"] = "1"

from app.motor import candidatos, fonte, juiz, sinais  # noqa: E402


# ---------------------------------------------------------------- motor
def test_chave_rapida():
    assert fonte.chave_rapida("https://www.youtube.com/watch?v=YV9u_1VzZDQ&t=10") == "yt:YV9u_1VzZDQ"
    assert fonte.chave_rapida("https://youtu.be/YV9u_1VzZDQ") == "yt:YV9u_1VzZDQ"
    assert fonte.chave_rapida("https://www.youtube.com/live/YV9u_1VzZDQ") == "yt:YV9u_1VzZDQ"
    assert fonte.chave_rapida("https://www.twitch.tv/videos/123456") == "tw:123456"
    assert fonte.chave_rapida("https://kick.com/x") is None


def test_lingua_legenda_nunca_pede_traducao():
    i = {"language": "pt", "subtitles": {"live_chat": []}, "automatic_captions": {"pt-orig": [], "pt": [], "pt-PT": [], "en": []}}
    assert fonte.lingua_legenda(i) == ("pt-orig", True)
    i2 = {"language": "pt", "subtitles": {"pt-BR": []}, "automatic_captions": {"pt-orig": []}}
    assert fonte.lingua_legenda(i2) == ("pt-BR", False)


def test_json3_palavras_e_frases(tmp_path):
    j = {"events": [{"tStartMs": 1000, "dDurationMs": 3000, "segs": [{"utf8": "fala"}, {"utf8": " galera", "tOffsetMs": 400}, {"utf8": " [Música]", "tOffsetMs": 900}]},
                    {"tStartMs": 6000, "dDurationMs": 1000, "segs": [{"utf8": "matei"}, {"utf8": " todo", "tOffsetMs": 300}]}]}
    p = tmp_path / "a.json3"
    p.write_text(json.dumps(j))
    w = fonte.palavras_json3(p)
    assert [x["word"] for x in w] == ["fala", "galera", "matei", "todo"]
    assert w[1]["start"] == 1.4 and w[2]["start"] == 6.0
    segs = fonte.frases(w)
    assert len(segs) == 2 and segs[1]["text"] == "matei todo"


def test_chat_youtube_e_dinheiro(tmp_path):
    linhas = [
        {"replayChatItemAction": {"videoOffsetTimeMsec": "12000", "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "message": {"runs": [{"text": "KKKKKK "}, {"emoji": {"shortcuts": [":fire:"]}}]}, "authorName": {"simpleText": "ana"}}}}}]}},
        {"replayChatItemAction": {"videoOffsetTimeMsec": "15000", "actions": [{"addChatItemAction": {"item": {"liveChatPaidMessageRenderer": {
            "message": {"runs": [{"text": "toma 10"}]}, "authorName": {"simpleText": "bia"}}}}}]}},
    ]
    p = tmp_path / "c.json"
    p.write_text("\n".join(json.dumps(x) for x in linhas))
    m = fonte.chat_youtube(p)
    assert len(m) == 2 and m[0]["t"] == 12.0 and ":fire:" in m[0]["texto"] and m[1]["pago"]
    s = sinais.serie_chat(m, 30, atraso=6)
    assert s["risada"][6] == 1 and s["pago"][9] == 1


def test_comentarios_com_tempo():
    c = fonte.comentarios_com_tempo({"comments": [{"text": "1:02:10 kkkk e 3:15 também", "like_count": 40}, {"text": "99:99 nada"}]}, 4000)
    assert sorted(x["t"] for x in c) == [195.0, 3730.0]


def test_heatmap_ignora_abertura():
    ctx = {"heatmap": [{"a": 0, "b": 60, "v": 1.0}, {"a": 600, "b": 620, "v": 0.8}]}
    s = sinais.serie_publico(ctx, [], 1200)
    assert s[30] == 0 and s[610] == pytest.approx(0.8)


def test_tipo_do_video():
    assert sinais.tipo_do_video({"titulo": "GTA RP cidade alta", "categorias": ["Gaming"], "tags": []}) == "gameplay"
    assert sinais.tipo_do_video({"titulo": "REACT do vídeo mais estranho", "categorias": [], "tags": []}) == "react"
    assert sinais.tipo_do_video({"titulo": "Flow podcast #300", "categorias": ["People"], "tags": []}) == "podcast"


def _segs(dur):
    return [{"start": float(t), "end": float(t) + 4.5, "text": f"frase {t}"} for t in range(0, dur, 5)]


def test_candidatos_duracao_e_sem_sobrepor():
    dur = 1800
    nota = np.zeros(dur)
    for p in (300, 900, 1500):
        nota[p - 3:p + 3] = 1.0
    c = candidatos.gerar(nota, _segs(dur), [], 3, "tiktok")
    assert len(c) == 3
    for x in c:
        assert 61 * 0.85 <= x["fim"] - x["inicio"] <= 95
        assert x["inicio"] <= x["pico"] <= x["fim"]
    for a in c:
        for b in c:
            if a is not b:
                assert a["fim"] <= b["inicio"] or a["inicio"] >= b["fim"]


def test_candidatos_viral_curto():
    nota = np.zeros(600)
    nota[300] = 1.0
    c = candidatos.gerar(nota, _segs(600), [], 1, "viral")
    assert c and 17 <= c[0]["fim"] - c[0]["inicio"] <= 45


def test_juiz_sem_ia_nao_derruba():
    class C:
        llm_base, llm_key, llm_modelo = "http://127.0.0.1:9", "x", "m"
    import httpx
    cands = [{"inicio": 10.0, "fim": 80.0, "pico": 50, "nota_sinal": 0.8}, {"inicio": 100.0, "fim": 170.0, "pico": 150, "nota_sinal": 0.2}]
    with httpx.Client(timeout=1) as cl:
        j = juiz.julgar(cands, _segs(200), {"titulo": "x", "canal": "y"}, "gameplay", "tiktok", lambda a, b: "chat 5x o normal", C(), cl)
    assert [x["juiz"] for x in j] == [False, False] and j[0]["nota"] > j[1]["nota"]


def test_juiz_json_torto_e_variados():
    assert juiz._json('ok {"cortes":[{"id":1,"nota":5,},]}')["cortes"][0]["nota"] == 5
    assert juiz._id({"id": "#3"}, 1) == 3 and juiz._id({}, 7) == 7
    js = [{"nota": 90, "assunto": "fuga"}, {"nota": 85, "assunto": "fuga"}, {"nota": 70, "assunto": "casamento"}]
    assert [x["nota"] for x in juiz.variados(js, 2)] == [90, 70]


# ---------------------------------------------------------------- app
@pytest.fixture()
def cli(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Config
    from app.main import criar_app
    cfg = Config(dados=str(tmp_path), dev=True, admin_key="adm", cakto_segredo="seg",
                 planos_por_produto={"p-corte": "corte", "p-m5": "m5"}, checkouts={"corte": "https://pay.cakto.com.br/x"})
    app = criar_app(cfg, iniciar_fila=False)
    return TestClient(app), app.state.db


def _conta(c, email="joao@t.com", nome="Joao"):
    r = c.post("/api/cadastro", json={"nome": nome, "email": email, "senha": "senha-forte-1", "whatsapp": "62999990000", "aceite": True})
    assert r.status_code == 200, r.text
    return r


def test_cadastro_validacoes(cli):
    c, _ = cli
    assert c.post("/api/cadastro", json={"nome": "", "email": "a@b.com", "senha": "12345678", "aceite": True}).status_code == 422
    assert c.post("/api/cadastro", json={"nome": "A", "email": "a@b.com", "senha": "123", "aceite": True}).status_code == 422
    assert c.post("/api/cadastro", json={"nome": "A", "email": "a@b.com", "senha": "12345678"}).status_code == 422
    _conta(c, "a@b.com")
    r = c.post("/api/cadastro", json={"nome": "A", "email": "a@b.com", "senha": "12345678", "aceite": True})
    assert r.status_code == 409 and "já tem conta" in r.json()["detail"]
    conta = c.get("/api/conta").json()
    assert conta["plano"] == "teste" and conta["restam_cortes"] == 1 and conta["whatsapp"] == "5562999990000"


def test_teste_gratis_um_corte_e_paywall(cli):
    c, db = cli
    _conta(c)
    r = c.post("/api/cortes", json={"url": "https://www.youtube.com/watch?v=YV9u_1VzZDQ", "quantos": 5})
    assert r.status_code == 200 and r.json()["entrada"]["quantos"] == 1 and r.json()["entrada"]["teste"]
    r = c.post("/api/cortes", json={"url": "https://www.youtube.com/watch?v=YV9u_1VzZDQ", "quantos": 1})
    assert r.status_code == 402 and r.json()["detail"]["plano"] == "corte"
    assert c.post("/api/animacao", json={"roteiro": {"cenas": [{"fala": "x"}]}}).status_code == 402


def test_link_invalido(cli):
    c, _ = cli
    _conta(c)
    assert c.post("/api/cortes", json={"url": "https://exemplo.com/video"}).status_code == 422
    assert c.post("/api/link", json={"url": "nada"}).status_code == 422


def test_isolamento_entre_clientes(cli):
    c, db = cli
    _conta(c, "a@t.com")
    p = c.post("/api/cortes", json={"url": "https://youtu.be/YV9u_1VzZDQ"}).json()
    c.post("/api/sair")
    _conta(c, "b@t.com")
    assert c.get(f"/api/pedidos/{p['id']}").status_code == 404
    assert c.get(f"/api/pedidos/{p['id']}/arquivo/corte1.mp4").status_code == 404


def test_cakto_plano_e_moedas_idempotente(cli):
    c, db = cli
    _conta(c)
    ev = {"secret": "seg", "event": "purchase_approved", "data": {"id": "v1", "customer": {"email": "joao@t.com"}, "product": {"id": "p-corte"}}}
    assert c.post("/api/cakto", json={**ev, "secret": "errado"}).status_code == 401
    assert c.post("/api/cakto", json=ev).json()["plano"] == "corte"
    assert c.post("/api/cakto", json=ev).json()["repetido"]
    m = {"secret": "seg", "event": "purchase_approved", "data": {"id": "v2", "customer": {"email": "joao@t.com"}, "product": {"id": "p-m5"}}}
    assert c.post("/api/cakto", json=m).json()["moedas"] == 5
    conta = c.get("/api/conta").json()
    assert conta["plano"] == "corte" and conta["moedas"] == 5 and conta["restam_cortes"] == 30


def test_video_ia_sem_moeda(cli):
    c, db = cli
    _conta(c)
    r = c.post("/api/video_ia", json={"prompt": "a cat dancing funk on a rooftop"})
    assert r.status_code == 402 and r.json()["detail"]["moedas"]


def test_video_ia_cobra_e_devolve(cli):
    c, db = cli
    _conta(c)
    db.exec("UPDATE usuarios SET moedas=2")
    p = c.post("/api/video_ia", json={"prompt": "a cat dancing funk on a rooftop"}).json()
    assert c.get("/api/conta").json()["moedas"] == 1
    from app.video_ia import devolver
    t = db.um("SELECT * FROM trabalhos WHERE id=?", (p["id"],))
    devolver(db, t)
    devolver(db, db.um("SELECT * FROM trabalhos WHERE id=?", (p["id"],)))  # 2x não devolve 2 moedas
    assert c.get("/api/conta").json()["moedas"] == 2


def test_vitrine_so_publica_e_limite(cli, tmp_path):
    c, db = cli
    from app import planos
    prev = tmp_path / "p.mp4"
    prev.write_bytes(b"0" * 100)
    agora = time.time()
    db.exec("INSERT INTO fontes(chave,url,publica,criado) VALUES('yt:a','u',1,?),('up:1-x','upload',0,?)", (agora, agora))
    for f in ("yt:a", "up:1-x"):
        db.exec("INSERT INTO cortes_base(fonte,objetivo,inicio,fim,nota,gancho,tema,previa,capa,publico,criado) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f, "tiktok", 0, 70, 90, "G", "gta", str(prev), str(prev), 1 if f == "yt:a" else 0, agora))
    _conta(c)
    v = c.get("/api/vitrine").json()
    assert len(v["secoes"][0]["itens"]) == 1  # o upload privado nunca aparece
    bid = v["secoes"][0]["itens"][0]["id"]
    assert c.post(f"/api/vitrine/{bid}/usar").status_code == 402  # teste grátis só vê
    for _ in range(planos.LIMITE_USOS_DIA):
        db.exec("INSERT INTO usos(corte_base,usuario,quando) VALUES(?,?,?)", (bid, 99, agora))
    assert c.get("/api/vitrine").json()["secoes"][0]["itens"] == []  # esgotou hoje: some de "Em alta"
    assert c.get("/api/publico/vitrine").status_code == 200


def test_fila_justa_primeiro_corte_de_todos(cli):
    _, db = cli
    from app import fila
    agora = time.time()
    for tid in ("A", "B"):
        db.exec("INSERT INTO trabalhos(id,usuario,tipo,entrada,estado,criado) VALUES(?,?,?,?,?,?)", (tid, 1, "cortes", "{}", "montando", agora))
    # A pediu antes e tem 3 cortes; B chegou depois
    for k in (1, 2, 3, 99):
        db.exec("INSERT INTO tarefas(trabalho,k,dados,criado) VALUES('A',?,'{}',?)", (k, agora + k))
    db.exec("INSERT INTO tarefas(trabalho,k,dados,criado) VALUES('B',1,'{}',?)", (agora + 10,))
    db.exec("INSERT INTO trabalhos(id,usuario,tipo,entrada,estado,criado) VALUES('C',1,'cortes','{}','fila',?)", (agora + 20,))
    ordem = []
    x = fila._pegar(db)
    ordem.append("A1")
    assert x[1]["trabalho"] == "A" and x[1]["k"] == 1
    # enquanto o 1º corte de A roda, o 2º de A espera: a CPU vai para o 1º de B e para a análise de C
    seguintes = []
    while (y := fila._pegar(db)):
        seguintes.append(y[1].get("trabalho", y[1]["id"]) + (str(y[1]["k"]) if y[0] == "tarefa" else ""))
    assert seguintes == ["B1", "C"]
    db.exec("UPDATE tarefas SET estado='pronto' WHERE trabalho='A' AND k=1")
    while (y := fila._pegar(db)):
        seguintes.append(y[1].get("trabalho", y[1]["id"]) + str(y[1]["k"]))
    assert seguintes == ["B1", "C", "A2", "A3"]  # a prévia da vitrine (A99) espera os cortes do cliente
    db.exec("UPDATE tarefas SET estado='pronto' WHERE trabalho='A' AND k IN (2,3)")
    assert fila._pegar(db)[1]["k"] == 99


def test_animacao_validar_esquema():
    from app import animacao_v2 as a
    r = a.validar({"formato": "top5", "gancho": "um dois tres quatro cinco seis sete oito nove", "cenas": [{"fala": "oi", "n": "5", "titulo": "x", "lixo": "<script>"}, {"fala": ""}]})
    assert r["gancho"] == "UM DOIS TRES QUATRO CINCO SEIS SETE" and len(r["cenas"]) == 1 and "lixo" not in r["cenas"][0] and r["cenas"][0]["n"] == 5
    q = a.validar({"formato": "quiz", "pergunta": "?", "opcoes": ["a", "b", "c"], "certa": 9})
    assert q["quiz"]["certa"] == 2 and len(q["cenas"]) == 2
    with pytest.raises(ValueError):
        a.validar({"formato": "historia", "cenas": []})
    assert a.escolher_formato("top 5 carros do GTA") == "top5" and a.escolher_formato("quiz de futebol") == "quiz"


def test_paginas(cli):
    c, _ = cli
    assert "Viraliz" in c.get("/").text and "v6_hero" not in c.get("/").text
    assert "v6_hero" in c.get("/", headers={"host": "viralizai.fael.rangeltech.net"}).text
    assert c.get("/app").status_code == 200 and c.get("/termos").status_code == 200 and c.get("/health").json()["ok"]


def test_animacao_validar_idempotente():
    from app import animacao_v2 as a
    for bruto in ({"formato": "conversa", "contato": "Chefe", "mensagens": [{"de": "eu", "texto": "oi"}, {"de": "Chefe", "texto": "fala"}]},
                  {"formato": "quiz", "pergunta": "?", "opcoes": ["a", "b", "c"], "certa": 1, "fala_pergunta": "x", "fala_revela": "y"},
                  {"formato": "versus", "a": "A", "b": "B", "quesitos": [{"rotulo": "q", "va": 7, "vb": 3, "fala": "f"}], "abertura": "o", "veredito": "v", "vencedor": "a"},
                  {"formato": "noticia", "faixa": "URGENTE", "manchete": "m", "cenas": [{"fala": "f"}], "numeros": [{"rotulo": "r", "valor": "1"}]}):
        uma = a.validar(bruto)
        assert a.validar(uma) == uma, bruto["formato"]


# ---------------------------------------------------------------- postar sozinho e caçador
def _fake_pn(registro):
    import httpx

    def h(req):
        caminho = req.url.path
        registro.append((req.method, caminho))
        if caminho == "/logins":
            return httpx.Response(200, json={"id": "L1", "passo": {"tipo": "qr", "imagem": "data:image/png;base64,AA", "espera_s": 3}})
        if caminho.startswith("/logins/L1"):
            return httpx.Response(200, json={"id": "L1", "passo": {"tipo": "conectado"}})
        if caminho.endswith("/publicar"):
            if len([r for r in registro if r[1].endswith("/publicar")]) == 1:
                return httpx.Response(502, json={"detail": "rede fora"})  # 1ª tentativa falha: tem que reenviar
            return httpx.Response(200, json={"link": "https://tiktok.com/@x/video/1"})
        return httpx.Response(200, json={})
    return httpx.MockTransport(h)


def test_postar_sozinho_ponta_a_ponta(cli, tmp_path, monkeypatch):
    c, db = cli
    from app import postar, pn as pnmod
    reg = []
    transporte = _fake_pn(reg)
    monkeypatch.setattr(postar, "cliente", lambda cfg: pnmod.PN("http://pn", "tok", transporte))
    _conta(c)
    assert c.post("/api/contas", json={"rede": "tiktok", "aceite": True}).status_code == 402  # teste grátis não posta
    db.exec("UPDATE usuarios SET plano='viral', ativo_ate=?", (time.time() + 9999,))
    r = c.post("/api/contas", json={"rede": "tiktok", "aceite": True}).json()
    assert r["passo"]["tipo"] == "qr"
    assert c.get(f"/api/contas/{r['conta']}/login").json()["passo"]["tipo"] == "conectado"
    # um pedido pronto com 1 corte
    from app import fila
    pasta = fila.pasta_trabalho(c.app.state.cfg, "P1"); pasta.mkdir(parents=True)
    (pasta / "corte1.mp4").write_bytes(b"0" * 2000)
    res = {"cortes": [{"k": 1, "estado": "pronto", "arquivo": "corte1.mp4", "legenda": "olha isso", "hashtags": ["#gta"], "nota": 90}]}
    db.exec("INSERT INTO trabalhos(id,usuario,tipo,entrada,estado,resultado,criado) VALUES('P1',1,'cortes','{}','pronto',?,?)", (json.dumps(res), time.time()))
    assert c.post("/api/posts", json={"pedido": "P1", "k": 1, "contas": [r["conta"]]}).status_code == 200
    cfg = c.app.state.cfg
    postar.rodar_fila(db, cfg)
    p = db.um("SELECT * FROM posts")
    assert p["estado"] == "agendado" and p["tentativas"] == 1  # falhou 1x e foi reagendado
    db.exec("UPDATE posts SET proxima=0")
    postar.rodar_fila(db, cfg)
    p = db.um("SELECT * FROM posts")
    assert p["estado"] == "publicado" and p["link"].startswith("https://tiktok") and "#gta" in p["legenda"]
    assert any("publicar" in x[1] for x in reg)


def test_cacador_busca_corta_e_nao_repete(cli, monkeypatch):
    c, db = cli
    from app import cacador
    _conta(c)
    assert c.post("/api/cacador", json={"ativo": True, "temas": ["gta rp"]}).status_code == 402  # só no Piloto
    db.exec("UPDATE usuarios SET plano='piloto', ativo_ate=?", (time.time() + 9999,))
    monkeypatch.setattr(cacador, "buscar", lambda tema, cfg, quantos=15: [
        {"id": "AAAAAAAAAAA", "url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "titulo": "live 1", "views": 90000, "duracao": 3600, "canal": "x"},
        {"id": "BBBBBBBBBBB", "url": "https://www.youtube.com/watch?v=BBBBBBBBBBB", "titulo": "live 2", "views": 50000, "duracao": 3600, "canal": "y"}])
    cfg = c.post("/api/cacador", json={"ativo": True, "temas": ["gta rp"], "hora": "09:00", "videos_dia": 1, "cortes_video": 2}).json()
    assert cfg["temas"] == ["gta rp"] and cfg["ativo"]
    r1 = c.post("/api/cacador/rodar").json()
    assert r1["achados"] == 2 and len(r1["pedidos"]) == 1 and "live 1" in r1["pedidos"][0]["titulo"]
    r2 = c.post("/api/cacador/rodar").json()
    assert len(r2["pedidos"]) == 1 and "live 2" in r2["pedidos"][0]["titulo"]  # não repete o vídeo da 1ª rodada
    t = db.um("SELECT entrada FROM trabalhos WHERE id=?", (r1["pedidos"][0]["id"],))
    assert json.loads(t["entrada"])["cacador"] and json.loads(t["entrada"])["quantos"] == 2
    assert len(c.get("/api/postagens").json()["cacador"]["rodadas"]) == 2


def test_cacador_agenda_1_por_dia_por_rede(cli):
    c, db = cli
    from app import cacador, fila
    _conta(c)
    now = time.time()
    db.exec("INSERT INTO contas(usuario,rede,estado,criado,atualizado) VALUES(1,'tiktok','conectada',?,?),(1,'instagram','conectada',?,?)", (now, now, now, now))
    pasta = fila.pasta_trabalho(c.app.state.cfg, "C1"); pasta.mkdir(parents=True)
    for k in (1, 2):
        (pasta / f"corte{k}.mp4").write_bytes(b"0" * 1000)
    res = {"cortes": [{"k": 1, "estado": "pronto", "arquivo": "corte1.mp4", "nota": 70}, {"k": 2, "estado": "pronto", "arquivo": "corte2.mp4", "nota": 95}]}
    t = {"id": "C1", "usuario": 1, "entrada": json.dumps({"postar_auto": True, "hora_post": "19:00"})}
    assert cacador.agendar_posts_do_pedido(db, c.app.state.cfg, t, res) == 4
    por_conta = db.todos("SELECT conta, k, quando FROM posts ORDER BY conta, quando")
    assert [x["k"] for x in por_conta[:2]] == [2, 1]  # o de nota maior primeiro
    assert abs(por_conta[1]["quando"] - por_conta[0]["quando"] - 86400) < 1  # 1 por dia
    assert cacador.agendar_posts_do_pedido(db, c.app.state.cfg, t, res) == 0  # não duplica


def test_cacador_varios_posts_por_dia_e_limite_do_plano(cli):
    c, db = cli
    from app import cacador, fila
    _conta(c)
    db.exec("UPDATE usuarios SET plano='piloto', ativo_ate=?", (time.time() + 9999,))
    assert c.post("/api/cacador", json={"temas": ["x"], "posts_dia": 9}).json()["posts_dia"] == 5  # Piloto: até 5
    db.exec("UPDATE usuarios SET plano='viral', adicionais=?", (json.dumps({"cacador": time.time() + 9999}),))
    assert c.post("/api/cacador", json={"temas": ["x"], "posts_dia": 5}).json()["posts_dia"] == 2  # adicional: até 2
    now = time.time()
    db.exec("INSERT INTO contas(usuario,rede,estado,criado,atualizado) VALUES(1,'tiktok','conectada',?,?)", (now, now))
    pasta = fila.pasta_trabalho(c.app.state.cfg, "D1"); pasta.mkdir(parents=True)
    for k in (1, 2):
        (pasta / f"corte{k}.mp4").write_bytes(b"0" * 1000)
    res = {"cortes": [{"k": 1, "estado": "pronto", "arquivo": "corte1.mp4", "nota": 80}, {"k": 2, "estado": "pronto", "arquivo": "corte2.mp4", "nota": 90},
                      {"k": 3, "estado": "erro"}]}
    t = {"id": "D1", "usuario": 1, "entrada": json.dumps({"postar_auto": True, "hora_post": "08:00", "posts_dia": 3})}
    assert cacador.agendar_posts_do_pedido(db, c.app.state.cfg, t, res) == 2  # pediu 3 por dia, o vídeo rendeu 2: posta 2
    q = [x["quando"] for x in db.todos("SELECT quando FROM posts ORDER BY quando")]
    assert len(q) == 2 and 3000 < q[1] - q[0] < 86400  # no mesmo dia, espaçados (não 1 por dia)


def test_landing_fael_conta_adriano(tmp_path):
    """Spec 57 §4.4: a landing do Fael vende pela conta Cakto do Adriano (preços próprios, só planos) e o webhook aceita os dois segredos."""
    from fastapi.testclient import TestClient
    from app.config import Config
    from app.main import criar_app
    cfg = Config(dados=str(tmp_path), dev=True, cakto_segredo="seg-lucas", cakto_segredo_fael="seg-adriano",
                 planos_por_produto={"p-corte": "corte", "a-viral": "viral"}, checkouts={"corte": "https://pay.cakto.com.br/lucas"},
                 checkouts_fael={"corte": "https://pay.cakto.com.br/adri-corte", "viral": "https://pay.cakto.com.br/adri-viral"})
    c = TestClient(criar_app(cfg, iniciar_fila=False))
    nosso = c.get("/api/planos").json()
    assert nosso["planos"][0]["checkout"].endswith("/lucas") and nosso["moedas"]
    fael = c.get("/api/planos", headers={"host": "viralizai.fael.rangeltech.net"}).json()
    precos = {p["codigo"]: p["preco"] for p in fael["planos"]}
    assert precos == {"corte": 29.90, "animacao": 49.90, "viral": 99.90, "piloto": 119.90}
    assert fael["planos"][0]["checkout"].endswith("/adri-corte") and "lancamento" not in fael["planos"][0]
    assert fael["moedas"] == [] and fael["adicionais"] == []
    ev = {"secret": "seg-adriano", "event": "purchase_approved", "data": {"id": "a1", "customer": {"email": "fa@t.com"}, "product": {"id": "a-viral"}}}
    assert c.post("/api/cakto", json=ev).json()["plano"] == "viral"
    ev2 = {**ev, "secret": "seg-lucas", "data": {**ev["data"], "id": "l1", "product": {"id": "p-corte"}}}
    assert c.post("/api/cakto", json=ev2).json()["plano"] == "corte"
    assert c.post("/api/cakto", json={**ev, "secret": "outro", "data": {**ev["data"], "id": "x"}}).status_code == 401
    assert "19,90" not in c.get("/", headers={"host": "viralizai.fael.rangeltech.net"}).text
