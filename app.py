import os
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from parse import parse_recipe_from_url
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import date, datetime, timezone


import db
import auth


load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

@app.template_filter("timeago")
def timeago_filter(dt):
    """Turn a timestamp into '2 days ago' style text."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = delta.total_seconds()

    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = int(seconds // 60)
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = int(seconds // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if seconds < 604800:
        d = int(seconds // 86400)
        return f"{d} day{'s' if d != 1 else ''} ago"
    if seconds < 2592000:
        w = int(seconds // 604800)
        return f"{w} week{'s' if w != 1 else ''} ago"
    if seconds < 31536000:
        mo = int(seconds // 2592000)
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = int(seconds // 31536000)
    return f"{y} year{'s' if y != 1 else ''} ago"

@app.context_processor
def inject_notifications():
    """Make pending_count and inbox_count available to all templates."""
    user = session.get("user")
    if not user:
        return {"pending_count": 0, "inbox_count": 0}
    pending = len(db.get_pending_requests_for(user["id"]))
    inbox = len(db.get_inbox_for_user(user["id"]))
    return {"pending_count": pending, "inbox_count": inbox}

db.init_db()

auth.init_oauth(app)
app.register_blueprint(auth.auth_bp)

'''---------- Routes ------------'''

@app.route("/")
def index():
    """Entry point for the app, we send logged in users to home, and others to login."""
    if session.get("user"):
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/login")
def login():
    """The login page goes here"""
    return render_template("login.html")


@app.route("/home")
def home():
    """Home page, set the user once they have logged in"""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    ''' getting more info to make homepage a bit more robust'''
    recipes = db.get_recipes_for_user(user["id"])
    recent = recipes[:3]
    return render_template("home.html", user=user, recent=recent, total=len(recipes))


@app.route("/convert", methods=["GET", "POST"])
def convert():
    """Convert page. GET renders the form; POST handles the submission."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    # GET — render the form
    if request.method == "GET":
        mode = request.args.get("mode", "url")
        if mode not in ("url", "manual"):
            mode = "url"
        return render_template("convert.html", user=user, mode=mode)

    # POST — handle the submission
    mode = request.form.get("mode", "url")

    if mode == "url":
        url = request.form.get("url", "").strip()
        if not url:
            return render_template("convert.html", user=user, mode="url",
                                   error="Please enter a URL.")

        recipe = parse_recipe_from_url(url)
        if not recipe:
            return render_template("convert.html", user=user, mode="url",
                                   error="Couldn't parse a recipe from that URL. "
                                         "Try a different site, or switch to Manual mode.")

        session["pending_recipe"] = recipe
        return redirect(url_for("preview"))

    else:  # manual mode
        ingredients_raw = request.form.get("ingredients", "")
        instructions_raw = request.form.get("instructions", "")
        recipe = {
            "name": request.form.get("name", "").strip(),
            "ingredients": [line.strip() for line in ingredients_raw.split("\n") if line.strip()],
            "instructions": [line.strip() for line in instructions_raw.split("\n") if line.strip()],
            "servings": request.form.get("servings", "").strip(),
            "prep_time": request.form.get("prep_time", "").strip(),
            "cook_time": request.form.get("cook_time", "").strip(),
            "image_url": "",
            "source_url": "",
        }
        session["pending_recipe"] = recipe
        return redirect(url_for("preview"))
    

@app.route("/preview")
def preview():
    """Preview page — editable recipe form."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipe = session.get("pending_recipe")
    if not recipe:
        # No pending recipe — bounce back to convert
        return redirect(url_for("convert"))

    return render_template("preview.html", user=user, recipe=recipe)


@app.route("/preview/save", methods=["POST"])
def preview_save():
    """Save the (edited) recipe to the DB, then go to the saved list."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipe = {
        "name": request.form.get("name", "").strip(),
        "servings": request.form.get("servings", "").strip(),
        "prep_time": request.form.get("prep_time", "").strip(),
        "cook_time": request.form.get("cook_time", "").strip(),
        "ingredients": [i.strip() for i in request.form.getlist("ingredients") if i.strip()],
        "instructions": [i.strip() for i in request.form.getlist("instructions") if i.strip()],
        "source_url": session.get("pending_recipe", {}).get("source_url", ""),
        "image_url": session.get("pending_recipe", {}).get("image_url", ""),
    }

    if not recipe["name"]:
        return redirect(url_for("preview"))

    db.create_recipe(user["id"], recipe)
    session.pop("pending_recipe", None)
    return redirect(url_for("saved"))


