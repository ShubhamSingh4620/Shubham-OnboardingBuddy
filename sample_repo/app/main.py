"""Flask application factory and HTTP routes."""
from flask import Flask, jsonify, request

from app import auth
from app.models import BOOKS, Book, books_for


def create_app() -> Flask:
    """Build the Flask app and register the routes."""
    app = Flask(__name__)

    @app.post("/login")
    def login_route():
        payload = request.get_json(force=True)
        try:
            token = auth.login(payload["username"], payload["password"])
        except PermissionError:
            return jsonify(error="invalid credentials"), 401
        return jsonify(token=token)

    @app.get("/books")
    def list_books():
        username = auth.verify_token(request.headers["Authorization"])
        return jsonify([book.__dict__ for book in books_for(username)])

    @app.post("/books")
    def add_book():
        username = auth.verify_token(request.headers["Authorization"])
        payload = request.get_json(force=True)
        BOOKS.append(Book(payload["title"], payload["author"], username))
        return jsonify(status="created"), 201

    return app


if __name__ == "__main__":
    create_app().run(port=5000)
