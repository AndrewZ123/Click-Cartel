# Small Python image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates curl git tzdata \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -u 10001 appuser
WORKDIR /app

# Copy requirements and install
COPY click-cartel-discord-bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY click-cartel-discord-bot /app/click-cartel-discord-bot

# Run as non-root
USER appuser

# Launch
CMD ["python", "/app/click-cartel-discord-bot/src/bot.py"]