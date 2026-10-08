# Library Management System

Full-stack web app: **HTML/CSS/JavaScript** frontend (Node.js tooling), **Python Flask** backend, **SQLite** database.

## Features
- Add, list, search (title / author / ISBN), issue, return and delete books
- Members table related to books through an `issues` table (full history)
- A book cannot be issued if it is already issued; an issued book cannot be deleted
- A book that is not issued cannot be returned
- 14-day loan period, Rs 2/day late fine, max 3 books per member
- No page reloads: everything uses the Fetch API with JSON

## Project structure
```
app.py            Flask app + REST API
seed.py           sample data
templates/        index.html
static/css/       style.css
static/js/        app.js (Fetch API)
tests/            test_api.py (edge cases)
package.json      Node.js tooling (dev server, format, lint)
requirements.txt  Python dependencies
```

## Run it
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python seed.py                  # optional sample data
python app.py                   # open http://127.0.0.1:5000
```
Node tooling (optional): `npm install`, then `npm run dev` (auto-restart), `npm run format`, `npm run lint`.

## Tests
```bash
python -m unittest discover -s tests -v
```

## Database schema
| Table   | Columns |
|---------|---------|
| members | id (PK), name, email (unique), phone, joined_on |
| books   | id (PK), title, author, isbn (unique), category, status (Available/Issued), added_on |
| issues  | id (PK), book_id (FK books), member_id (FK members), issue_date, due_date, return_date, fine |

## REST API
| Method | URL | Purpose |
|--------|-----|---------|
| GET    | /api/books?q=&status=&category= | List / search books |
| POST   | /api/books | Add book `{title, author, isbn, category}` |
| DELETE | /api/books/<id> | Delete book (409 if issued) |
| POST   | /api/books/<id>/issue | Issue to member `{member_id}` (409 if unavailable) |
| POST   | /api/books/<id>/return | Return book (409 if not issued) |
| GET/POST | /api/members | List / add members |
| GET    | /api/issues | Issue history |
| GET    | /api/stats | Dashboard counts |

Status codes: 200/201 success, 400 validation error, 404 not found, 409 conflict.
