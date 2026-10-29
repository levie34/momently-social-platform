import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "momently.db"))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "local-dev-only-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

CATEGORIES = ["Love & Romance", "Friendship", "Family", "Birthday", "Celebration", "Just Because", "Games & Challenges"]
THEMES = ["🌸 Soft & Sweet", "✨ Magical", "😂 Funny", "💌 Heartfelt", "🎮 Playful", "🎉 Celebration"]

def db_conn():
    if "db" not in g:
        folder = os.path.dirname(DB_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      display_name TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      bio TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      is_admin INTEGER NOT NULL DEFAULT 0,
      is_active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS moments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      recipient TEXT NOT NULL,
      category TEXT NOT NULL,
      theme TEXT NOT NULL,
      message TEXT NOT NULL,
      privacy TEXT NOT NULL DEFAULT 'public',
      slug TEXT UNIQUE NOT NULL,
      created_at TEXT NOT NULL,
      is_hidden INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS reactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      moment_id INTEGER NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      emoji TEXT NOT NULL,
      created_at TEXT NOT NULL,
      UNIQUE(moment_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS comments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      moment_id INTEGER NOT NULL REFERENCES moments(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      body TEXT NOT NULL,
      created_at TEXT NOT NULL,
      is_hidden INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS reports (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      moment_id INTEGER REFERENCES moments(id) ON DELETE CASCADE,
      reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      reason TEXT NOT NULL,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open'
    );
    """)
    admin_name = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe-123!")
    existing = db.execute("SELECT id FROM users WHERE username=?", (admin_name,)).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username,display_name,password_hash,created_at,is_admin) VALUES (?,?,?,?,1)",
            (admin_name, "Momently Admin", generate_password_hash(admin_password), datetime.utcnow().isoformat(timespec="seconds"))
        )
    db.commit()
    db.close()

def now():
    return datetime.utcnow().isoformat(timespec="seconds")

@app.before_request
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)

def validate_csrf():
    sent = request.form.get("csrf_token", "")
    if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
        abort(400, description="Security token missing or expired. Refresh the page and try again.")

@app.context_processor
def inject_globals():
    user = None
    if session.get("user_id"):
        user = db_conn().execute("SELECT id, username, display_name, bio, is_admin FROM users WHERE id=? AND is_active=1", (session["user_id"],)).fetchone()
    return {"current_user": user, "categories": CATEGORIES, "themes": THEMES, "csrf_token": session.get("csrf", "")}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Create a free account or log in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = db_conn().execute("SELECT is_admin FROM users WHERE id=? AND is_active=1", (session.get("user_id", -1),)).fetchone()
        if not user or not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def clean_text(value, limit):
    return re.sub(r"\s+", " ", (value or "").strip())[:limit]

@app.route("/")
def index():
    db = db_conn()
    q = clean_text(request.args.get("q"), 70)
    category = request.args.get("category", "")
    sql = """SELECT m.*, u.username, u.display_name,
             (SELECT COUNT(*) FROM reactions r WHERE r.moment_id=m.id) AS reaction_count,
             (SELECT COUNT(*) FROM comments c WHERE c.moment_id=m.id AND c.is_hidden=0) AS comment_count
             FROM moments m JOIN users u ON u.id=m.user_id
             WHERE m.privacy='public' AND m.is_hidden=0 AND u.is_active=1"""
    params = []
    if q:
        sql += " AND (m.title LIKE ? OR m.message LIKE ? OR u.display_name LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if category in CATEGORIES:
        sql += " AND m.category=?"
        params.append(category)
    sql += " ORDER BY m.id DESC LIMIT 60"
    moments = db.execute(sql, params).fetchall()
    return render_template("index.html", moments=moments, q=q, selected_category=category)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        validate_csrf()
        username = clean_text(request.form.get("username"), 24).lower()
        display_name = clean_text(request.form.get("display_name"), 40)
        password = request.form.get("password", "")
        if not re.fullmatch(r"[a-z0-9_]{3,24}", username):
            flash("Username must be 3–24 characters: letters, numbers or underscores.", "error")
        elif len(display_name) < 2:
            flash("Please enter a display name with at least 2 characters.", "error")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "error")
        else:
            try:
                db_conn().execute(
                    "INSERT INTO users (username,display_name,password_hash,created_at) VALUES (?,?,?,?)",
                    (username, display_name, generate_password_hash(password), now())
                )
                db_conn().commit()
                user = db_conn().execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                session.clear()
                session["user_id"] = user["id"]
                session["csrf"] = secrets.token_urlsafe(24)
                flash("Welcome to Momently! Your account is ready.", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That username is already taken. Try another.", "error")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validate_csrf()
        username = clean_text(request.form.get("username"), 24).lower()
        password = request.form.get("password", "")
        user = db_conn().execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf"] = secrets.token_urlsafe(24)
            flash("You're back. Let's make a moment.", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Login details weren't recognised.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    validate_csrf()
    session.clear()
    flash("You have logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = db_conn()
    mine = db.execute("""SELECT m.*,
        (SELECT COUNT(*) FROM reactions r WHERE r.moment_id=m.id) AS reaction_count,
        (SELECT COUNT(*) FROM comments c WHERE c.moment_id=m.id AND c.is_hidden=0) AS comment_count
        FROM moments m WHERE m.user_id=? ORDER BY m.id DESC""", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", moments=mine)

@app.route("/create", methods=["GET", "POST"])
@login_required
def create_moment():
    if request.method == "POST":
        validate_csrf()
        title = clean_text(request.form.get("title"), 90)
        recipient = clean_text(request.form.get("recipient"), 60)
        category = request.form.get("category", "")
        theme = request.form.get("theme", "")
        message = (request.form.get("message") or "").strip()[:3000]
        privacy = request.form.get("privacy", "public")
        if len(title) < 3 or len(recipient) < 1 or len(message) < 10:
            flash("Add a title, who it's for, and a message of at least 10 characters.", "error")
        elif category not in CATEGORIES or theme not in THEMES or privacy not in ("public", "unlisted"):
            flash("Please choose valid options.", "error")
        else:
            slug = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
            db_conn().execute("""INSERT INTO moments
                (user_id,title,recipient,category,theme,message,privacy,slug,created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (session["user_id"], title, recipient, category, theme, message, privacy, slug, now()))
            db_conn().commit()
            flash("Your moment is live. Share it with someone special!", "success")
            return redirect(url_for("view_moment", slug=slug))
    return render_template("create.html")

@app.route("/m/<slug>", methods=["GET", "POST"])
def view_moment(slug):
    db = db_conn()
    moment = db.execute("""SELECT m.*,u.username,u.display_name,u.id AS creator_id
        FROM moments m JOIN users u ON u.id=m.user_id WHERE m.slug=? AND m.is_hidden=0 AND u.is_active=1""", (slug,)).fetchone()
    if not moment:
        abort(404)
    if moment["privacy"] == "unlisted" and (not session.get("user_id") or session["user_id"] != moment["creator_id"]):
        # An unlisted link is intentionally shareable; possession of the slug is the access key.
        pass
    if request.method == "POST":
        validate_csrf()
        if not session.get("user_id"):
            flash("Log in to react or comment.", "info")
            return redirect(url_for("login", next=request.path))
        if request.form.get("action") == "react":
            emoji = request.form.get("emoji", "💛")
            if emoji not in ("💛", "😍", "😂", "🎉", "🫶"):
                emoji = "💛"
            db.execute("INSERT INTO reactions(moment_id,user_id,emoji,created_at) VALUES (?,?,?,?) ON CONFLICT(moment_id,user_id) DO UPDATE SET emoji=excluded.emoji,created_at=excluded.created_at",
                       (moment["id"], session["user_id"], emoji, now()))
            db.commit()
            flash("Reaction added!", "success")
        elif request.form.get("action") == "comment":
            body = (request.form.get("body") or "").strip()
            if len(body) < 2 or len(body) > 500:
                flash("Comments must be 2–500 characters.", "error")
            else:
                db.execute("INSERT INTO comments(moment_id,user_id,body,created_at) VALUES (?,?,?,?)",
                           (moment["id"], session["user_id"], body, now()))
                db.commit()
                flash("Comment posted.", "success")
        return redirect(url_for("view_moment", slug=slug))
    reactions = db.execute("""SELECT r.emoji, u.username, u.display_name FROM reactions r
        JOIN users u ON u.id=r.user_id WHERE r.moment_id=? ORDER BY r.id DESC""", (moment["id"],)).fetchall()
    comments = db.execute("""SELECT c.*,u.username,u.display_name FROM comments c
        JOIN users u ON u.id=c.user_id WHERE c.moment_id=? AND c.is_hidden=0 ORDER BY c.id DESC LIMIT 100""", (moment["id"],)).fetchall()
    return render_template("moment.html", moment=moment, reactions=reactions, comments=comments)

@app.route("/u/<username>")
def profile(username):
    user = db_conn().execute("SELECT id,username,display_name,bio,created_at FROM users WHERE username=? AND is_active=1", (username.lower(),)).fetchone()
    if not user:
        abort(404)
    moments = db_conn().execute("""SELECT m.*,
        (SELECT COUNT(*) FROM reactions r WHERE r.moment_id=m.id) AS reaction_count,
        (SELECT COUNT(*) FROM comments c WHERE c.moment_id=m.id AND c.is_hidden=0) AS comment_count
        FROM moments m WHERE m.user_id=? AND m.is_hidden=0 AND (m.privacy='public' OR ?=?) ORDER BY m.id DESC""",
        (user["id"], session.get("user_id", -1), user["id"])).fetchall()
    return render_template("profile.html", profile_user=user, moments=moments)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = db_conn()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        validate_csrf()
        display_name = clean_text(request.form.get("display_name"), 40)
        bio = clean_text(request.form.get("bio"), 180)
        if len(display_name) < 2:
            flash("Display name must have at least 2 characters.", "error")
        else:
            db.execute("UPDATE users SET display_name=?,bio=? WHERE id=?", (display_name, bio, user["id"]))
            db.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("settings"))
    return render_template("settings.html", profile_user=user)

@app.route("/report/<int:moment_id>", methods=["POST"])
@login_required
def report_moment(moment_id):
    validate_csrf()
    reason = clean_text(request.form.get("reason"), 240) or "Community concern"
    moment = db_conn().execute("SELECT id FROM moments WHERE id=?", (moment_id,)).fetchone()
    if moment:
        db_conn().execute("INSERT INTO reports(moment_id,reporter_id,reason,created_at) VALUES (?,?,?,?)",
                          (moment_id, session["user_id"], reason, now()))
        db_conn().commit()
        flash("Report received. A moderator can review it.", "success")
    return redirect(request.referrer or url_for("index"))

@app.route("/admin")
@login_required
@admin_required
def admin():
    db = db_conn()
    reports = db.execute("""SELECT r.*,m.title,m.slug,u.username AS reporter FROM reports r
        LEFT JOIN moments m ON m.id=r.moment_id JOIN users u ON u.id=r.reporter_id
        WHERE r.status='open' ORDER BY r.id DESC""").fetchall()
    moments = db.execute("""SELECT m.*,u.username FROM moments m JOIN users u ON u.id=m.user_id
        ORDER BY m.id DESC LIMIT 100""").fetchall()
    stats = {
        "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "moments": db.execute("SELECT COUNT(*) FROM moments").fetchone()[0],
        "reports": db.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0],
    }
    return render_template("admin.html", reports=reports, moments=moments, stats=stats)

@app.route("/admin/report/<int:report_id>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_report_action(report_id, action):
    validate_csrf()
    db = db_conn()
    report = db.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if report:
        if action == "hide" and report["moment_id"]:
            db.execute("UPDATE moments SET is_hidden=1 WHERE id=?", (report["moment_id"],))
        db.execute("UPDATE reports SET status=? WHERE id=?", ("reviewed", report_id))
        db.commit()
        flash("Report reviewed.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/moment/<int:moment_id>/<action>", methods=["POST"])
@login_required
@admin_required
def admin_moment_action(moment_id, action):
    validate_csrf()
    if action == "hide":
        db_conn().execute("UPDATE moments SET is_hidden=1 WHERE id=?", (moment_id,))
    elif action == "show":
        db_conn().execute("UPDATE moments SET is_hidden=0 WHERE id=?", (moment_id,))
    db_conn().commit()
    flash("Content moderation updated.", "success")
    return redirect(url_for("admin"))

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Bad request.")), 400

@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You don't have permission to open this page."), 403

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="We couldn't find that moment or page."), 404

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
else:
    # WSGI servers import the module; ensure the database schema exists.
    init_db()
