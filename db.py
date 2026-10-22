import sqlite3
import os
import json

DB_PATH = os.getenv("DATABASE_PATH", "recipes.db")


def get_connection():
    """Open a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    # makes the results from a tuple to a special row, allowing me to select by key, as opposed to only index.
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
                       
        CREATE TABLE IF NOT EXISTS recipes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            name         TEXT NOT NULL,
            source_url   TEXT,
            servings     TEXT,
            prep_time    TEXT,
            cook_time    TEXT,
            ingredients  TEXT NOT NULL,
            instructions TEXT NOT NULL,
            image_url    TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
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

def create_recipe(user_id, recipe):
    """Insert a new recipe. `recipe` is a dict with name, ingredients (list), etc."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO recipes
           (user_id, name, source_url, servings, prep_time, cook_time,
            ingredients, instructions, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            recipe["name"],
            recipe.get("source_url", ""),
            recipe.get("servings", ""),
            recipe.get("prep_time", ""),
            recipe.get("cook_time", ""),
            json.dumps(recipe["ingredients"]),
            json.dumps(recipe["instructions"]),
            recipe.get("image_url", ""),
        ),
    )
    conn.commit()
    recipe_id = cur.lastrowid
    conn.close()
    return recipe_id

def get_recipes_for_user(user_id):
    """Return all recipes for a user, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM recipes
           WHERE user_id = ?
           ORDER BY created_at DESC, id DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [_deserialize_recipe(dict(row)) for row in rows]


def get_recipe(recipe_id, user_id):
    """Return one recipe by ID, only if it belongs to this user."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM recipes WHERE id = ? AND user_id = ?",
        (recipe_id, user_id),
    ).fetchone()
    conn.close()
    return _deserialize_recipe(dict(row)) if row else None


def _deserialize_recipe(row):
    """Turn JSON-encoded fields back into Python lists."""
    row["ingredients"] = json.loads(row["ingredients"])
    row["instructions"] = json.loads(row["instructions"])
    return row