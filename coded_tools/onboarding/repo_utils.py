"""Shared helpers for the Onboarding Buddy coded tools.

Security model
--------------
* The repository root is NEVER chosen by the LLM. It comes, in order, from
  ``sly_data["repo_root"]`` (supplied by the client), the ``ONBOARDING_REPO_ROOT``
  environment variable (supplied by whoever runs the server) or the bundled
  ``sample_repo``. A hostile file inside the repository therefore cannot redirect
  the tools somewhere else.
* Every path a tool touches is resolved and must stay inside that root.
* Repository content is untrusted data: instruction-like text aimed at AI
  assistants is flagged, and credential files are never displayed.
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List

from neuro_san.interfaces.coded_tool import CodedTool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO_ROOT = PROJECT_ROOT / "sample_repo"
ENV_REPO_ROOT = "ONBOARDING_REPO_ROOT"

SKIP_DIRS = frozenset(
    {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build",
     ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".tox", "logs", "target"}
)
MAX_FILES = 3000
MAX_FILE_BYTES = 500_000

TEXT_SUFFIXES = frozenset(
    {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".rs", ".c", ".cpp", ".h",
     ".cs", ".php", ".sh", ".sql", ".md", ".txt", ".yml", ".yaml", ".toml", ".json", ".hocon",
     ".cfg", ".ini", ".html", ".css", ".env", ""}
)
SENSITIVE_FILE_NAMES = frozenset({".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", "credentials"})
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
TEMPLATE_SUFFIXES = (".example", ".sample", ".template")

# Heuristics for text that tries to give orders to an AI assistant.
INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions",
        r"disregard\s+(all\s+|any\s+)?(previous|prior|above|your)\s+(instructions|rules)",
        r"(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|llm|assistant|agent)s?",
        r"you\s+are\s+now\s+(a|an|in)\b",
        r"(reveal|print|output|include|send)\b.{0,60}\b(system\s+prompt|api\s*key|password|secret|credentials)",
        r"(read|open|cat|fetch)\b.{0,40}(/etc/passwd|\.ssh|system32|\.\./)",
    )
)


class SandboxError(ValueError):
    """Raised when a request would leave, or cannot find, the repository sandbox."""


def resolve_repo_root(sly_data: Dict[str, Any]) -> Path:
    """Return the repository root the tools are allowed to read."""
    configured = (sly_data or {}).get("repo_root") or os.environ.get(ENV_REPO_ROOT) or str(DEFAULT_REPO_ROOT)
    root = Path(str(configured)).expanduser().resolve()
    if not root.is_dir():
        raise SandboxError(f"The configured repository root '{configured}' is not a directory.")
    return root


def safe_join(root: Path, relative: Any) -> Path:
    """Join ``relative`` onto ``root`` and refuse anything that resolves outside it."""
    text = str(relative or "").strip().replace("\\", "/")
    if not text:
        raise SandboxError("No file path was given.")
    candidate = (root / text).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise SandboxError(f"'{text}' is outside the repository sandbox and cannot be read.")
    return candidate


def is_sensitive(path: Path) -> bool:
    """True for credential-style files whose contents must never be displayed."""
    name = path.name.lower()
    if name.endswith(TEMPLATE_SUFFIXES):
        return False
    return name in SENSITIVE_FILE_NAMES or name.startswith(".env.") or name.endswith(SENSITIVE_SUFFIXES)


def is_text_file(path: Path) -> bool:
    """Cheap check: known text suffix (or well-known name) and no NUL bytes in the first KB."""
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
        return False
    try:
        with path.open("rb") as handle:
            return b"\x00" not in handle.read(1024)
    except OSError:
        return False


def iter_repo_files(root: Path) -> Iterator[Path]:
    """Yield regular files under ``root`` in a stable order, skipping noise and symlinks."""
    count = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(files):
            path = Path(current) / name
            try:
                if path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path
            count += 1
            if count >= MAX_FILES:
                return


def relative_posix(root: Path, path: Path) -> str:
    """Repository-relative path with forward slashes, the format used in citations."""
    return path.relative_to(root).as_posix()


def read_lines(path: Path) -> List[str]:
    """Read a text file as a list of lines, tolerating bad encodings."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read().splitlines()


def find_injection_lines(lines: List[str], first_line_number: int = 1) -> List[int]:
    """Line numbers whose text looks like an instruction aimed at an AI assistant."""
    return [
        first_line_number + offset
        for offset, line in enumerate(lines)
        if any(pattern.search(line) for pattern in INJECTION_PATTERNS)
    ]


def as_int(value: Any, default: int, low: int, high: int) -> int:
    """Coerce an LLM-supplied argument to an int clamped to [low, high]."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


class SandboxedTool(CodedTool):
    """Base class: resolve the sandbox, report sandbox violations politely, keep I/O off the event loop.

    Subclasses implement ``run(root, args, sly_data)`` and return the text the calling agent will see.
    """

    def run(self, root: Path, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Do the actual work for one tool call."""
        raise NotImplementedError

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        try:
            return self.run(resolve_repo_root(sly_data), args or {}, sly_data)
        except SandboxError as error:
            return f"ERROR: {error}"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """Blocking file I/O runs in a worker thread so concurrent agents are not serialized."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
