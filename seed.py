"""Load a sample dataset: ~266 books (from data/books.csv), 30 members and sample loans.

Run:    python seed.py            add sample data (safe to run again)
        python seed.py --reset    delete the database first, then add fresh sample data
        python seed.py my.csv     use your own CSV (columns: title,author,isbn,category)
"""
import csv
import os
import random
import sqlite3
import sys
from datetime import date, timedelta

from app import DEFAULT_DB, FINE_PER_DAY, LOAN_DAYS, create_app

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "books.csv")

MEMBERS = [
    "Asha Patil", "Ravi Joshi", "Neha Deshmukh", "Rohan Kulkarni", "Sneha Jadhav",
    "Aditya Pawar", "Priya Shinde", "Omkar More", "Pooja Chavan", "Sahil Gaikwad",
    "Ananya Kale", "Vedant Bhosale", "Riya Salunkhe", "Kunal Thakur", "Isha Naik",
    "Harsh Mehta", "Divya Rane", "Yash Sawant", "Meera Iyer", "Arjun Nair",
    "Kavya Reddy", "Siddharth Rao", "Tanvi Gupta", "Aman Sharma", "Nisha Verma",
    "Pratik Wagh", "Shruti Phadke", "Tejas Ghule", "Mansi Bhagat", "Rugved Ibind",
]


def read_books(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [(r["title"], r["author"], r["isbn"], r["category"]) for r in csv.DictReader(f)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv_path = args[0] if args else CSV_PATH
    db_path = os.environ.get("LIBRARY_DB", DEFAULT_DB)

    if "--reset" in sys.argv and os.path.exists(db_path):
        os.remove(db_path)
    create_app(db_path)  # makes sure the tables exist

    books = read_books(csv_path)
    members = [(n, n.lower().replace(" ", ".") + "@example.com", f"98{random.Random(n).randint(10000000, 99999999)}")
               for n in MEMBERS]

    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.executemany("INSERT OR IGNORE INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)", books)
        con.executemany("INSERT OR IGNORE INTO members (name, email, phone) VALUES (?, ?, ?)", members)

        # sample loans, only on a database that has none yet
        if con.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            rng = random.Random(7)
            today = date.today()
            book_ids = [r[0] for r in con.execute("SELECT id FROM books ORDER BY id")]
            member_ids = [r[0] for r in con.execute("SELECT id FROM members ORDER BY id")]
            picks = rng.sample(book_ids, 40)

            for i, book_id in enumerate(picks[:22]):       # currently issued (some overdue)
                issued = today - timedelta(days=rng.randint(1, 30))
                con.execute(
                    "INSERT INTO issues (book_id, member_id, issue_date, due_date) VALUES (?, ?, ?, ?)",
                    (book_id, member_ids[i % len(member_ids)], issued.isoformat(),
                     (issued + timedelta(days=LOAN_DAYS)).isoformat()))
                con.execute("UPDATE books SET status = 'Issued' WHERE id = ?", (book_id,))

            for book_id in picks[22:]:                      # returned earlier, some late
                issued = today - timedelta(days=rng.randint(40, 120))
                due = issued + timedelta(days=LOAN_DAYS)
                returned = issued + timedelta(days=rng.randint(4, 26))
                fine = max(0, (returned - due).days) * FINE_PER_DAY
                con.execute(
                    "INSERT INTO issues (book_id, member_id, issue_date, due_date, return_date, fine) VALUES (?, ?, ?, ?, ?, ?)",
                    (book_id, rng.choice(member_ids), issued.isoformat(), due.isoformat(), returned.isoformat(), fine))

        total = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        out = con.execute("SELECT COUNT(*) FROM books WHERE status='Issued'").fetchone()[0]
        mem = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    print(f"Database ready: {total} books ({out} issued), {mem} members -> {db_path}")


if __name__ == "__main__":
    main()
