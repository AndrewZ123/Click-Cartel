import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
REVIEW_CHANNEL_ID = os.getenv("REVIEW_CHANNEL_ID")
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID")