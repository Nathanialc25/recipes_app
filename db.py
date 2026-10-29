import os
import json
import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Global connection pool. Created once at import time.
# min=1, max=4: keeps 1-4 connections alive per Cloud Run container.
_connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 4,
    DATABASE_URL,
    cursor_factory=psycopg2.extras.RealDictCursor,
)


def get_connection():
    """Borrow a connection from the pool."""
    return _connection_pool.getconn()


def release_connection(conn):
    """Return a connection to the pool."""
    _connection_pool.putconn(conn)


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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS friendships (
        id          SERIAL PRIMARY KEY,
        requester_id INTEGER NOT NULL REFERENCES users(id),
        addressee_id INTEGER NOT NULL REFERENCES users(id),
        status      TEXT NOT NULL DEFAULT 'pending',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(requester_id, addressee_id),
        CHECK (requester_id <> addressee_id)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shared_recipes (
        id                SERIAL PRIMARY KEY,
        recipient_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sender_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name              TEXT NOT NULL,
        source_url        TEXT,
        servings          TEXT,
        prep_time         TEXT,
        cook_time         TEXT,
        ingredients       TEXT NOT NULL,
        instructions      TEXT NOT NULL,
        image_url         TEXT,
        shared_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    cur.close()
    release_connection(conn)


def get_user_by_google_id(google_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
    row = cur.fetchone()
    cur.close()
    release_connection(conn)
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
    release_connection(conn)
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
    release_connection(conn)
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
    release_connection(conn)
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
    release_connection(conn)
    return _deserialize_recipe(dict(row)) if row else None


def _deserialize_recipe(row):
    row["ingredients"] = json.loads(row["ingredients"])
    row["instructions"] = json.loads(row["instructions"])
    return row


def get_user_by_email(email):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
    row = cur.fetchone()
    cur.close()
    release_connection(conn)
    return dict(row) if row else None


def create_friend_request(requester_id, addressee_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO friendships (requester_id, addressee_id, status)
           VALUES (%s, %s, 'pending') RETURNING id""",
        (requester_id, addressee_id),
    )
    fid = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    release_connection(conn)
    return fid


def accept_friend_request(friendship_id, addressee_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE friendships SET status = 'accepted'
           WHERE id = %s AND addressee_id = %s AND status = 'pending'""",
        (friendship_id, addressee_id),
    )
    conn.commit()
    changed = cur.rowcount
    cur.close()
    release_connection(conn)
    return changed > 0


def decline_friend_request(friendship_id, addressee_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """DELETE FROM friendships
           WHERE id = %s AND addressee_id = %s AND status = 'pending'""",
        (friendship_id, addressee_id),
    )
    conn.commit()
    changed = cur.rowcount
    cur.close()
    release_connection(conn)
    return changed > 0


def get_friendship_between(user_a, user_b):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM friendships
           WHERE (requester_id = %s AND addressee_id = %s)
              OR (requester_id = %s AND addressee_id = %s)""",
        (user_a, user_b, user_b, user_a),
    )
    row = cur.fetchone()
    cur.close()
    release_connection(conn)
    return dict(row) if row else None


def get_pending_requests_for(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT f.id, f.created_at, u.name, u.email, u.id AS requester_id
           FROM friendships f
           JOIN users u ON u.id = f.requester_id
           WHERE f.addressee_id = %s AND f.status = 'pending'
           ORDER BY f.created_at DESC""",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    release_connection(conn)
    return [dict(r) for r in rows]


def get_friends_for(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT u.id, u.name, u.email
           FROM friendships f
           JOIN users u ON u.id = CASE
             WHEN f.requester_id = %s THEN f.addressee_id
             ELSE f.requester_id
           END
           WHERE f.status = 'accepted'
             AND (f.requester_id = %s OR f.addressee_id = %s)
           ORDER BY u.name""",
        (user_id, user_id, user_id),
    )
    rows = cur.fetchall()
    cur.close()
    release_connection(conn)
    return [dict(r) for r in rows]


def send_shared_recipe(recipient_id, sender_id, recipe):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO shared_recipes
           (recipient_id, sender_id, name, source_url, servings, prep_time,
            cook_time, ingredients, instructions, image_url)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            recipient_id,
            sender_id,
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
    cur.close()
    release_connection(conn)


def get_inbox_for_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT sr.*, u.name AS sender_name, u.email AS sender_email
           FROM shared_recipes sr
           JOIN users u ON u.id = sr.sender_id
           WHERE sr.recipient_id = %s
           ORDER BY sr.shared_at DESC""",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    release_connection(conn)
    return [_deserialize_shared_recipe(dict(r)) for r in rows]


def get_shared_recipe(shared_id, user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT sr.*, u.name AS sender_name, u.email AS sender_email
           FROM shared_recipes sr
           JOIN users u ON u.id = sr.sender_id
           WHERE sr.id = %s AND sr.recipient_id = %s""",
        (shared_id, user_id),
    )
    row = cur.fetchone()
    cur.close()
    release_connection(conn)
    return _deserialize_shared_recipe(dict(row)) if row else None


def dismiss_shared_recipe(shared_id, user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM shared_recipes WHERE id = %s AND recipient_id = %s",
        (shared_id, user_id),
    )
    conn.commit()
    changed = cur.rowcount
    cur.close()
    release_connection(conn)
    return changed > 0


def copy_shared_to_saved(shared_id, user_id):
    shared = get_shared_recipe(shared_id, user_id)
    if not shared:
        return None

    recipe = {
        "name": shared["name"],
        "source_url": shared.get("source_url", ""),
        "servings": shared.get("servings", ""),
        "prep_time": shared.get("prep_time", ""),
        "cook_time": shared.get("cook_time", ""),
        "ingredients": shared["ingredients"],
        "instructions": shared["instructions"],
        "image_url": shared.get("image_url", ""),
    }
    new_id = create_recipe(user_id, recipe)
    dismiss_shared_recipe(shared_id, user_id)
    return new_id


def _deserialize_shared_recipe(row):
    row["ingredients"] = json.loads(row["ingredients"])
    row["instructions"] = json.loads(row["instructions"])
    return row