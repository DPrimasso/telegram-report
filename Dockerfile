# Immagine per il bot a comandi su Render. Non un buildpack (env: python):
# quello esegue la build come utente non privilegiato, e "playwright
# install --with-deps" ha bisogno di apt-get per le librerie di sistema di
# Chromium, permesso solo da root. Una build Docker parte gia' da root, e
# risolve il problema alla radice invece di aggirarlo.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

CMD ["python", "-m", "bot.app"]
