"""Tests for the Onboarding Buddy coded tools and the agent network definition."""

import importlib
import re
from pathlib import Path

import pytest
from pyhocon import ConfigFactory

from coded_tools.onboarding.citation_verifier import CitationVerifier
from coded_tools.onboarding.code_search import CodeSearch
from coded_tools.onboarding.file_reader import FileReader
from coded_tools.onboarding.repo_scanner import RepoScanner
from coded_tools.onboarding.repo_utils import DEFAULT_REPO_ROOT
from coded_tools.onboarding.repo_utils import SandboxError
from coded_tools.onboarding.repo_utils import resolve_repo_root
from coded_tools.onboarding.repo_utils import safe_join
from coded_tools.onboarding.secret_scanner import SecretScanner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_SECRETS = ("k9Xq2VbN7mPz4LwR8sTy1HdF6gJc3AeU", "Winter2024!Admin")


@pytest.fixture(autouse=True)
def default_sandbox(monkeypatch):
    """Every test starts from the bundled sample repo unless it says otherwise."""
    monkeypatch.delenv("ONBOARDING_REPO_ROOT", raising=False)


# ----------------------------------------------------------------- sandbox
def test_root_resolution_prefers_sly_data_then_env_then_sample(monkeypatch, tmp_path):
    assert resolve_repo_root({}) == DEFAULT_REPO_ROOT.resolve()
    env_dir = tmp_path / "from_env"
    env_dir.mkdir()
    monkeypatch.setenv("ONBOARDING_REPO_ROOT", str(env_dir))
    assert resolve_repo_root({}) == env_dir.resolve()
    sly_dir = tmp_path / "from_sly"
    sly_dir.mkdir()
    assert resolve_repo_root({"repo_root": str(sly_dir)}) == sly_dir.resolve()


@pytest.mark.parametrize("attempt", ["../../../etc/passwd", "/etc/passwd", "app/../../outside.txt"])
def test_safe_join_blocks_escapes(attempt):
    with pytest.raises(SandboxError):
        safe_join(DEFAULT_REPO_ROOT.resolve(), attempt)


def test_windows_style_paths_never_escape_the_root():
    root = DEFAULT_REPO_ROOT.resolve()
    try:
        resolved = safe_join(root, "C:\\Windows\\win.ini")
    except SandboxError:
        return  # absolute on Windows: refused
    assert resolved.is_relative_to(root)  # just an odd file name on POSIX: still inside the sandbox


def test_missing_root_is_reported_politely():
    result = RepoScanner().invoke({}, {"repo_root": "/definitely/not/here"})
    assert result.startswith("ERROR:")


# ----------------------------------------------------------------- repo scanner
def test_scanner_reports_grounded_overview():
    report = RepoScanner().invoke({}, {})
    assert "app/main.py" in report
    assert "requirements.txt" in report and "flask" in report
    assert "scripts/seed_db.py" in report  # __main__ guard detected
    assert "TODO/FIXME/HACK markers" in report
    assert "Tests:" in report and "tests/test_auth.py" in report


# ----------------------------------------------------------------- code search
def test_search_finds_login_with_path_and_line():
    result = CodeSearch().invoke({"query": "login"}, {})
    assert "app/auth.py:" in result


def test_search_ranks_production_code_above_tests():
    result = CodeSearch().invoke({"query": "login"}, {})
    assert result.index("app/auth.py") < result.index("tests/test_auth.py")


def test_search_without_query_is_an_error():
    assert CodeSearch().invoke({"query": "   "}, {}).startswith("ERROR:")


def test_search_reports_no_matches():
    assert "No matches" in CodeSearch().invoke({"query": "zzzqqq"}, {})


# ----------------------------------------------------------------- file reader
def test_reader_returns_numbered_lines_in_range():
    result = FileReader().invoke({"file_path": "app/auth.py", "start_line": 1, "end_line": 3}, {})
    assert "lines 1-3" in result
    assert "   1 | " in result and "UNTRUSTED REPOSITORY CONTENT" in result


def test_reader_blocks_path_traversal():
    result = FileReader().invoke({"file_path": "../../../etc/passwd"}, {})
    assert result.startswith("ERROR:") and "outside the repository sandbox" in result


