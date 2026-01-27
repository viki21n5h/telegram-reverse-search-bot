import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

import asyncio
import os
import sqlite3
import cv2
import numpy as np
import torch
import clip
from PIL import Image
from dotenv import load_dotenv
from telethon import TelegramClient

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
FRAMES_DIR = "temp_files/frames"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# ================= CLIP MODEL =================
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🤖 Using device: {device}")
model, preprocess = clip.load("ViT-B/32", device=device)

# ================= DB =================
conn = sqlite3.connect("video_search.db", check_same_thread=False)
c = conn.cursor()

# Schema: videos + keyframes with embedded CLIP vectors
c.execute("""
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT UNIQUE,
    channel TEXT,
    message_id INTEGER,
    video_url TEXT,
    duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS keyframes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT,
    frame_index INTEGER,
    timestamp REAL,
    image_path TEXT,
    embedding BLOB,
    FOREIGN KEY(video_id) REFERENCES videos(video_id)
)
""")

c.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON keyframes(video_id)")
c.execute("CREATE INDEX IF NOT EXISTS idx_frame_index ON keyframes(frame_index)")

conn.commit()

# ================= TELETHON =================
client = TelegramClient("user_session", API_ID, API_HASH)

total_bytes = 0
total_embeddings = 0


def encode_image(image_path):
    """Encode a single image to CLIP embedding"""
    try:
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            emb = model.encode_image(image)
        return emb.cpu().numpy()[0]
    except Exception as e:
        print(f"❌ Encoding error: {e}")
        return None


def extract_keyframes(video_path, out_dir=None, max_frames=20):
    """Extract ~20 keyframes from video using OpenCV"""
    if out_dir is None:
        out_dir = FRAMES_DIR
    
    os.makedirs(out_dir, exist_ok=True)
    
    try:
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total == 0:
            print(f"⚠️ Video has 0 frames: {video_path}")
            cap.release()
            return []
        
        step = max(1, total // max_frames)
        frames = []
        i = 0
        saved = 0
        
        while cap.isOpened() and saved < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            if i % step == 0:
                path = f"{out_dir}/frame_{saved}.jpg"
                cv2.imwrite(path, frame)
                frames.append(path)
                saved += 1
            i += 1
        
        cap.release()
        print(f"✅ Extracted {saved} keyframes from video")
        return frames
    except Exception as e:
        print(f"❌ Keyframe extraction error: {e}")
        return []


async def process_image(file_path, link, channel):
    """Process single image: encode to CLIP embedding and store in DB"""
    global total_bytes, total_embeddings
    try:
        emb = encode_image(file_path)
        if emb is None:
            return
        
        # Convert embedding to bytes
        embedding_bytes = emb.tobytes()
        
        # Insert into videos table
        video_id = f"image_{hash(link) % 10**9}"
        c.execute(
            "INSERT OR IGNORE INTO videos (video_id, channel, message_id, video_url) VALUES (?, ?, ?, ?)",
            (video_id, channel, None, link)
        )
        
        # Insert into keyframes table
        c.execute(
            "INSERT INTO keyframes (video_id, frame_index, timestamp, image_path, embedding) VALUES (?, ?, ?, ?, ?)",
            (video_id, 0, 0.0, file_path, embedding_bytes)
        )
        conn.commit()
        total_embeddings += 1
        print(f"✅ Image processed: {link}")
    except Exception as e:
        print(f"❌ Image processing error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


async def process_video(file_path, link, channel):
    """Process video: extract keyframes, encode each, store in DB"""
    global total_bytes, total_embeddings
    try:
        frames = extract_keyframes(file_path)
        
        if not frames:
            print(f"⚠️ No frames extracted from video: {link}")
            return
        
        # Create unique video_id
        video_id = f"video_{hash(link) % 10**9}"
        
        # Insert into videos table
        c.execute(
            "INSERT OR IGNORE INTO videos (video_id, channel, message_id, video_url) VALUES (?, ?, ?, ?)",
            (video_id, channel, None, link)
        )
        
        # Process each keyframe
        for frame_num, frame_path in enumerate(frames):
            emb = encode_image(frame_path)
            if emb is None:
                continue
            
            # Convert embedding to bytes
            embedding_bytes = emb.tobytes()
            
            # Calculate timestamp (rough estimate based on frame number)
            timestamp = frame_num * (1.0 / len(frames))
            
            # Insert into keyframes table
            c.execute(
                "INSERT INTO keyframes (video_id, frame_index, timestamp, image_path, embedding) VALUES (?, ?, ?, ?, ?)",
                (video_id, frame_num, timestamp, frame_path, embedding_bytes)
            )
            total_embeddings += 1
        
        conn.commit()
        print(f"✅ Video processed: {link} ({len(frames)} keyframes)")
        
        # Cleanup frames
        for frame_path in frames:
            if os.path.exists(frame_path):
                os.remove(frame_path)
    
    except Exception as e:
        print(f"❌ Video processing error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


async def main():
    global total_bytes, total_embeddings
    await client.start()
    print("✅ Logged in")

    for channel in CHANNELS:
        print(f"📥 Scraping channel: {channel}")

        async for msg in client.iter_messages(channel, limit=500):

            if total_bytes >= MAX_BYTES:
                print("🛑 Reached 200MB limit. Stopping scrape.")
                break

            try:
                # ---------- PHOTO ----------
                if msg.photo:
                    file = await msg.download_media(file=DOWNLOAD_DIR)
                    size = os.path.getsize(file)
                    total_bytes += size

                    link = f"https://t.me/{channel}/{msg.id}"
                    await process_image(file, link, channel)

                # ---------- VIDEO ----------
                elif msg.video:
                    file = await msg.download_media(file=DOWNLOAD_DIR)
                    size = os.path.getsize(file)
                    total_bytes += size

                    link = f"https://t.me/{channel}/{msg.id}"
                    await process_video(file, link, channel)

            except Exception as e:
                print(f"⚠️ Skip error: {e}")

        print(f"✅ Finished channel: {channel}")

    # Save FAISS index (deprecated - embeddings now in DB)
    # faiss.write_index(index, "video.index")

    await client.disconnect()
    conn.close()
    print(f"🎉 Scraping complete. Total embeddings: {total_embeddings}")


asyncio.run(main())