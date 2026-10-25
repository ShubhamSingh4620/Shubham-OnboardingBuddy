"""Check every entry of the LLM fallback chain with one tiny live call each.

The app's fallback chain hides WHY a model failed: when every entry fails, only the first entry's error is
shown. Run this script to see the real status of each entry:

    python scripts/check_providers.py

It reads the same ``config/llm_config.hocon`` and ``.env`` as the app, so a green line here means that entry
will work in the app. Retries are switched off so a dead entry reports immediately.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

from dotenv import load_dotenv
from pyhocon import ConfigFactory

from neuro_san.internals.run_context.langchain.llms.default_llm_factory import DefaultLlmFactory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "llm_config.hocon"
PROMPT = "Reply with the single word OK."
TIMEOUT_SECONDS = 60
MESSAGE_WIDTH = 170

# (lower-case text found in the error, advice). The first match wins, so specific markers come first.
ADVICE = (
    ("credit_balance_exhausted", "No credits left on this account. Add credits, or move this entry to the end."),
    ("insufficient_quota", "Quota or credits exhausted on this account. Add credits, or move this entry to the end."),
    ("resource_exhausted", "Free-tier quota for this model is used up (per-minute or per-day cap). Wait, rely on"
                           " the other entries, use a key from another project, or enable billing."),
    ("not_found", "This key cannot use that model name. Delete the entry or change model_name."),
    ("rate limit", "Rate limited. Wait a minute; this entry works but is being throttled."),
    ("401", "The API key was rejected. Check the value in .env."),
    ("403", "The API key is not allowed to use this model."),
    ("api key", "The API key is missing or invalid. Check .env."),
    ("connect", "Network problem: check your internet connection, VPN or firewall."),
    ("timed out", "No answer within the time limit. The provider may be overloaded."),
)


def explain(error_text: str) -> str:
    """Turn a provider error message into a one-line suggestion."""
    lowered = error_text.lower()
    for marker, advice in ADVICE:
        if marker in lowered:
            return advice
    return "Unrecognised error: read the message above."


def label(entry: Dict[str, Any]) -> str:
    """Short human-readable name for a chain entry."""
    provider = str(entry.get("class", "?")).rsplit(".", 1)[-1]
    return f"{provider} / {entry.get('model_name', '?')}"


async def check_entry(factory: DefaultLlmFactory, entry: Dict[str, Any]) -> str:
    """Make one tiny call to one entry. Returns '' when it works, otherwise the error text."""
    single = dict(entry)
    single["max_retries"] = 0
    try:
        resources = factory.create_llm_with_fallbacks(single, {})
        if isinstance(resources, dict):
            return "Could not build the model. Is the API key set in .env and the provider package installed?"
        reply = await asyncio.wait_for(resources.get_model().ainvoke(PROMPT), TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return "timed out"
    except Exception as error:  # pylint: disable=broad-exception-caught
        return f"{type(error).__name__}: {error}"
    return "" if getattr(reply, "content", reply) else "The model returned an empty answer."


async def main() -> int:
    """Check every entry in order and print a report. Exit code 0 if at least one entry works."""
    load_dotenv(PROJECT_ROOT / ".env")
    chain = ConfigFactory.parse_file(str(CONFIG_PATH))["llm_config"]["fallbacks"]
    entries: List[Dict[str, Any]] = [dict(item) for item in chain]
    factory = DefaultLlmFactory()
    factory.load()

    print(f"Checking {len(entries)} entries from {CONFIG_PATH.name} with one tiny live call each...\n")
    working: List[int] = []
    for number, entry in enumerate(entries, start=1):
        started = time.monotonic()
        problem = await check_entry(factory, entry)
        seconds = time.monotonic() - started
        if problem:
            one_line = " ".join(problem.split())[:MESSAGE_WIDTH]
            print(f"{number}. {label(entry):<42} FAILED  ({seconds:.1f}s)\n     {one_line}\n     -> {explain(problem)}")
        else:
            working.append(number)
            print(f"{number}. {label(entry):<42} OK      ({seconds:.1f}s)")

    print(f"\n{len(working)} of {len(entries)} entries work.")
    if working:
        print(f"The app will use entry {working[0]} first, and fall back to the others in order.")
        return 0
    print("No entry works: the app cannot answer. Fix at least one key above.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
