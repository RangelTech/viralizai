FROM python:3.12-slim
# ffmpeg (montagem), deno (yt-dlp lê o YouTube), Node 22 + bibliotecas do Chrome headless (moldes de animação Remotion)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip gnupg \
      libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
      libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 fonts-noto-color-emoji \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y --no-install-recommends nodejs \
 && curl -fsSL -o /tmp/deno.zip https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
 && unzip -q /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip && deno --version \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --create-home --home-dir /home/app app && mkdir /data && chown 10001:10001 /data
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY motion/package.json motion/package-lock.json ./motion/
RUN cd motion && npm ci --no-audit --no-fund && chown -R 10001:10001 /srv/motion
COPY --chown=10001:10001 motion ./motion
USER 10001
# Chrome headless do Remotion baixado no build (não na 1ª animação do cliente)
RUN cd motion && npx remotion browser ensure
USER root
COPY app ./app
COPY static ./static
COPY skills ./skills
ARG GIT_COMMIT=dev
ENV GIT_COMMIT=${GIT_COMMIT} PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 VIRALIZAI_DADOS=/data DENO_DIR=/tmp/deno XDG_CACHE_HOME=/tmp/cache \
    HOME=/home/app VIRALIZAI_MODELOS=/data/modelos
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
