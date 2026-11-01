# GuideForge — 100% Open-Source Client & Developer Manual Generator + Polyglot Code Runner

**GuideForge** is a 100% open-source command-line tool (`uv` Python project) that turns a single declarative YAML file (`guide.yaml`) and a local project into **narrated video walkthroughs** and **written manuals** tailored for **both non-technical clients and technical developers**—with native polyglot code detection and execution across **Node.js/TypeScript, Python, Go, Rust, and Bash**.

## Key Highlights

1. **100% Open-Source, Zero Commercial Copyright Restrictions**:
   - Every library and runtime tool is open-source (`MIT`, `Apache-2.0`, `BSD`, `HPND`, `MPL-2.0`, `LGPL/GPL`).
   - Uses local open-source neural and speech synthesis engines (**Piper TTS**, **Kokoro ONNX**, **eSpeak-NG**, **Coqui TTS**, **pyttsx3**) with zero proprietary cloud lock-in or per-character fees.
   - Run `uv run guideforge licenses` anytime to audit the full open-source compliance table.
2. **Built for Both Clients & Developers (`audience: "client" | "developer" | "both"`)**:
   - **For Non-Technical Clients**: Plain, friendly step-by-step instructions, numbered annotated screenshots, visual *Tip/Note/Warning* callout boxes, and narrated MP4 videos with large captions.
   - **For Developers**: Auto-detected project stack tables, architecture notes, runnable polyglot code blocks, and live captured `stdout`/`stderr` terminal cards embedded directly into the manual and video frames.
3. **Polyglot Stack Detection & Code Execution (Node.js, Python, Go, Rust, Bash)**:
   - **Stack Inspector (`guideforge stack`)**: Detects `package.json` / `tsconfig.json` (Node/TS), `pyproject.toml` / `uv.lock` (Python), `go.mod` (Go), and `Cargo.toml` (Rust), along with frameworks and installed compiler versions.
   - **Universal Code Runner (`guideforge exec` & step `code_block`)**: Executes inline snippets or source files across **Node.js**, **Python**, **Go**, **Rust**, and **Bash**, capturing real execution output and timing.
   - **Auto App Server Manager (`app_server`)**: Automatically boots your local Node, Python, Go, or Rust web server, waits for `ready_url` to respond, records the browser walkthrough, and shuts the server down cleanly.

## Project Structure (`uv` Package Layout)

```text
guideforge/
├── pyproject.toml               # 100% open-source PEP 621 metadata & uv config
├── .python-version              # Pinned Python version (3.11) for uv
├── .gitignore                   # Standard Python, uv, and media build ignores
├── AGENTS.md                    # Antigravity CLI agent architecture & dev handbook
├── README.md                    # Installation, gh CLI setup & polyglot usage guide
├── examples/
│   └── guide.yaml               # Sample dual-audience (Client + Dev) polyglot config
├── docs/
│   └── ARCHITECTURE.md          # Pipeline data-flow and polyglot execution spec
├── scripts/
│   └── publish_github.sh        # One-command GitHub creation & push via `gh` CLI
├── .github/workflows/
│   └── ci.yml                   # GitHub Actions CI running uv, ruff, and pytest
├── src/guideforge/
│   ├── ui_controller.py         # NiceGUI web dashboard + `/api/v1/*` multi-agent REST controller
│   ├── browser_agent.py         # Open-source `browser-use` (CDP) + local Ollama agent runner
│   ├── __init__.py              # Package exports & version (0.2.0)
│   ├── __main__.py              # Allows `python3 -m guideforge`
│   ├── cli.py                   # CLI entry point (`guideforge` command)
│   ├── config.py                # Dataclasses, license manifest & jargon linter
│   ├── polyglot.py              # Stack detector & Node/Python/Go/Rust code runner
│   ├── recorder.py              # Playwright automation, cursor JS & terminal overlay
│   ├── voice.py                 # Open-source local TTS (Piper/Kokoro/eSpeak-NG) & SRT/VTT
│   ├── video.py                 # FFmpeg video composition, cards & audio ducking
│   ├── exporter.py              # Client, Developer & Dual-Audience HTML/MD/PDF/DOCX exporter
│   └── utils.py                 # Shared media, font, and timestamp helpers
└── tests/
    └── test_guideforge.py       # Unit & polyglot execution test suite
```

## Quick Start with `uv`

```bash
# 1. Sync virtual environment (and optional local TTS extras)
uv sync --all-groups

# 2. Install Playwright's open-source Chromium browser
uv run playwright install chromium
```

### CLI Commands (Interactive & Antigravity CLI Ready)

| Command | Description |
| :--- | :--- |
| `uv run guideforge discover --url http://localhost:3000 --goal "..."` | Uses open-source **`browser-use`** (`MIT`) + local **Ollama (`ChatOllama`)** to autonomously explore your app and generate `guide.yaml`. |
| `uv run guideforge ui --port 8080` | Launches the **NiceGUI Web Studio** (`http://127.0.0.1:8080`) + `/api/v1/*` agent control plane. |
| `uv run guideforge control <action> --json` | Controls a running NiceGUI instance (or `--local` controller) from **Antigravity CLI** or any other CLI agent. |
| `uv run guideforge agent-manifest --json` | Emits the universal JSON capability & endpoint schema for any CLI coding agent. |
| `uv run guideforge init` | Creates a starter `guide.yaml` with client steps and polyglot developer code blocks. |
| `uv run guideforge validate examples/guide.yaml` | Validates schema, open-source TTS config, polyglot languages, and client jargon rules. |
| `uv run guideforge stack .` | Inspects any project folder to detect Node.js, Python, Go, and Rust stacks and runtimes. |
| `uv run guideforge exec -l rust 'fn main(){println!("Hi");}'` | Compiles and runs code in `python`, `node`, `typescript`, `go`, `rust`, or `bash`. |
| `uv run guideforge licenses` | Prints the open-source license compliance table (zero commercial restrictions). |
| `uv run guideforge export examples/guide.yaml --audience client` | Exports a clean, non-technical Client Manual (HTML, PDF, DOCX, Markdown). |
| `uv run guideforge export examples/guide.yaml --audience developer` | Exports a technical Developer Manual with stack tables and live code outputs. |
| `uv run guideforge all examples/guide.yaml` | Runs the complete pipeline (`validate` → `voice` → `record` → `render`) for both audiences. |

## Publishing to GitHub with the `gh` CLI

```bash
# Option A: Run the bundled helper script
./scripts/publish_github.sh guideforge --public

# Option B: Run git + gh directly
git init -b main
git add -A
git commit -m "feat: open-source GuideForge uv project with polyglot Node/Python/Go/Rust support"
gh repo create guideforge --public --source=. --remote=origin --push
```
