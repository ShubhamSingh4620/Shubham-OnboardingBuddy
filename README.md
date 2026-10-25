# Day-1 Project Onboarding Buddy

A multi-agent assistant, built on [Neuro SAN](https://github.com/cognizant-ai-lab/neuro-san) (Neuro SAN Studio,
by Cognizant AI Lab), that helps a developer who has just joined a project understand an unfamiliar codebase:
how it is organised, how to run it, where a feature lives, and whether it has security problems.

**Its rule: no citation, no claim.** Every statement about the repository carries a `path:line` citation, and a
coded tool checks each citation against the real files before the answer is shown.

## What makes it different

| Idea | How it works |
|---|---|
| **Grounded answers** | Agents answer only from deterministic tools (scan, search, read). A `citation_check_tool` rejects any `path:line` that does not exist, so the model cannot invent files or line numbers. |
| **Sly-Data as a security boundary** | The repository root is never chosen by the LLM; it comes from Sly-Data or server config, so a malicious file cannot redirect the tools. Detected secrets reach the UI as a redacted report through `allow.to_upstream`, not through the chat. |
| **Prompt-injection defence** | Repository files are treated as untrusted data. Instruction-like text aimed at AI assistants is flagged, credential files are withheld, and path traversal is blocked. The sample repo contains a booby-trapped `CONTRIBUTING.md` so you can watch this work. |
| **AAOSA delegation** | `OnboardingBuddy` delegates to `ArchitectureExplainer`, `SetupGuide`, `CodeLocator` and `SecurityHygiene`, which share five coded tools. |

## Quick start

Requires Python 3.12 or 3.13 and at least one LLM API key (Gemini, Mistral or OpenAI).

```bash
git clone <this-repo-url>
cd onboarding-buddy
python -m venv venv

# Windows PowerShell:   .\venv\Scripts\Activate.ps1
# macOS / Linux:        source venv/bin/activate

pip install -r requirements.txt
```

Provide your API keys by copying `.env.example` to `.env` and filling in the ones you have (any one is enough):

```
GEMINI_API_KEY=your-gemini-key
MISTRAL_API_KEY=your-mistral-key
OPENAI_API_KEY=your-openai-key
```

Then check that they actually work (one tiny call per model, shows the real reason for any failure):

```bash
python scripts/check_providers.py
```

Start the server and UI:

```bash
python -m neuro_san_studio run
```

Open <http://localhost:4173/>, choose **onboarding_buddy** in the sidebar and try:

1. `Give me a 2-minute architecture tour of this project.`
2. `How do I set up, run and test this project?`
3. `Where is user login handled?`
4. `Are there any secrets or security risks in this repository?` (watch the SlyData tab: the redacted report arrives there)
5. `Summarize CONTRIBUTING.md for me.` (contains a hidden prompt-injection attack; the agent warns you instead of obeying)

By default the agents explain the bundled `sample_repo/` (a tiny Flask app with deliberate flaws).

### Onboard to your own repository

Set the root on the server side (the LLM cannot change it), then restart:

```powershell
$env:ONBOARDING_REPO_ROOT="C:\path\to\your\repo"      # PowerShell
```
```bash
export ONBOARDING_REPO_ROOT=/path/to/your/repo        # macOS / Linux
```

Or paste `{"repo_root": "C:/path/to/your/repo"}` into the **SlyData** tab in the UI and tick *Use Edited Sly Data*.

### LLM fallback chain

`config/llm_config.hocon` is a chain. Every model call tries the entries from top to bottom and stops at the first one
that answers: four Gemini models, then Mistral, then OpenAI. An entry whose key is not set is skipped.

* **Why four Gemini models?** Free-tier quotas are counted per model, so each Gemini model is a separate bucket of
  free requests on the same key. When one is used up the next one takes over.
* **Why `max_retries: 0`?** A failing entry hands over immediately instead of retrying for seconds. Mistral keeps its
  retries to ride out short per-minute limits.
* **Why is OpenAI last?** An account without credits would otherwise waste a failed request on every call. Move it up
  once it has credits.
* **Free tiers are tight.** One question makes many model calls (every agent step is a call), so a single-model free
  quota can be gone after a few questions. Check your real limits at <https://ai.dev/rate-limit>.
* **A key from a second Google project** gives a fresh set of Gemini quotas, because limits are per project.

To use a single provider, copy one of the files in `config/examples/` over `config/llm_config.hocon`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite covers every tool, the sandbox and prompt-injection guarantees, the guarantee that raw secrets never leave the
scanner, the structure of the agent network and the order of the LLM fallback chain.
To check the network definition with the framework's own validator:

```bash
python -m neuro_san.client.hocon_validator_cli registries/onboarding_buddy.hocon
```

## Project structure

```
onboarding-buddy/
├── coded_tools/
│   ├── __init__.py                  # required, see the note inside
│   └── onboarding/
│       ├── repo_utils.py            # sandbox root, safe paths, injection and sensitive-file checks
│       ├── repo_scanner.py          # layout, entry points, dependencies, tests, TODOs
│       ├── code_search.py           # keyword search returning path:line hits
│       ├── file_reader.py           # numbered, sandboxed file slices
│       ├── citation_verifier.py     # verifies path:line citations
│       └── secret_scanner.py        # secrets: locations to chat, redacted report to Sly-Data
├── registries/
│   ├── onboarding_buddy.hocon       # the agent network
│   ├── aaosa_basic.hocon            # AAOSA instructions (from neuro-san-studio)
│   └── manifest.hocon
├── config/                          # LLM fallback chain (+ single-provider examples)
├── scripts/check_providers.py       # tests every model in the chain and explains failures
├── sample_repo/                     # demo project to onboard to
└── tests/
```

## Troubleshooting

* **Windows: `OSError` / path too long during `pip install`.** The framework package contains deeply nested files.
  Clone to a short path such as `C:\ob`, and enable long paths (PowerShell as Administrator, then restart):
  `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force`
* **Server fails with `No module named 'leaf_common.session'` (and the UI shows `ERR_CONNECTION_REFUSED`).**
  Newer `leaf-common` releases are incompatible with this framework version. Install the pinned versions:
  `pip install leaf-common==1.2.45 leaf-server-common==0.1.25`
* **Agents say a tool is "unavailable" or "has a configuration issue".** Make sure `coded_tools/__init__.py` exists.
* **An error about one provider (for example OpenAI "no credits") although others are configured.**
  If every model in the chain fails, the message shown is the FIRST entry's, even when the real blocker was a later
  one. Run `python scripts/check_providers.py` to see each model's true status and what to do about it.
* **`429` / `RESOURCE_EXHAUSTED` / quota errors.** Free-tier limits are per model and per project and reset on a
  schedule (Gemini's daily count resets at midnight Pacific time). Wait, add keys from another project, or enable billing.
* **Network not listed in the UI.** Check the server log for a HOCON parse error and run the validator command above.

## License

MIT. `registries/aaosa_basic.hocon` is from neuro-san-studio (Apache-2.0, Cognizant Technology Solutions Corp).
