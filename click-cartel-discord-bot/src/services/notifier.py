from discord import Webhook, RequestsWebhookAdapter
import logging

class Notifier:
    def __init__(self, webhook_url):
        self.webhook = Webhook.from_url(webhook_url, adapter=RequestsWebhookAdapter())
        logging.basicConfig(level=logging.INFO)

    def send_listing_notification(self, listing):
        try:
            message = f"New Listing:\nTitle: {listing.title}\nPayout: {listing.payout}\nLink: {listing.link}\nDate Posted: {listing.date_posted}"
            self.webhook.send(message)
            logging.info("Notification sent for listing: %s", listing.title)
        except Exception as e:
            logging.error("Failed to send notification: %s", e)

    def log_error(self, error_message):
        logging.error("Error: %s", error_message)