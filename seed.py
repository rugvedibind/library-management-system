"""Fill the database with sample books and members (safe to run more than once).

Run:  python seed.py
"""
import sqlite3

from app import DEFAULT_DB, create_app

BOOKS = [
    ("Clean Code", "Robert C. Martin", "9780132350884", "Programming"),
    ("Introduction to Algorithms", "Thomas H. Cormen", "9780262033848", "Computer Science"),
    ("Python Crash Course", "Eric Matthes", "9781593279288", "Programming"),
    ("Database System Concepts", "Abraham Silberschatz", "9780078022159", "Computer Science"),
    ("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", "Biography"),
    ("The Guide", "R. K. Narayan", "9780226568287", "Fiction"),
    ("Train to Pakistan", "Khushwant Singh", "9780143065883", "Fiction"),
    ("Discovery of India", "Jawaharlal Nehru", "9780143031031", "History"),
    ("A Brief History of Time", "Stephen Hawking", "9780553380163", "Science"),
    ("Ikigai", "Hector Garcia", "9780143130727", "Self-Help"),
]

MEMBERS = [
    ("Asha Patil", "asha@example.com", "9876543210"),
    ("Ravi Joshi", "ravi@example.com", "9123456780"),
    ("Neha Deshmukh", "neha@example.com", "9988776655"),
]

if __name__ == "__main__":
    create_app()  # makes sure the tables exist
    with sqlite3.connect(DEFAULT_DB) as con:
        con.executemany(
            "INSERT OR IGNORE INTO books (title, author, isbn, category) VALUES (?, ?, ?, ?)", BOOKS
        )
        con.executemany(
            "INSERT OR IGNORE INTO members (name, email, phone) VALUES (?, ?, ?)", MEMBERS
        )
    print(f"Seeded {len(BOOKS)} books and {len(MEMBERS)} members into {DEFAULT_DB}")
