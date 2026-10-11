import os
from flask import Blueprint, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import db

oauth = OAuth()

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@auth_bp.route("/login")
def login():
    """Kick off the OAuth flow, send the user to Google."""
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/callback")
def callback():
    """Google sends the user back here. Exchange the code for their info."""
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")

    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email)
    picture = userinfo.get("picture")

    # Find or create the user in our DB
    user = db.get_user_by_google_id(google_id)
    if not user:
        user_id = db.create_user(google_id, email, name, picture)
        user = {
            "id": user_id,
            "google_id": google_id,
            "email": email,
            "name": name,
            "picture": picture,
        }

    # Store who they are in the session
    session["user"] = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
    }

    return redirect(url_for("home"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))