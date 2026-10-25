# Bookshelf API

A small Flask service for managing a personal book collection. Users log in, then add, list
and search their books.

## Quick start

1. Create a virtual environment: `python -m venv .venv` and activate it.
2. Install dependencies: `pip install -r requirements.txt`
3. Seed the demo data: `python scripts/seed_db.py`
4. Start the server: `python -m app.main` (listens on port 5000)

## Running the tests

Run `pytest -q` from the project root.

## Project layout

- `app/main.py` - application factory and HTTP routes
- `app/auth.py` - login and token verification
- `app/models.py` - Book and User data classes plus the in-memory store
- `app/config.py` - settings
- `scripts/seed_db.py` - loads demo users and books
- `tests/` - pytest suite

## Deployment

A `Dockerfile` is provided. Configuration is read from environment variables.
