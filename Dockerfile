# Small Python image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Make the "src" package importable
    PYTHONPATH=/app/click-cartel-discord-bot

# System deps (certs, runtime)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 10001 appuser
WORKDIR /app

# Copy requirements and install
COPY click-cartel-discord-bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY click-cartel-discord-bot /app/click-cartel-discord-bot

# Data dir for sqlite (mounted as a volume)
RUN mkdir -p /data && chown -R appuser:appuser /data /app
USER appuser

# Start the bot
CMD ["python", "/app/click-cartel-discord-bot/src/bot.py"]