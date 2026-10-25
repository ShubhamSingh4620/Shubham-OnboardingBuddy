"""CodedTool: RepoScanner.

Produces a factual, citable overview of the repository: languages, layout, key files,
entry points, dependencies, tests and TODO markers. Every item carries the path (and line
where relevant) so the agents can cite it and the CitationVerifier can check it.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

from .repo_utils import SandboxedTool
from .repo_utils import is_sensitive
from .repo_utils import is_text_file
from .repo_utils import iter_repo_files
from .repo_utils import read_lines
from .repo_utils import relative_posix

KEY_FILE_NAMES = frozenset(
    {"readme.md", "contributing.md", "license", "requirements.txt", "requirements-dev.txt", "pyproject.toml",
     "setup.py", "setup.cfg", "package.json", "dockerfile", "docker-compose.yml", "makefile", "tox.ini",
     "pytest.ini", ".env.example"}
)
ENTRY_FILE_NAMES = frozenset(
    {"main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py", "cli.py", "run.py"}
)
MAIN_GUARD = re.compile(r"""if\s+__name__\s*==\s*["']__main__["']""")
TODO_MARKER = re.compile(r"\b(TODO|FIXME|HACK)\b")
MAX_LISTED = 8


class RepoScanner(SandboxedTool):
    """Summarise the repository so the agents can talk about it with evidence."""

    def run(self, root: Path, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        files = list(iter_repo_files(root))
        if not files:
            return "The repository is empty, or contains only files that are skipped (vcs, caches, binaries)."

        relative = [relative_posix(root, path) for path in files]
        entry_points: List[str] = []
        todos: List[str] = []
        todo_total = 0

        for path, rel in zip(files, relative):
            if is_sensitive(path) or not is_text_file(path):
                continue
            lines = read_lines(path)
            if path.suffix == ".py":
                entry_points.extend(self._entry_points(path, rel, lines))
            for number, text in enumerate(lines, start=1):
                if TODO_MARKER.search(text):
                    todo_total += 1
                    if len(todos) < MAX_LISTED:
                        todos.append(f"  - {rel}:{number}: {text.strip()[:100]}")

        sections = [
            f"Repository: {root.name} ({len(files)} files scanned)",
            self._languages(files),
            self._layout(relative),
            self._key_files(relative),
            self._list_section("Entry points", entry_points),
            self._dependencies(root, files),
            self._tests(relative),
        ]
        if todos:
            sections.append(f"TODO/FIXME/HACK markers: {todo_total} (first {len(todos)})\n" + "\n".join(todos))
        return "\n".join(section for section in sections if section)

    @staticmethod
    def _languages(files: List[Path]) -> str:
        counts = Counter((path.suffix.lower() or "(no extension)") for path in files)
        top = ", ".join(f"{suffix}: {count}" for suffix, count in counts.most_common(6))
        return f"File types: {top}"

    @staticmethod
    def _layout(relative: List[str]) -> str:
        folders: Counter = Counter(rel.split("/")[0] for rel in relative if "/" in rel)
        root_files = [rel for rel in relative if "/" not in rel]
        lines = ["Top-level layout:"]
        lines += [f"  - {name}/ ({count} files)" for name, count in sorted(folders.items())]
        if root_files:
            lines.append("  - root files: " + ", ".join(root_files[:12]))
        return "\n".join(lines)

    @staticmethod
    def _key_files(relative: List[str]) -> str:
        found = [rel for rel in relative if rel.rsplit("/", 1)[-1].lower() in KEY_FILE_NAMES]
        return "Key files: " + ", ".join(found[:15]) if found else "Key files: none of the usual ones found"

    @staticmethod
    def _entry_points(path: Path, rel: str, lines: List[str]) -> List[str]:
        found = []
        if path.name in ENTRY_FILE_NAMES:
            found.append(f"  - {rel}:1 (conventional entry-point file name)")
        for number, text in enumerate(lines, start=1):
            if MAIN_GUARD.search(text):
                found.append(f"  - {rel}:{number} (__main__ guard: runnable script)")
        return found

    @staticmethod
    def _list_section(title: str, items: List[str]) -> str:
        if not items:
            return f"{title}: none detected"
        return f"{title}:\n" + "\n".join(items[:MAX_LISTED])

    @staticmethod
    def _dependencies(root: Path, files: List[Path]) -> str:
        lines: List[str] = []
        for path in files:
            name = path.name.lower()
            rel = relative_posix(root, path)
            if name.startswith("requirements") and name.endswith(".txt"):
                packages = [
                    re.split(r"[<>=!~\[; ]", entry.strip(), maxsplit=1)[0]
                    for entry in read_lines(path)
                    if entry.strip() and not entry.strip().startswith(("#", "-"))
                ]
                lines.append(f"  - {rel}: {', '.join(packages[:20])}")
            elif name == "package.json":
                try:
                    data = json.loads("\n".join(read_lines(path)))
                except json.JSONDecodeError:
                    continue
                dependencies = ", ".join(list(data.get("dependencies", {}))[:20])
                scripts = ", ".join(f"{key}={value}" for key, value in list(data.get("scripts", {}).items())[:5])
                lines.append(f"  - {rel}: dependencies [{dependencies}] scripts [{scripts}]")
        if not lines:
            return "Dependencies: no requirements.txt or package.json found"
        return "Dependencies:\n" + "\n".join(lines)

    @staticmethod
    def _tests(relative: List[str]) -> str:
        tests = [
            rel for rel in relative
            if re.search(r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_test\.py$|\.(test|spec)\.[jt]sx?$", rel)
        ]
        if not tests:
            return "Tests: none detected"
        return f"Tests: {len(tests)} file(s), e.g. " + ", ".join(tests[:5])
