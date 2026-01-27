import asyncio
import os
import sqlite3
from telethon import TelegramClient
from PIL import Image
import imagehash
from dotenv import load_dotenv

# ================= LOAD ENV =================
load_dotenv("details.env")

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    print("❌ API_ID or API_HASH missing")
    exit(1)

# ================= SETTINGS =================
CHANNELS = ["meme"]  # add more later
MAX_MB = 200
MAX_BYTES = MAX_MB * 1024 * 1024

DOWNLOAD_DIR = "tmp_media"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= DB =================
conn = sqlite3.connect("media.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS media (
    hash TEXT,
    link TEXT UNIQUE
)
""")

# ================= TELETHON =================
client = TelegramClient("user_session", API_ID, API_HASH)

total_bytes = 0


async def process_image(file_path, link):
    global total_bytes
    try:
        img = Image.open(file_path).convert("RGB")
        h = str(imagehash.phash(img))
        c.execute("INSERT OR IGNORE INTO media VALUES (?,?)", (h, link))
        conn.commit()
    except Exception as e:
        print("❌ Image error:", e)
    finally:
        os.remove(file_path)


async def main():
    global total_bytes
    await client.start()
    print("✅ Logged in")

    for channel in CHANNELS:
        print(f"📥 Scraping channel: {channel}")

        async for msg in client.iter_messages(channel, limit=500):

            if total_bytes >= MAX_BYTES:
                print("🛑 Reached 200MB limit. Stopping scrape.")
                await client.disconnect()
                conn.close()
                return

            try:
                # ---------- PHOTO ----------
                if msg.photo:
                    file = await msg.download_media(file=DOWNLOAD_DIR)
                    size = os.path.getsize(file)
                    total_bytes += size

                    link = f"https://t.me/{channel}/{msg.id}"
                    await process_image(file, link)

            except Exception as e:
                print("⚠️ Skip error:", e)

        print(f"✅ Finished channel: {channel}")

    await client.disconnect()
    conn.close()
    print("🎉 Scraping complete")


asyncio.run(main())