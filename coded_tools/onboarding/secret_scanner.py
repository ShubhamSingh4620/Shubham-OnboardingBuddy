"""CodedTool: SecretScanner.

Scans the whole repository for hardcoded credentials.

Data-flow design (the point of using Sly-Data here):
  * The raw secret value is used only inside this function to compute a short fingerprint and a
    redacted preview. It is never returned, logged or stored.
  * The chat stream (what the LLM sees) gets only ``file:line``, the kind of secret and a fingerprint.
  * The structured report with redacted previews is written to ``sly_data["secret_findings"]``,
    the private channel that the network's ``allow.to_upstream`` policy delivers to the client UI.
"""

import hashlib
import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

from .repo_utils import SandboxedTool
from .repo_utils import is_sensitive
from .repo_utils import is_text_file
from .repo_utils import iter_repo_files
from .repo_utils import read_lines
from .repo_utils import relative_posix

SECRET_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("API key assignment", re.compile(r"(?i)api[_-]?key\w*\s*[:=]\s*[\"']([^\"'\s]{16,})[\"']")),
    ("Secret/token assignment", re.compile(r"(?i)[\w-]*(?:secret|token)[\w-]*\s*[:=]\s*[\"']([^\"'\s]{16,})[\"']")),
    ("Hardcoded password", re.compile(r"(?i)(?:password|passwd|pwd)\w*\s*[:=]\s*[\"']([^\"']{4,})[\"']")),
    ("Password inside a connection URL", re.compile(r"[a-z][a-z0-9+.-]*://[^\s:/@]+:([^\s@]{3,})@")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("Secret in .env-style line", re.compile(r"(?m)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*=(\S{8,})$")),
)
PLACEHOLDER = re.compile(r"(?i)(change.?me|example|your[_-]|<.+>|x{4,}|placeholder|dummy|\$\{|os\.environ|getenv)")
MAX_FINDINGS = 100
MAX_LISTED_IN_CHAT = 15


class SecretScanner(SandboxedTool):
    """Report where credentials are hardcoded, without ever exposing their values."""

    def run(self, root: Path, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        findings: List[Dict[str, str]] = []
        for path in iter_repo_files(root):
            if len(findings) >= MAX_FINDINGS:
                break
            findings.extend(self._scan_file(path, relative_posix(root, path)))

        sly_data["secret_findings"] = findings
        return self._summarise(findings)

    def _scan_file(self, path: Path, rel: str) -> List[Dict[str, str]]:
        """Findings for one file: the file itself if it is a credentials file, plus any secret lines."""
        findings: List[Dict[str, str]] = []
        if is_sensitive(path):
            findings.append(self._finding(rel, 1, "Credentials file committed to the repository", path.name))
        if not is_text_file(path):
            return findings
        for number, text in enumerate(read_lines(path), start=1):
            for label, pattern in SECRET_PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                value = match.group(1) if match.groups() else match.group(0)
                if PLACEHOLDER.search(value):
                    continue
                findings.append(self._finding(rel, number, label, value))
                break  # one finding per line is enough
        return findings

    @staticmethod
    def _summarise(findings: List[Dict[str, str]]) -> str:
        """Chat-safe summary: locations, kinds and fingerprints only."""
        if not findings:
            return "Secret scan complete: no hardcoded credentials detected."
        files = {finding["file"] for finding in findings}
        lines = [
            f"Secret scan complete: {len(findings)} potential secret(s) in {len(files)} file(s). "
            "Values are withheld; only locations are shown."
        ]
        for finding in findings[:MAX_LISTED_IN_CHAT]:
            lines.append(
                f"  - {finding['file']}:{finding['line']}  {finding['type']}  (fingerprint {finding['fingerprint']})"
            )
        if len(findings) > MAX_LISTED_IN_CHAT:
            lines.append(f"  ... and {len(findings) - MAX_LISTED_IN_CHAT} more")
        lines.append("A redacted structured report was delivered to the client through Sly-Data.")
        lines.append(
            "Recommended fix: rotate these credentials, purge them from git history, "
            "load them from environment variables."
        )
        return "\n".join(lines)

    @staticmethod
    def _finding(rel: str, line: int, kind: str, value: str) -> Dict[str, str]:
        """Build a finding holding a fingerprint and a redacted preview, never the value itself."""
        return {
            "file": rel,
            "line": str(line),
            "type": kind,
            "fingerprint": hashlib.sha256(value.encode("utf-8")).hexdigest()[:10],
            "preview": f"{value[:2]}{'*' * 8}" if len(value) > 4 else "*" * 8,
        }
