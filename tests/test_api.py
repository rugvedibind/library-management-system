"""Run with:  python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


class LibraryApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(self.path)
        self.c = self.app.test_client()
        self.book = self.add_book("Clean Code", "Robert C. Martin", "9780132350884", "Programming")
        self.member = self.add_member("Asha Patil", "asha@example.com")

    def tearDown(self):
        os.remove(self.path)

    # helpers
    def add_book(self, title, author, isbn, category="General"):
        r = self.c.post("/api/books", json=dict(title=title, author=author, isbn=isbn, category=category))
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def add_member(self, name, email):
        r = self.c.post("/api/members", json=dict(name=name, email=email))
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def issue(self, book_id, member_id):
        return self.c.post(f"/api/books/{book_id}/issue", json={"member_id": member_id})

    # ---- add / list ----
    def test_add_and_list(self):
        books = self.c.get("/api/books").get_json()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["status"], "Available")

    def test_add_requires_fields(self):
        r = self.c.post("/api/books", json={"title": "", "author": "x", "isbn": "9780132350884"})
        self.assertEqual(r.status_code, 400)

    def test_invalid_isbn_rejected(self):
        r = self.c.post("/api/books", json=dict(title="T", author="A", isbn="123"))
        self.assertEqual(r.status_code, 400)

    def test_duplicate_isbn_rejected(self):
        r = self.c.post("/api/books", json=dict(title="Other", author="A", isbn="978-0-13-235088-4"))
        self.assertEqual(r.status_code, 409)

    def test_non_json_body(self):
        r = self.c.post("/api/books", data="hello", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    # ---- search ----
    def test_search_by_title_author_isbn(self):
        for q in ("clean", "martin", "9780132350884", "978-0-13-235088-4"):
            found = self.c.get("/api/books", query_string={"q": q}).get_json()
            self.assertEqual(len(found), 1, q)

    def test_search_non_existent_book(self):
        r = self.c.get("/api/books", query_string={"q": "zzz-not-a-book"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    # ---- issue ----
    def test_issue_marks_book_issued(self):
        r = self.issue(self.book["id"], self.member["id"])
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["status"], "Issued")
        self.assertEqual(data["issued_to"], "Asha Patil")

    def test_cannot_issue_already_issued_book(self):
        self.issue(self.book["id"], self.member["id"])
        other = self.add_member("Ravi Joshi", "ravi@example.com")
        r = self.issue(self.book["id"], other["id"])
        self.assertEqual(r.status_code, 409)
        self.assertIn("already issued", r.get_json()["error"])

    def test_issue_unknown_book_or_member(self):
        self.assertEqual(self.issue(999, self.member["id"]).status_code, 404)
        self.assertEqual(self.issue(self.book["id"], 999).status_code, 404)

    def test_issue_without_member_id(self):
        r = self.c.post(f"/api/books/{self.book['id']}/issue", json={})
        self.assertEqual(r.status_code, 400)

    def test_member_borrow_limit(self):
        for i in range(3):
            b = self.add_book(f"Book {i}", "Auth", f"97800000000{i:02d}"[:13].ljust(13, "0"))
            self.assertEqual(self.issue(b["id"], self.member["id"]).status_code, 200)
        extra = self.add_book("Extra", "Auth", "9781111111111")
        self.assertEqual(self.issue(extra["id"], self.member["id"]).status_code, 409)

    # ---- return ----
    def test_return_book(self):
        self.issue(self.book["id"], self.member["id"])
        r = self.c.post(f"/api/books/{self.book['id']}/return")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "Available")
        self.assertEqual(r.get_json()["fine"], 0)

    def test_return_book_not_issued(self):
        r = self.c.post(f"/api/books/{self.book['id']}/return")
        self.assertEqual(r.status_code, 409)

    def test_return_unknown_book(self):
        self.assertEqual(self.c.post("/api/books/999/return").status_code, 404)

    def test_late_return_fine(self):
        self.issue(self.book["id"], self.member["id"])
        import sqlite3
        late = (date.today() - timedelta(days=5)).isoformat()
        with sqlite3.connect(self.path) as con:
            con.execute("UPDATE issues SET due_date = ?", (late,))
        r = self.c.post(f"/api/books/{self.book['id']}/return")
        self.assertEqual(r.get_json()["fine"], 10)  # 5 days x Rs 2

    # ---- delete ----
    def test_delete_book(self):
        r = self.c.delete(f"/api/books/{self.book['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/api/books").get_json(), [])

    def test_cannot_delete_issued_book(self):
        self.issue(self.book["id"], self.member["id"])
        self.assertEqual(self.c.delete(f"/api/books/{self.book['id']}").status_code, 409)

    def test_delete_unknown_book(self):
        self.assertEqual(self.c.delete("/api/books/999").status_code, 404)

    # ---- members ----
    def test_duplicate_member_email(self):
        r = self.c.post("/api/members", json=dict(name="Dup", email="ASHA@example.com"))
        self.assertEqual(r.status_code, 409)

    def test_invalid_member_email(self):
        r = self.c.post("/api/members", json=dict(name="X", email="not-an-email"))
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
