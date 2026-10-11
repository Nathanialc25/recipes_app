import sqlite3
import os

DB_PATH = os.getenv("DATABASE_PATH", "recipes.db")


def get_connection():
    """Open a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    # makes the rows return as dicts so we can access them via values
    conn.row_factory = sqlite3.Row  
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id   TEXT UNIQUE NOT NULL,
            email       TEXT NOT NULL,
            name        TEXT,
            picture     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def get_user_by_google_id(google_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(google_id, email, name, picture):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO users (google_id, email, name, picture)
           VALUES (?, ?, ?, ?)""",
        (google_id, email, name, picture),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id