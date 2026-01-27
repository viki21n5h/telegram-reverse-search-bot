import sqlite3

conn = sqlite3.connect("media.db")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS media (
    hash TEXT,
    link TEXT
)
""")

conn.commit()
conn.close()
print("Database ready")