@app.route("/saved")
def saved():
    """List all recipes for the current user, newest first."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipes = db.get_recipes_for_user(user["id"])
    return render_template("saved.html", user=user, recipes=recipes)

@app.route("/recipe/<int:recipe_id>")
def recipe_detail(recipe_id):
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipe = db.get_recipe(recipe_id, user["id"])
    if not recipe:
        return redirect(url_for("saved"))

    friends = db.get_friends_for(user["id"])
    return render_template("recipe.html", user=user, recipe=recipe, friends=friends)

@app.route("/friends")
def friends():
    """Friend list + pending requests + add-friend form."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    friends_list = db.get_friends_for(user["id"])
    pending = db.get_pending_requests_for(user["id"])
    return render_template(
        "friends.html", user=user, friends=friends_list, pending=pending,
        error=request.args.get("error"), sent=request.args.get("sent"),
        view="friends", inbox=[],
    )


@app.route("/friends/add", methods=["POST"])
def friends_add():
    """Handle the add-friend form."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    email = request.form.get("email", "").strip().lower()
    if not email:
        return redirect(url_for("friends", error="Enter an email."))

    if email == user["email"].lower():
        return redirect(url_for("friends", error="You can't friend yourself."))

    target = db.get_user_by_email(email)
    if not target:
        return redirect(url_for("friends", error="No user with that email. They need to log in first."))

    existing = db.get_friendship_between(user["id"], target["id"])
    if existing:
        if existing["status"] == "accepted":
            return redirect(url_for("friends", error="You're already friends."))
        return redirect(url_for("friends", error="A request already exists."))

    db.create_friend_request(user["id"], target["id"])
    return redirect(url_for("friends", sent="1"))


@app.route("/friends/accept/<int:friendship_id>", methods=["POST"])
def friends_accept(friendship_id):
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    db.accept_friend_request(friendship_id, user["id"])
    return redirect(url_for("friends"))


@app.route("/friends/decline/<int:friendship_id>", methods=["POST"])
def friends_decline(friendship_id):
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))
    db.decline_friend_request(friendship_id, user["id"])
    return redirect(url_for("friends"))

@app.route("/recipe/<int:recipe_id>/send", methods=["POST"])
def recipe_send(recipe_id):
    """Send a recipe to a friend's inbox."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipe = db.get_recipe(recipe_id, user["id"])
    if not recipe:
        return redirect(url_for("saved"))

    friend_id = request.form.get("friend_id", type=int)
    if not friend_id:
        return redirect(url_for("recipe_detail", recipe_id=recipe_id))

    # Verify the target is actually a friend
    friends = db.get_friends_for(user["id"])
    if not any(f["id"] == friend_id for f in friends):
        return redirect(url_for("recipe_detail", recipe_id=recipe_id))

    db.send_shared_recipe(friend_id, user["id"], recipe)
    return redirect(url_for("recipe_detail", recipe_id=recipe_id))


@app.route("/friends/inbox")
def friends_inbox():
    """Shared recipes inbox."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    inbox = db.get_inbox_for_user(user["id"])
    friends_list = db.get_friends_for(user["id"])
    pending = db.get_pending_requests_for(user["id"])

    return render_template(
        "friends.html",
        user=user,
        friends=friends_list,
        pending=pending,
        inbox=inbox,
        view="inbox",
    )


@app.route("/shared/<int:shared_id>/save", methods=["POST"])
def shared_save(shared_id):
    """Copy a shared recipe into the current user's collection."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    new_id = db.copy_shared_to_saved(shared_id, user["id"])
    if new_id:
        return redirect(url_for("recipe_detail", recipe_id=new_id))
    return redirect(url_for("friends_inbox"))


@app.route("/shared/<int:shared_id>/dismiss", methods=["POST"])
def shared_dismiss(shared_id):
    """Remove a shared recipe from the inbox without saving."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    db.dismiss_shared_recipe(shared_id, user["id"])
    return redirect(url_for("friends_inbox"))


@app.route("/privacy")
def privacy():
    today = date.today().strftime("%B %d, %Y")
    return render_template("privacy.html", today=today)

'''Great for dev work, the debug set to true will ocnstantly show the updated pages if I edit,
also only runs right now if I literally run with python3 app.py, ignored when I deploy app any different '''
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)