# db.py — Simple SQLite wrapper for Lyra Framework
import sqlite3
import os
import logging

DB_PATH = "lyra.db"

def get_db():
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create the messages table if it doesn't exist."""
    if os.path.exists(DB_PATH):
        logging.info("SQLite database already exists.")
        return

    try:
        with get_db() as conn:
            conn.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,          -- 'user' or 'assistant'
                    content TEXT NOT NULL,
                    actions TEXT,                -- future use
                    internal_dialogue TEXT,      -- future use
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logging.info(f"SQLite database created: {DB_PATH}")
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")

# Initialize on import
init_db()