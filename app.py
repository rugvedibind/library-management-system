"""Library Management System - Flask + SQLite backend.

Run:  python app.py        (server on http://127.0.0.1:5000)
"""
import os
import re
import sqlite3
from datetime import date, timedelta

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(BASE_DIR, "library.db")

LOAN_DAYS = 14          # how long a book can be kept
FINE_PER_DAY = 2        # rupees per late day
MAX_BOOKS_PER_MEMBER = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    email     TEXT NOT NULL UNIQUE,
    phone     TEXT,
    joined_on TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS books (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    title    TEXT NOT NULL,
    author   TEXT NOT NULL,
    isbn     TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'General',
    status   TEXT NOT NULL DEFAULT 'Available'
             CHECK (status IN ('Available', 'Issued')),
    added_on TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES members(id),
    issue_date  TEXT NOT NULL,
    due_date    TEXT NOT NULL,
    return_date TEXT,
    fine        INTEGER NOT NULL DEFAULT 0
);
"""

BOOK_SELECT = """
SELECT b.id, b.title, b.author, b.isbn, b.category, b.status, b.added_on,
       m.id AS member_id, m.name AS issued_to, i.due_date
FROM books b
LEFT JOIN issues  i ON i.book_id = b.id AND i.return_date IS NULL
LEFT JOIN members m ON m.id = i.member_id
"""


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or os.environ.get("LIBRARY_DB", DEFAULT_DB)

    # ---------- database helpers ----------
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with sqlite3.connect(app.config["DB_PATH"]) as con:
        con.executescript(SCHEMA)

    def rows(cursor):
        return [dict(r) for r in cursor.fetchall()]

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError("Request body must be valid JSON.")
        return data

    def clean(data, key, required=True, max_len=150):
        value = str(data.get(key) or "").strip()
        if required and not value:
            raise ApiError(f"'{key}' is required.")
        if len(value) > max_len:
            raise ApiError(f"'{key}' must be at most {max_len} characters.")
        return value

    def normalise_isbn(raw):
        isbn = re.sub(r"[\s-]", "", raw).upper()
        if not (re.fullmatch(r"\d{13}", isbn) or re.fullmatch(r"\d{9}[\dX]", isbn)):
            raise ApiError("ISBN must be 10 or 13 digits (hyphens allowed).")
        return isbn

    def get_book(book_id):
        book = get_db().execute(BOOK_SELECT + " WHERE b.id = ?", (book_id,)).fetchone()
        if book is None:
            raise ApiError(f"Book with id {book_id} not found.", 404)
        return dict(book)

    # ---------- error handling ----------
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify(error=err.message), err.status

    @app.errorhandler(404)
    def handle_404(_e):
        return jsonify(error="Resource not found."), 404

    @app.errorhandler(405)
    def handle_405(_e):
        return jsonify(error="Method not allowed."), 405

    # ---------- pages ----------
    @app.get("/")
    def index():
        return render_template("index.html")

    # ---------- books ----------
    @app.get("/api/books")
    def list_books():
        """List books. Optional ?q= (title/author/ISBN), ?category=, ?status="""
        q = request.args.get("q", "").strip()
        category = request.args.get("category", "").strip()
        status = request.args.get("status", "").strip()

        sql, params, where = BOOK_SELECT, [], []
        if q:
            like = f"%{q}%"
            digits_only = re.sub(r"[\s-]", "", q)
            like_isbn = f"%{digits_only}%"
            where.append("(b.title LIKE ? OR b.author LIKE ? OR b.isbn LIKE ?)")
            params += [like, like, like_isbn]
        if category:
            where.append("b.category = ?")
            params.append(category)
        if status:
            if status not in ("Available", "Issued"):
                raise ApiError("status must be 'Available' or 'Issued'.")
            where.append("b.status = ?")
            params.append(status)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY b.title COLLATE NOCASE"
        return jsonify(rows(get_db().execute(sql, params)))

    @app.post("/api/books")
    def add_book():
        data = body()
        title = clean(data, "title")
        author = clean(data, "author")
        isbn = normalise_isbn(clean(data, "isbn", max_len=20))
        category = clean(data, "category", required=False, max_len=50) or "General"
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)",
                (title, author, isbn, category),
            )
            db.commit()
        except sqlite3.IntegrityError:
            raise ApiError(f"A book with ISBN {isbn} already exists.", 409)
        return jsonify(get_book(cur.lastrowid)), 201

    @app.delete("/api/books/<int:book_id>")
    def delete_book(book_id):
        book = get_book(book_id)
        if book["status"] == "Issued":
            raise ApiError("This book is currently issued. Return it before deleting.", 409)
        db = get_db()
        db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        db.commit()
        return jsonify(message=f"'{book['title']}' deleted.")

    @app.post("/api/books/<int:book_id>/issue")
    def issue_book(book_id):
        data = body()
        try:
            member_id = int(data.get("member_id"))
        except (TypeError, ValueError):
            raise ApiError("'member_id' is required.")
        book = get_book(book_id)
        db = get_db()
        member = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if member is None:
            raise ApiError(f"Member with id {member_id} not found.", 404)
        if book["status"] == "Issued":
            raise ApiError(f"'{book['title']}' is already issued to {book['issued_to']}.", 409)
        held = db.execute(
            "SELECT COUNT(*) FROM issues WHERE member_id = ? AND return_date IS NULL",
            (member_id,),
        ).fetchone()[0]
        if held >= MAX_BOOKS_PER_MEMBER:
            raise ApiError(
                f"{member['name']} already has {MAX_BOOKS_PER_MEMBER} books (the limit).", 409
            )
        today = date.today()
        db.execute(
            "INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
            (book_id, member_id, today.isoformat(), (today + timedelta(days=LOAN_DAYS)).isoformat()),
        )
        db.execute("UPDATE books SET status = 'Issued' WHERE id = ?", (book_id,))
        db.commit()
        return jsonify(get_book(book_id))

    @app.post("/api/books/<int:book_id>/return")
    def return_book(book_id):
        book = get_book(book_id)
        if book["status"] != "Issued":
            raise ApiError(f"'{book['title']}' is not issued, so it cannot be returned.", 409)
        db = get_db()
        issue = db.execute(
            "SELECT * FROM issues WHERE book_id = ? AND return_date IS NULL", (book_id,)
        ).fetchone()
        today = date.today()
        late_days = max(0, (today - date.fromisoformat(issue["due_date"])).days)
        fine = late_days * FINE_PER_DAY
        db.execute(
            "UPDATE issues SET return_date = ?, fine = ? WHERE id = ?",
            (today.isoformat(), fine, issue["id"]),
        )
        db.execute("UPDATE books SET status = 'Available' WHERE id = ?", (book_id,))
        db.commit()
        result = get_book(book_id)
        result["fine"] = fine
        return jsonify(result)

    # ---------- members ----------
    @app.get("/api/members")
    def list_members():
        sql = """
        SELECT m.*, (SELECT COUNT(*) FROM issues i
                     WHERE i.member_id = m.id AND i.return_date IS NULL) AS books_held
        FROM members m ORDER BY m.name COLLATE NOCASE
        """
        return jsonify(rows(get_db().execute(sql)))

    @app.post("/api/members")
    def add_member():
        data = body()
        name = clean(data, "name", max_len=100)
        email = clean(data, "email", max_len=120).lower()
        phone = clean(data, "phone", required=False, max_len=20)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ApiError("Enter a valid email address.")
        if phone and not re.fullmatch(r"[\d+\s-]{7,20}", phone):
            raise ApiError("Phone may contain only digits, spaces, + and -.")
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO members (name, email, phone) VALUES (?, ?, ?)", (name, email, phone)
            )
            db.commit()
        except sqlite3.IntegrityError:
            raise ApiError(f"A member with email {email} already exists.", 409)
        member = db.execute("SELECT * FROM members WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(member, books_held=0)), 201

    # ---------- history & stats ----------
    @app.get("/api/issues")
    def list_issues():
        sql = """
        SELECT i.id, b.title, m.name AS member, i.issue_date, i.due_date,
               i.return_date, i.fine
        FROM issues i
        JOIN books b ON b.id = i.book_id
        JOIN members m ON m.id = i.member_id
        ORDER BY i.id DESC LIMIT 100
        """
        return jsonify(rows(get_db().execute(sql)))

    @app.get("/api/stats")
    def stats():
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        issued = db.execute("SELECT COUNT(*) FROM books WHERE status = 'Issued'").fetchone()[0]
        members = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        overdue = db.execute(
            "SELECT COUNT(*) FROM issues WHERE return_date IS NULL AND due_date < ?",
            (date.today().isoformat(),),
        ).fetchone()[0]
        categories = [
            r[0] for r in db.execute("SELECT DISTINCT category FROM books ORDER BY category")
        ]
        return jsonify(
            total=total, issued=issued, available=total - issued,
            members=members, overdue=overdue, categories=categories,
        )

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=int(os.environ.get("PORT", 5000)))
