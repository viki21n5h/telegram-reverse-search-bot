import os
import glob
import sqlite3
import subprocess
import imagehash
from PIL import Image
from dotenv import load_dotenv

from telegram.ext import ApplicationBuilder, MessageHandler, filters, CommandHandler
from telegram.constants import ChatAction

# ========== LOAD TOKEN ==========
load_dotenv("details.env")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("❌ BOT_TOKEN not found in details.env")
    exit(1)

print("✅ BOT TOKEN loaded")

# ========== DATABASE ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "media.db")

print("Using DB:", DB_PATH)

conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
c = conn.cursor()

# Check DB content
c.execute("SELECT COUNT(*) FROM media")
count = c.fetchone()[0]
print("📦 Total records in DB:", count)

# ========== COMMANDS ==========

async def start(update, context):
    print("👉 /start received")
    await update.message.reply_text(
        "Send me a photo or a video screenshot and I will try to find it in public Telegram channels."
    )

# ========== PHOTO HANDLER ==========

async def handle_photo(update, context):
    print("📷 Photo received")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    msg_id = update.message.message_id
    photo_file = f"query_{msg_id}.jpg"

    photo = await update.message.photo[-1].get_file()
    await photo.download_to_drive(photo_file)

    qhash = imagehash.phash(Image.open(photo_file).convert("RGB"))

    c.execute("SELECT hash, link FROM media")
    results = c.fetchall()

    print("🔍 Comparing against", len(results), "records")

    matches = []
    for h, link in results:
        if qhash - imagehash.hex_to_hash(h) < 10:
            matches.append(link)

    if matches:
        await update.message.reply_text(
            "✅ Matches found:\n" + "\n".join(matches[:5])
        )
    else:
        await update.message.reply_text("❌ No match found.")

    if os.path.exists(photo_file):
        os.remove(photo_file)

# ========== ERROR HANDLER ==========

async def error_handler(update, context):
    print("❌ Error:", context.error)

# ========== APP ==========

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_error_handler(error_handler)

print("🤖 Bot is running...")
app.run_polling()
