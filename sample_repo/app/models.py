"""Data classes and the in-memory store used by the demo."""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class User:
    username: str
    password_hash: str


@dataclass
class Book:
    title: str
    author: str
    owner: str
    tags: List[str] = field(default_factory=list)


USERS: Dict[str, User] = {}
BOOKS: List[Book] = []


def books_for(username: str) -> List[Book]:
    """Return the books owned by one user."""
    return [book for book in BOOKS if book.owner == username]
