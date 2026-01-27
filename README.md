### Telegram Image Search Bot

A Python-based Telegram bot that scrapes images from specified public Telegram channels, builds an image fingerprint database, and allows users to upload an image to find visually similar content.
When a match is found, the bot returns the direct link to the original Telegram message containing the image.

This project demonstrates how to build a small-scale image search engine for Telegram using perceptual hashing and public channel scraping.

### How It Works

-A scraper logs in using a Telegram user account and downloads images from selected public channels.
-Each image is converted into a perceptual hash and stored in a SQLite database with its Telegram message link.
-A Telegram bot receives an image from the user.
-The bot computes the hash of the uploaded image and compares it with the stored hashes.
-If a similar image is found, the bot replies with the original Telegram post link.

![telegram-cloud-photo-size-5-6323406747506249423-y](https://github.com/user-attachments/assets/e62db481-7415-4677-a576-11cf32f06357)


### Installation

1. Clone the repository
2. Create virtual environment
3. Install dependencies
4. Install FFmpeg
5. Environment Setup

  Create a file named details.env:

BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
API_ID=YOUR_TELEGRAM_API_ID
API_HASH=YOUR_TELEGRAM_API_HASH

  Configure Scraper

Edit scraper.py and set channels:

CHANNELS = ["memes", "wallpapers", "photography"]

6. Run scraper:

python scraper.py

7. run bot

   python bot.py
   
9. start your ot in telegram and upload your photo.


