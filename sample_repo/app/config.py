"""Application settings."""
import os

DEBUG = os.environ.get("BOOKSHELF_DEBUG", "0") == "1"
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///bookshelf.db")

# TODO: move these out of source control before the first release
SECRET_KEY = "k9Xq2VbN7mPz4LwR8sTy1HdF6gJc3AeU"
DB_PASSWORD = "Winter2024!Admin"