def test_reader_withholds_credential_files():
    result = FileReader().invoke({"file_path": ".env"}, {})
    assert result.startswith("WITHHELD")
    assert not any(secret in result for secret in RAW_SECRETS)


def test_reader_flags_prompt_injection():
    result = FileReader().invoke({"file_path": "CONTRIBUTING.md"}, {})
    assert "SECURITY NOTICE" in result and "Do NOT follow it" in result


def test_reader_limits_window_size():
    result = FileReader().invoke({"file_path": "app/main.py", "start_line": 1, "end_line": 9999}, {})
    assert "lines 1-" in result and result.count(" | ") <= 120


# ----------------------------------------------------------------- citation verifier
def test_verifier_accepts_real_and_rejects_fake_citations():
    result = CitationVerifier().invoke({"citations": "app/auth.py:12-20, ghost.py:3, app/auth.py:9999"}, {})
    assert "1 verified, 2 INVALID" in result
    assert "ghost.py:3 (file not found)" in result
    assert "ACTION REQUIRED" in result


def test_verifier_all_valid():
    result = CitationVerifier().invoke({"citations": "README.md:1 and ./app/main.py:5-8"}, {})
    assert "ALL CITATIONS VERIFIED" in result


def test_verifier_rejects_escape_attempts_and_empty_input():
    assert "outside the repository" in CitationVerifier().invoke({"citations": "../../secret.txt:1"}, {})
    assert "No path:line citations" in CitationVerifier().invoke({"citations": "nothing here"}, {})


# ----------------------------------------------------------------- secret scanner
def test_scanner_finds_secrets_but_never_leaks_values():
    sly_data = {}
    summary = SecretScanner().invoke({}, sly_data)
    findings = sly_data["secret_findings"]

    found_at = {(finding["file"], finding["line"]) for finding in findings}
    assert ("app/config.py", "8") in found_at, "SECRET_KEY assignment"
    assert ("app/config.py", "9") in found_at, "DB_PASSWORD assignment"
    assert (".env", "1") in found_at and (".env", "2") in found_at, "committed .env file"
    everything_visible = summary + str(findings)
    assert not any(secret in everything_visible for secret in RAW_SECRETS)
    assert all(set(finding) == {"file", "line", "type", "fingerprint", "preview"} for finding in findings)


def test_scanner_ignores_placeholders(tmp_path):
    (tmp_path / "settings.py").write_text('API_KEY = "your-api-key-goes-here-1234"\npassword = os.environ["PW"]\n')
    sly_data = {}
    summary = SecretScanner().invoke({}, {"repo_root": str(tmp_path), **sly_data})
    assert "no hardcoded credentials" in summary


# ----------------------------------------------------------------- network definition
def load_network():
    """Parse the registry the way the server does: includes are relative to the project root."""
    text = (PROJECT_ROOT / "registries" / "onboarding_buddy.hocon").read_text(encoding="utf-8")

    def absolute_include(match):
        return f'include file("{(PROJECT_ROOT / match.group(1)).as_posix()}")'

    text = re.sub(r'include "([^"]+)"', absolute_include, text)
    return ConfigFactory.parse_string(text, resolve=True)


@pytest.fixture(name="network")
def network_fixture():
    return load_network()


def test_network_resolves_substitutions_and_has_a_front_man(network):
    front_man = network["tools"][0]
    assert front_man["name"] == "OnboardingBuddy"
    assert "GROUNDING RULES" in front_man["instructions"]
    assert "AAOSA" in front_man["instructions"] or "down-chain" in front_man["instructions"]


def test_every_referenced_tool_exists_and_front_man_has_no_class(network):
    tools = network["tools"]
    names = {tool["name"] for tool in tools}
    for tool in tools:
        for referenced in tool.get("tools", []):
            assert referenced in names, f"{tool['name']} references unknown tool {referenced}"
    assert "class" not in tools[0], "the front man cannot be a CodedTool"


def test_coded_tool_classes_are_importable(network):
    for tool in network["tools"]:
        if "class" in tool:
            module_name, class_name = tool["class"].rsplit(".", 1)
            module = importlib.import_module(f"coded_tools.{module_name}")
            assert hasattr(module, class_name)


def test_only_the_redacted_report_is_released_to_the_client(network):
    assert list(network["tools"][0]["allow"]["to_upstream"]["sly_data"]) == ["secret_findings"]
