# Small Python image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl git tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps
COPY click-cartel-discord-bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy src
COPY click-cartel-discord-bot /app/click-cartel-discord-bot

# Run as non-root
RUN useradd -m -u 10001 appuser
USER appuser

CMD ["python", "/app/click-cartel-discord-bot/src/bot.py"]