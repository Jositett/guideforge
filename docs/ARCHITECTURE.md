# GuideForge Architecture & Polyglot Execution Specification

## 1. Open-Source Stack Guarantee

GuideForge uses strictly OSI-approved open-source libraries and tools:
- **Browser Automation**: Playwright (`Apache-2.0`) driving Chromium (`BSD-3-Clause`).
- **Voice Synthesis**: Local **Piper TTS** (`MIT`), **Kokoro ONNX** (`Apache-2.0`), **eSpeak-NG** (`GPL-3.0+`), or **Coqui TTS** (`MPL-2.0`).
- **Video & Audio Processing**: **FFmpeg** (`LGPL/GPL`) + **Pillow** (`HPND`).
- **Document Generation**: Native HTML5/CSS3, Markdown, Chromium HTML-to-PDF, and `python-docx` (`MIT`).

## 2. Dual-Audience + Polyglot Data Flow

1. **Stack Inspection (`PolyglotStackDetector`)**: Scans `project_dir` for `pyproject.toml`/`uv.lock` (Python), `package.json`/`tsconfig.json` (Node/TS), `go.mod` (Go), and `Cargo.toml` (Rust).
2. **Polyglot Snippet Execution (`PolyglotCodeRunner`)**: Executes each step's `code_block` in its target runtime (`python3`, `node`/`tsx`, `go run`, `rustc`, `bash`) and records `stdout`, `stderr`, exit code, and duration in `recording_manifest.json`.
3. **App Server Lifecycle (`AppServerLifecycle`)**: Optionally starts the user's web server (`npm run dev`, `uv run ...`, `go run .`, `cargo run`) and polls `ready_url` before launching headless Chromium.
4. **Dual-Mode Rendering**:
   - `--audience client`: Strips code blocks and developer notes, producing a warm, jargon-free client manual.
   - `--audience developer`: Includes the detected stack matrix, developer notes, source code snippets, and live terminal output cards.
   - `--audience both`: Combines client-friendly walkthrough steps with expandable/structured developer reference panels.
