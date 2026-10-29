import os
import json
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    """Open a connection to Postgres.
    Rows come back as dict-like objects instead of tuples."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL PRIMARY KEY,
            google_id   TEXT UNIQUE NOT NULL,
            email       TEXT NOT NULL,
            name        TEXT,
            picture     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            name         TEXT NOT NULL,
            source_url   TEXT,
            servings     TEXT,
            prep_time    TEXT,
            cook_time    TEXT,
            ingredients  TEXT NOT NULL,
            instructions TEXT NOT NULL,
            image_url    TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


def get_user_by_google_id(google_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def create_user(google_id, email, name, picture):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users (google_id, email, name, picture)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (google_id, email, name, picture),
    )
    user_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return user_id


def create_recipe(user_id, recipe):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO recipes
           (user_id, name, source_url, servings, prep_time, cook_time,
            ingredients, instructions, image_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
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
    recipe_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return recipe_id


def get_recipes_for_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM recipes
           WHERE user_id = %s
           ORDER BY created_at DESC, id DESC""",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_deserialize_recipe(dict(row)) for row in rows]


def get_recipe(recipe_id, user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM recipes WHERE id = %s AND user_id = %s",
        (recipe_id, user_id),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _deserialize_recipe(dict(row)) if row else None


def _deserialize_recipe(row):
    row["ingredients"] = json.loads(row["ingredients"])
    row["instructions"] = json.loads(row["instructions"])
    return row

