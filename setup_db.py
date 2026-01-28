import sqlite3

DB_NAME = "video_search.db"

def setup_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Videos table
    cursor.execute("""
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

    # Keyframes table (thumbnails + embeddings)
    cursor.execute("""
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

    # Indexes for faster search
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON keyframes(video_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_frame_index ON keyframes(frame_index)")

    conn.commit()
    conn.close()
    print("✅ Database schema created successfully")

if __name__ == "__main__":
    setup_database()
