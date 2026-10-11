import os
from flask import Flask, render_template, session, redirect, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")


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


@app.route("/logout")
def logout():
    """Clear the session and go back to login page """
    session.clear()
    return redirect(url_for("login"))

'''Great for dev work, the debug set to true will ocnstantly show the updated pages if I edit,
also only runs right now if I literally run with python3 app.py'''
if __name__ == "__main__":
    app.run(debug=True, port=5000)