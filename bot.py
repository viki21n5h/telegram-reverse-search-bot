import os
import sqlite3
import numpy as np
import torch
import clip
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

# ========== CLIP MODEL ==========
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🤖 Using device: {device}")
model, preprocess = clip.load("ViT-B/32", device=device)

# ========== DATABASE ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "video_search.db")

print("Using DB:", DB_PATH)

conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
c = conn.cursor()

# Check DB content
c.execute("SELECT COUNT(*) FROM videos")
count = c.fetchone()[0]
print("📦 Total videos in DB:", count)


# ========== HELPER FUNCTIONS ==========

def encode_image(image_path):
    """Encode image to CLIP embedding"""
    try:
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            emb = model.encode_image(image)
        return emb.cpu().numpy()[0]
    except Exception as e:
        print(f"❌ Encoding error: {e}")
        return None


def search_database(query_emb, top_k=10):
    """Search database for similar embeddings using cosine similarity"""
    c.execute("SELECT id, embedding FROM keyframes")
    rows = c.fetchall()
    
    if not rows:
        return [], []
    
    # Load all embeddings from DB and compute similarities
    similarities = []
    for row_id, emb_bytes in rows:
        stored_emb = np.frombuffer(emb_bytes, dtype=np.float32)
        # Cosine similarity
        sim = np.dot(query_emb, stored_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(stored_emb) + 1e-8)
        similarities.append((row_id, sim))
    
    # Sort by similarity (descending) and get top_k
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_results = similarities[:top_k]
    
    indices = np.array([row_id for row_id, _ in top_results])
    distances = np.array([1 - sim for _, sim in top_results])  # Convert to distance
    
    return distances, indices


def rank_results(distances, indices):
    """Group results by video link and rank by best similarity"""
    if len(indices) == 0:
        return []
    
    # Fetch metadata from DB
    link_scores = {}
    for dist, idx in zip(distances, indices):
        c.execute("""
            SELECT v.video_url FROM keyframes k
            JOIN videos v ON k.video_id = v.video_id
            WHERE k.id = ?
        """, (int(idx),))
        result = c.fetchone()
        
        if result:
            link = result[0]
            score = 1 / (1 + dist)  # Convert distance to similarity
            
            if link not in link_scores:
                link_scores[link] = []
            link_scores[link].append(score)
    
    # Average scores per link
    ranked = {}
    for link, scores in link_scores.items():
        avg_score = np.mean(scores)
        ranked[link] = avg_score
    
    # Sort by score (descending)
    sorted_links = sorted(ranked.items(), key=lambda x: x[1], reverse=True)
    return [link for link, score in sorted_links]

# ========== COMMANDS ==========

async def start(update, context):
    print("👉 /start received")
    await update.message.reply_text(
        "Send me a photo or a video screenshot and I will try to find it in public Telegram channels."
    )

# ========== PHOTO HANDLER ==========

async def handle_photo(update, context):
    print("📷 Photo received")

    # Check if DB has embeddings
    c.execute("SELECT COUNT(*) FROM keyframes")
    count = c.fetchone()[0]
    
    if count == 0:
        await update.message.reply_text("❌ No embeddings indexed yet. Run scraper.py first.")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    msg_id = update.message.message_id
    photo_file = f"query_{msg_id}.jpg"

    try:
        photo = await update.message.photo[-1].get_file()
        await photo.download_to_drive(photo_file)

        # Encode query image
        query_emb = encode_image(photo_file)
        if query_emb is None:
            await update.message.reply_text("❌ Error processing image.")
            return

        # Search database
        distances, indices = search_database(query_emb, top_k=10)
        
        # Rank by link and get top 3
        ranked_links = rank_results(distances, indices)
        top_links = ranked_links[:3]

        if top_links:
            await update.message.reply_text(
                "✅ Top matches found:\n" + "\n".join(f"🔗 {link}" for link in top_links)
            )
        else:
            await update.message.reply_text("❌ No matches found.")

    except Exception as e:
        print(f"❌ Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
    
    finally:
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
