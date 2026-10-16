import os
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from parse import parse_recipe_from_url
from dotenv import load_dotenv

import db
import auth


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

db.init_db()

auth.init_oauth(app)
app.register_blueprint(auth.auth_bp)

'''---------- Routes ----------'''

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
    return render_template("home.html", user=user)


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
    """Show one recipe."""
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    recipe = db.get_recipe(recipe_id, user["id"])
    if not recipe:
        return redirect(url_for("saved"))

    return render_template("recipe.html", user=user, recipe=recipe)

'''Great for dev work, the debug set to true will ocnstantly show the updated pages if I edit,
also only runs right now if I literally run with python3 app.py'''
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)