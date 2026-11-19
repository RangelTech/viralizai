"""Prévia rápida de um filme do motor cinema: monta a página (motor + shots), roda renderFrame em tempos escolhidos e salva uma folha.
Uso: python previa.py <shots.js> <saida_dir> [tempos=1,3,5] [palavras.json]
Também serve de validador: imprime ERRO_CENA se algum plano lançar exceção."""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORDEM = ["lib.js", "chars.js", "env.js", "cenarios.js", "props.js", "alto.js"]


def codigo_filme(shots_js: str) -> str:
    """Motor + roteiro + compositor num script só (o mesmo que vai para o Remotion)."""
    partes = [(AQUI / f).read_text(encoding="utf-8") for f in ORDEM]
    return "\n;\n".join(partes + [shots_js, (AQUI / "main.js").read_text(encoding="utf-8")])


def pagina(shots_js: str, palavras: list[dict], imagens: dict[str, str] | None = None) -> str:
    fonte = (AQUI / "fonts" / "Poppins-Bold.ttf").as_uri()
    imgs = json.dumps(imagens or {})
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>@font-face{{font-family:Poppins;font-weight:700;src:url({fonte})}}body{{margin:0;background:#000}}</style></head>
<body><canvas id="c" width="540" height="960"></canvas><script>
const WORDS = {json.dumps(palavras)}; const OPCOES = {{legenda: true}}; const IMG = {{}};
for (const [k, u] of Object.entries({imgs})) {{ const im = new Image(); im.src = u; IMG[k] = im; }}
{codigo_filme(shots_js)}
window.FILME = montar(document.getElementById('c'));
</script></body></html>"""


def previa(shots_js: str, saida: Path, tempos: list[float], palavras: list[dict] | None = None, imagens: dict | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    from PIL import Image
    saida.mkdir(parents=True, exist_ok=True)
    html = saida / "previa.html"
    html.write_text(pagina(shots_js, palavras or [], imagens), encoding="utf-8")
    erros: list[str] = []
    ims = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--allow-file-access-from-files"])
        pg = b.new_page(viewport={"width": 540, "height": 960})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(html.as_uri()); pg.wait_for_timeout(800)
        if erros:
            b.close()
            return {"ok": False, "erros": erros}
        pg.evaluate("document.fonts.load('700 40px Poppins')")
        t0 = time.time()
        for t in tempos:
            d = pg.evaluate("f => { FILME.renderFrame(f); return document.getElementById('c').toDataURL('image/jpeg', .85); }", round(t * 30))
            f = saida / f"q_{t:05.2f}.jpg"; f.write_bytes(base64.b64decode(d.split(",")[1])); ims.append(Image.open(f))
        ms = (time.time() - t0) / max(1, len(tempos)) * 1000
        erro_cena = pg.evaluate("window.__ERRO_CENA || ''")
        dur = pg.evaluate("FILME.DUR")
        b.close()
    if erro_cena:
        erros.append(erro_cena)
    w, h = 270, 480
    folha = Image.new("RGB", (w * len(ims), h))
    for i, im in enumerate(ims):
        folha.paste(im.resize((w, h)), (i * w, 0))
    folha.save(saida / "folha.jpg", quality=85)
    return {"ok": not erros, "erros": erros, "ms_quadro": round(ms), "dur": dur, "folha": str(saida / "folha.jpg")}


if __name__ == "__main__":
    shots = Path(sys.argv[1]).read_text(encoding="utf-8")
    tempos = [float(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "1,3,5").split(",")]
    pal = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")) if len(sys.argv) > 4 else []
    print(json.dumps(previa(shots, Path(sys.argv[2]), tempos, pal), ensure_ascii=False))
