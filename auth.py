import os
from flask import Blueprint, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import db

oauth = OAuth()

#setting a blueprint for all the auth routes
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def init_oauth(app):
    """Wire up Authlib and register Google as an OAuth provider.
    Call once from app.py at startup. Requires app.secret_key to be set."""
    oauth.init_app(app)  #binding Oauth to my Flask app
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# /auth/login -> immediately redirects the browser to Google's login page
@auth_bp.route("/login")
def login():
    """Kick off the OAuth flow, send the user to Google."""
    redirect_uri = url_for("auth.callback", _external=True)
    # Tell Google where to send the user back after they log in
    return oauth.google.authorize_redirect(redirect_uri)


# Google redirects the user back here with ?code=...; we trade it for identity
@auth_bp.route("/callback")
def callback():
    """Google sends the user back here. Exchange the code for their info."""
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")

    # 'sub' is Google's stable permanent ID — use it, not email, to identify users
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

    # Store who they are in the session (this is what "logged in" means in our app)
    session["user"] = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
    }
    #redirect them to home page
    return redirect(url_for("home"))


# Log out of *this app* only — user's Google session is untouched
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))