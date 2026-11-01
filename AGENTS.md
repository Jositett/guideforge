# AGENTS.md — Antigravity CLI Development & Orchestration Handbook

This repository is structured as a **100% open-source `uv` Python project** (`src/guideforge` layout) built for both **non-technical clients** and **technical developers**, with built-in polyglot code execution across **Node.js/TypeScript, Python, Go, Rust, and Bash**.

## 1. Quick Commands for Antigravity CLI

| Task | Command | 
| ----- | ----- | 
| **Install / Sync Environment** | `uv sync --all-groups` | 
| **Install Optional Open-Source TTS** | `uv sync --extra tts` | 
| **Install `browser-use` + Ollama Agent** | `uv sync --extra agent` | 
| **Install NiceGUI Web Frontend** | `uv sync --extra ui` | 
| **Launch NiceGUI Web Studio & API** | `uv run guideforge ui --port 8080` | 
| **Emit Universal CLI Agent Schema** | `uv run guideforge agent-manifest --json` | 
| **Remote-Control NiceGUI from CLI Agent** | `uv run guideforge control --server http://127.0.0.1:8080 status --json` | 
| **Auto-Discover Workflow via `browser-use`** | `uv run guideforge discover --url http://localhost:3000 --goal "Sign in" --json` | 
| **Install Browser Binary** | `uv run playwright install chromium` | 
| **Inspect Project Code Stack** | `uv run guideforge stack . --json` | 
| **Execute Polyglot Code Snippet** | `uv run guideforge exec -l python "print('Hello')" --json` | 
| **Audit Open-Source Licenses** | `uv run guideforge licenses --json` | 
| **Validate Config (JSON mode)** | `uv run guideforge validate examples/guide.yaml --json` | 
| **Run Full Pipeline (JSON mode)** | `uv run guideforge all examples/guide.yaml --json` | 
| **Export Client-Only Manual** | `uv run guideforge export examples/guide.yaml --audience client --json` | 
| **Export Developer-Only Manual** | `uv run guideforge export examples/guide.yaml --audience developer --json` | 
| **Run Unit & Polyglot Tests** | `uv run pytest` | 
| **Lint & Format Check** | `uv run ruff check src tests` | 

## 2. Package Architecture (`src/guideforge/`)

* **`src/guideforge/config.py`**: Dataclasses (`GuideConfig`, `GuideStep`, `CodeSnippet`, `AppServerConfig`, `BrandingConfig`, `TTSConfig`, `VideoConfig`, `CalloutBox`), `OPEN_SOURCE_LICENSE_MANIFEST`, schema validator, and client-jargon linter.

* **`src/guideforge/polyglot.py`**:

  * `PolyglotStackDetector`: Automatically inspects any repository to detect **Node.js/TypeScript**, **Python**, **Go**, and **Rust** manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`), frameworks, package managers, and installed host runtime versions.

  * `PolyglotCodeRunner`: Executes code blocks or files in **Node.js (`node`/`tsx`)**, **Python (`python3`)**, **Go (`go run`)**, **Rust (`rustc`)**, and **Bash (`bash`)**, capturing live `stdout`, `stderr`, exit code, and execution latency (`ms`).

  * `AppServerLifecycle`: Context manager that boots, health-checks, and tears down local Node, Python, Go, or Rust dev servers during recording.

* **`src/guideforge/browser_agent.py`**: `BrowserUseRunner` class integrating [`browser-use`](https://github.com/browser-use/browser-use) (`MIT` license) with local open-source LLMs via **Ollama (`ChatOllama`)**. Supports autonomous `action: "agent_task"` steps and `guideforge discover` to auto-generate `guide.yaml` from a plain-language goal.

* **`src/guideforge/recorder.py`**: `BrowserRecorder` class. Orchestrates Playwright Chromium, smooth cursor/ripple/zoom JS, polyglot step execution, and Pillow screenshot annotation (including a bottom-right developer terminal card when `audience` is `developer` or `both`).

* **`src/guideforge/voice.py`**: `NarrationEngine` class. Uses **100% open-source local TTS engines** (`piper` MIT, `kokoro` Apache-2.0, `espeak-ng` GPLv3, `coqui` MPL-2.0, `pyttsx3` MPL-2.0) with zero commercial cloud API dependencies, plus `.srt` and `.vtt` subtitle generation.

* **`src/guideforge/video.py`**: `VideoProducer` class. Renders 1080p/4K branded intro/outro cards, stitches segments via FFmpeg, applies `sidechaincompress` audio ducking, and burns subtitles.

* **`src/guideforge/exporter.py`**: `WrittenGuideExporter` class. Produces **Client**, **Developer**, or **Dual-Audience (`both`)** manuals in HTML, Markdown, PDF, and DOCX—embedding both plain-language steps for clients and detected stack tables + verified polyglot code outputs for developers.

* **`src/guideforge/ui_controller.py`**: `GuideForgeController` + `launch_nicegui_controller()` built on [`NiceGUI`](https://github.com/zauberzeug/nicegui) (`MIT` license) and FastAPI. Serves an interactive 4-tab web dashboard at `/` alongside a synchronized `/api/v1/*` JSON control plane so **Antigravity CLI, Claude Code, Codex, Gemini CLI, Aider, Cursor, or OpenClaw** can drive the pipeline headlessly or co-pilot the live frontend.

* **`src/guideforge/cli.py`**: CLI router supporting `init`, `validate`, `stack`, `exec`, `licenses`, `voice`, `record`, `export`, `render`, `all`, and `run`.

## 3. Open-Source Policy Guardrail for Agents

When adding new dependencies in `pyproject.toml`, **only** use OSI-approved open-source packages without commercial copyright restrictions (MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL/GPL). Never introduce closed-source SDKs or mandatory paid cloud APIs.