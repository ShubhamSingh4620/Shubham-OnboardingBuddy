"""Load demo users and books into the in-memory store."""
from app.auth import hash_password
from app.models import BOOKS, USERS, Book, User


def seed() -> None:
    """Create one demo user and two books."""
    USERS["ana"] = User("ana", hash_password("s3cret-pass"))
    BOOKS.append(Book("Dune", "Frank Herbert", "ana", ["sci-fi"]))
    BOOKS.append(Book("Emma", "Jane Austen", "ana", ["classic"]))


if __name__ == "__main__":
    seed()
    print("Seeded demo data")
