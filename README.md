# Viralizaí

App da Rangel Tech para ganhar dinheiro com vídeo curto (spec 47 em `new_ragente/specs/47*`):

- **Cortar live ou vídeo** — motor em `app/motor/`: sinais sem baixar o vídeo (legenda json3, chat, "mais repetidos",
  comentários com tempo, áudio com YAMNet em CPU), candidatos com a história inteira, 1 juiz de IA, trecho baixado por
  índice DASH (segundos, não minutos). Cache absoluto por vídeo = vitrine "Prontos pra postar".
- **Criar animação** — moldes feitos à mão em `motion/` (Remotion); a IA só preenche um JSON validado (`app/animacao_v2.py`).
- **Vídeo com IA** — moedas, prévia grátis em imagem, gerado pelo Estúdio do llm-access (`app/video_ia.py`).
- **Editar meu vídeo** — legenda automática (Whisper em CPU), gancho, @, velocidade, esticar pra 1 min (`app/editor.py`).
- Fila justa (`app/fila.py`): todo mundo recebe o 1º corte antes de alguém receber o 3º.

Teste local: `VIRALIZAI_DEV=1 VIRALIZAI_DADOS=./dados_local uvicorn app.main:app` e `python -m pytest -q`.
Deploy: somente pelo `RangelTech/vps_rt_infra` (stack `viralizai`). Release: workflow `Release` com a versão.
Segredos: `/opt/platform/secrets/viralizai.env` na VPS (cofre: `personal-skills/secrets/viralizai.env`).
