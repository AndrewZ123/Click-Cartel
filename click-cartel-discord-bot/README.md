# Click-Cartel Discord Bot

Click-Cartel is a Discord bot designed to scrape real-time paid research and focus group listings from various websites. The bot posts these listings to a review channel for admin approval and subsequently publishes approved listings to public channels.

## Features

- Real-time scraping of listings from multiple websites.
- Admin approval workflow for new listings.
- Posting of approved listings to designated public channels.
- Modular architecture with separate components for scraping, database interaction, and notification handling.

## Project Structure

```
click-cartel-discord-bot
├── src
│   ├── bot.py               # Main entry point for the Discord bot
│   ├── config.py            # Configuration settings and environment variable loading
│   ├── cogs
│   │   ├── admin.py         # Admin-related commands
│   │   └── listings.py      # Commands for scraping and managing listings
│   ├── scrapers
│   │   ├── __init__.py      # Initializes the scrapers package
│   │   ├── base.py          # Base class for all scrapers
│   │   ├── site_a.py        # Scraper for UserInterviews.com
│   │   └── site_b.py        # Scraper for Respondent.io
│   ├── services
│   │   ├── db.py            # Database interaction functions
│   │   ├── notifier.py       # Notification handling for Discord
│   │   └── scheduler.py      # Scheduling of scraping tasks
│   ├── models
│   │   └── listing.py        # Listing model definition
│   └── utils
│       ├── http.py          # HTTP utility functions
│       └── parser.py        # HTML parsing functions
├── tests
│   ├── test_scrapers.py      # Unit tests for scrapers
│   └── test_cogs.py          # Unit tests for bot cogs
├── scripts
│   └── run.sh                # Shell script to run the bot
├── .env.example               # Example environment variables
├── .gitignore                 # Git ignore file
├── requirements.txt           # Project dependencies
├── pyproject.toml            # Project metadata and configuration
├── Dockerfile                 # Docker image instructions
└── README.md                  # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd click-cartel-discord-bot
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your environment variables by copying `.env.example` to `.env` and filling in the required values.

## Usage

To run the bot, execute the following command:
```
bash scripts/run.sh
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.