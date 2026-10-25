"""Authentication: password login and JWT issuing."""
import hashlib
import time

import jwt

from app.config import SECRET_KEY
from app.models import USERS

TOKEN_TTL_SECONDS = 3600


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def login(username: str, password: str) -> str:
    """Return a signed JWT when the credentials are valid, otherwise raise PermissionError."""
    user = USERS.get(username)
    if user is None or user.password_hash != hash_password(password):
        raise PermissionError("invalid credentials")
    claims = {"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(claims, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> str:
    """Return the username stored in a valid token."""
    claims = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return claims["sub"]
