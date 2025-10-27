#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Install required packages
pip install -r requirements.txt

# Run the Discord bot
python3 src/bot.py