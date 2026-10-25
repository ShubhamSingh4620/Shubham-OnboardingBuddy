"""CodedTool: CitationVerifier.

The grounding gate. The Onboarding Buddy must pass every ``path:line`` citation it intends to
show through this tool; citations that point to a missing file or a line beyond the end of the
file are reported as INVALID and have to be fixed or removed before the answer is sent.
"""

import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

from .repo_utils import SandboxError
from .repo_utils import SandboxedTool
from .repo_utils import read_lines
from .repo_utils import safe_join

CITATION = re.compile(r"(?P<path>[\w.\-/\\]+):(?P<start>\d+)(?:-(?P<end>\d+))?")


class CitationVerifier(SandboxedTool):
    """Verify path:line and path:start-end citations against the real repository."""

    def run(self, root: Path, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        text = str(args.get("citations", ""))
        citations = self._parse(text)
        if not citations:
            return "No path:line citations were found. Provide citations like app/auth.py:12 or app/auth.py:12-30."

        verified: List[str] = []
        invalid: List[str] = []
        for rel, start, end in citations:
            label = f"{rel}:{start}" + (f"-{end}" if end else "")
            problem = self._problem(root, rel, start, end)
            (invalid if problem else verified).append(f"{label} ({problem})" if problem else label)

        header = f"Citation check: {len(verified)} verified, {len(invalid)} INVALID."
        lines = [header]
        if verified:
            lines.append("VERIFIED: " + ", ".join(verified))
        if invalid:
            lines.append("INVALID: " + "; ".join(invalid))
            lines.append("ACTION REQUIRED: fix or remove the invalid citations, then run this check again.")
        else:
            lines.append("ALL CITATIONS VERIFIED: safe to include in the final answer.")
        return "\n".join(lines)

    @staticmethod
    def _parse(text: str) -> List[Tuple[str, int, int]]:
        seen = set()
        parsed: List[Tuple[str, int, int]] = []
        for match in CITATION.finditer(text):
            rel = match.group("path").replace("\\", "/")
            if rel.startswith("./"):
                rel = rel[2:]
            key = (rel, int(match.group("start")), int(match.group("end") or 0))
            if key not in seen:
                seen.add(key)
                parsed.append(key)
        return parsed

    @staticmethod
    def _problem(root: Path, rel: str, start: int, end: int) -> str:
        """Return a short description of what is wrong with a citation, or '' if it is valid."""
        try:
            target = safe_join(root, rel)
        except SandboxError:
            return "outside the repository"
        if not target.is_file():
            return "file not found"
        total = len(read_lines(target))
        if start < 1 or start > total:
            return f"line {start} does not exist, file has {total} lines"
        if end and (end < start or end > total):
            return f"range end {end} is invalid, file has {total} lines"
        return ""
