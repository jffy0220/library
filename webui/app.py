import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
import psycopg2.extras
from datetime import date
from functools import wraps
from werkzeug.security import check_password_hash
from waitress import serve

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
)

def get_conn():
    return psycopg2.connect(**DB_CFG)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")  # set a strong value in .env
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set to True only if you terminate TLS in front of Flask (HTTPS):
    SESSION_COOKIE_SECURE=False,
)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
        if row and check_password_hash(row["password_hash"], password):
            session["user"] = {"id": row["id"], "username": row["username"]}
            flash("Logged in.", "success")
            dest = request.args.get("next") or url_for("index")
            return redirect(dest)
        flash("Invalid credentials.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT id, created_utc, book_name, page_number, chapter, verse,
                   LEFT(COALESCE(text_snippet,''), 180) AS preview
            FROM snippets
            ORDER BY id DESC
            LIMIT 25
        """)
        rows = cur.fetchall()
    return render_template("list.html", rows=rows)

@app.route("/new", methods=["GET", "POST"])
@login_required
def new_snippet():
    if request.method == "POST":
        def to_none(s): 
            return (s.strip() if s and s.strip() != "" else None)
        date_read_raw = to_none(request.form.get("date_read"))
        book_name     = to_none(request.form.get("book_name"))
        page_number   = to_none(request.form.get("page_number"))
        chapter       = to_none(request.form.get("chapter"))
        verse         = to_none(request.form.get("verse"))
        text_snippet  = to_none(request.form.get("text_snippet"))
        thoughts      = to_none(request.form.get("thoughts"))

        pg_num = None
        if page_number is not None:
            try: pg_num = int(page_number)
            except ValueError: flash("Page number must be an integer (or blank). Saved without it.", "warning")

        d_read = None
        if date_read_raw:
            try:
                y, m, d = map(int, date_read_raw.split("-"))
                d_read = date(y, m, d)
            except Exception:
                flash("Invalid date format; expected YYYY-MM-DD. Saved without it.", "warning")

        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO snippets
                    (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (d_read, book_name, pg_num, chapter, verse, text_snippet, thoughts))
            conn.commit()
        flash("Snippet saved!", "success")
        return redirect(url_for("index"))
    return render_template("form.html")

@app.route("/snippet/<int:sid>")
@login_required
def view_snippet(sid: int):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM snippets WHERE id=%s", (sid,))
        row = cur.fetchone()
    if not row:
        flash("Not found.", "error")
        return redirect(url_for("index"))
    return render_template("form.html", row=row, readonly=True)

if __name__ == "__main__":
    # For LAN access, bind to your host IP or 0.0.0.0
    app.run(host="0.0.0.0", port=5000, debug=False)
