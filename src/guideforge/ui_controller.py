"""NiceGUI Web Frontend & Multi-Agent REST Controller (`src/guideforge/ui_controller.py`).

Provides:
  1. An interactive NiceGUI web dashboard (when the user wants a visual frontend)
     for editing `guide.yaml`, running polyglot code (Node, Python, Go, Rust),
     triggering `browser-use` discovery, and previewing generated videos/manuals.
  2. A synchronized FastAPI/JSON control plane (`/api/v1/*`) + CLI remote client
     (`guideforge control`) and Universal Agent Tool Schema (`guideforge agent-manifest`)
     so Antigravity CLI and other CLI agents (Claude Code, Codex, OpenClaw, Aider, Cursor)
     can drive the application headlessly or co-pilot the live NiceGUI frontend in real time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.request

from guideforge.browser_agent import BrowserUseRunner
from guideforge.config import (
    AgentLLMConfig,
    CodeSnippet,
    ConfigValidationError,
    OPEN_SOURCE_LICENSE_MANIFEST,
    SAMPLE_GUIDE_YAML,
    load_and_validate_config,
)
from guideforge.exporter import WrittenGuideExporter
from guideforge.polyglot import PolyglotCodeRunner, PolyglotStackDetector
from guideforge.recorder import BrowserRecorder
from guideforge.video import VideoProducer
from guideforge.voice import NarrationEngine

logger = logging.getLogger("guideforge")


# ==============================================================================
# 1. UNIVERSAL CLI AGENT MANIFEST (FOR ANTIGRAVITY CLI & OTHER CLI AGENTS)
# ==============================================================================

UNIVERSAL_AGENT_MANIFEST: Dict[str, Any] = {
    "tool_name": "guideforge",
    "version": "0.4.0",
    "license": "MIT (100% Open Source)",
    "compatible_agents": [
        "Antigravity CLI",
        "Claude Code",
        "OpenAI Codex CLI",
        "Gemini CLI",
        "Aider",
        "Cursor Agent",
        "OpenClaw",
    ],
    "invocation_modes": {
        "direct_cli": "uv run guideforge <subcommand> [args] --json",
        "nicegui_frontend_and_api": "uv run guideforge ui --host 127.0.0.1 --port 8080",
        "remote_cli_to_nicegui": "uv run guideforge control --server http://127.0.0.1:8080 <action> --json",
    },
    "cli_commands": [
        {
            "command": "init",
            "usage": "uv run guideforge init -o guide.yaml --force",
            "description": "Generate starter dual-audience (client + developer) guide.yaml.",
        },
        {
            "command": "validate",
            "usage": "uv run guideforge validate <config.yaml> --json",
            "description": "Validate YAML schema, open-source TTS config, and client jargon rules.",
        },
        {
            "command": "stack",
            "usage": "uv run guideforge stack <project_dir> --json",
            "description": "Detect Node.js, Python, Go, and Rust stacks, frameworks, and runtimes.",
        },
        {
            "command": "exec",
            "usage": "uv run guideforge exec -l <python|node|typescript|go|rust|bash> <code_or_file> --json",
            "description": "Execute polyglot code or scripts and return stdout, stderr, exit_code, and duration_ms.",
        },
        {
            "command": "discover",
            "usage": "uv run guideforge discover --url <url> --goal <goal> -o guide.yaml --json",
            "description": "Use open-source browser-use + local Ollama to explore a web app and generate guide.yaml.",
        },
        {
            "command": "all",
            "usage": "uv run guideforge all <config.yaml> --audience <client|developer|both> --json",
            "description": "Run full pipeline (voice -> record -> render video + HTML/PDF/DOCX/MD manuals).",
        },
        {
            "command": "ui",
            "usage": "uv run guideforge ui --config guide.yaml --port 8080",
            "description": "Launch the NiceGUI visual web dashboard and `/api/v1/*` agent control server.",
        },
        {
            "command": "control",
            "usage": "uv run guideforge control --server http://127.0.0.1:8080 <status|validate|stack|exec|run> --json",
            "description": "Control a running NiceGUI frontend instance from Antigravity CLI or any other CLI agent.",
        },
    ],
    "rest_endpoints": [
        {"method": "GET", "path": "/api/v1/status", "description": "Read live controller state and event log."},
        {"method": "GET", "path": "/api/v1/agent-manifest", "description": "Fetch this universal agent capability schema."},
        {"method": "POST", "path": "/api/v1/config", "description": "Update active guide.yaml content in the NiceGUI editor."},
        {"method": "POST", "path": "/api/v1/validate", "description": "Validate active or posted guide.yaml configuration."},
        {"method": "POST", "path": "/api/v1/stack", "description": "Inspect polyglot project stack (Node, Python, Go, Rust)."},
        {"method": "POST", "path": "/api/v1/exec", "description": "Execute polyglot code snippet and broadcast to NiceGUI UI."},
        {"method": "POST", "path": "/api/v1/discover", "description": "Run browser-use + Ollama autonomous discovery."},
        {"method": "POST", "path": "/api/v1/pipeline/{stage}", "description": "Trigger voice, record, export, render, or all."},
    ],
}


# ==============================================================================
# 2. SHARED CONTROLLER STATE & HEADLESS-SAFE ACTION DISPATCHER
# ==============================================================================

@dataclass
class ControllerState:
  config_path: str = "guide.yaml"
  audience: str = "both"
  browser_engine: str = "hybrid"
  status: str = "idle"
  last_stage: str = "none"
  last_result: Dict[str, Any] = field(default_factory=dict)
  logs: List[str] = field(default_factory=list)

  def log(self, message: str) -> None:
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {message}"
    self.logs.append(entry)
    if len(self.logs) > 200:
      self.logs = self.logs[-200:]
    logger.info(message)


class GuideForgeController:
  """Core controller shared between the NiceGUI frontend, FastAPI endpoints, and CLI agents."""

  def __init__(self, config_path: Path = Path("guide.yaml")):
    if not config_path.exists():
      config_path.write_text(SAMPLE_GUIDE_YAML, encoding="utf-8")
    self.state = ControllerState(config_path=str(config_path))
    self.code_runner = PolyglotCodeRunner()

  def get_config_text(self) -> str:
    p = Path(self.state.config_path)
    if p.exists():
      return p.read_text(encoding="utf-8")
    return SAMPLE_GUIDE_YAML

  def save_config_text(self, yaml_text: str) -> Dict[str, Any]:
    p = Path(self.state.config_path)
    p.write_text(yaml_text, encoding="utf-8")
    self.state.log(f"Updated configuration file: {p}")
    return self.validate_current()

  def validate_current(self) -> Dict[str, Any]:
    p = Path(self.state.config_path)
    try:
      cfg, warnings = load_and_validate_config(p)
      res = {
          "status": "valid",
          "config": str(p),
          "title": cfg.title,
          "audience": cfg.audience,
          "browser_engine": cfg.browser_engine,
          "steps_count": len(cfg.steps),
          "warnings": warnings,
      }
      self.state.last_stage = "validate"
      self.state.last_result = res
      self.state.log(f"Validated {p.name}: {len(cfg.steps)} steps ({cfg.audience} audience)")
      return res
    except ConfigValidationError as exc:
      res = {"status": "invalid", "error": str(exc)}
      self.state.last_stage = "validate"
      self.state.last_result = res
      self.state.log(f"Validation failed: {exc}")
      return res

  def inspect_stack(self, project_dir: str = ".") -> Dict[str, Any]:
    detector = PolyglotStackDetector(Path(project_dir))
    report = detector.inspect()
    res = {"status": "ok", "stage": "stack", "stack_report": report}
    self.state.last_stage = "stack"
    self.state.last_result = res
    langs = [s["language"] for s in report.get("detected_stacks", [])]
    self.state.log(f"Inspected stack in '{project_dir}': detected {langs}")
    return res

  def execute_code(self, language: str, code: str, workdir: str = ".") -> Dict[str, Any]:
    snippet = CodeSnippet(language=language, code=code, execute=True, workdir=workdir)
    exec_res = self.code_runner.run_snippet(snippet, default_workdir=Path(workdir))
    res = {"status": "ok", "stage": "exec", "result": asdict(exec_res)}
    self.state.last_stage = "exec"
    self.state.last_result = res
    self.state.log(
        f"Executed {language.upper()} snippet (exit={exec_res.exit_code}, {exec_res.duration_ms} ms)"
    )
    return res

  async def discover_workflow(
      self, url: str, goal: str, model: str = "llama3.1:8b"
  ) -> Dict[str, Any]:
    self.state.status = "running:discover"
    self.state.log(f"Starting browser-use discovery on {url}: '{goal}'")
    runner = BrowserUseRunner(AgentLLMConfig(model=model))
    info = await runner.discover_guide_from_goal(
        url=url,
        goal=goal,
        output_yaml_path=Path(self.state.config_path),
        audience=self.state.audience,
    )
    self.state.status = "idle"
    res = {"status": "ok", "stage": "discover", "discovery": info}
    self.state.last_stage = "discover"
    self.state.last_result = res
    self.state.log(f"Completed browser-use discovery -> {self.state.config_path}")
    return res

  async def run_pipeline_stage(
      self, stage: str, audience_override: Optional[str] = None
  ) -> Dict[str, Any]:
    self.state.status = f"running:{stage}"
    self.state.log(f"Starting pipeline stage '{stage}'...")
    try:
      cfg, warnings = load_and_validate_config(Path(self.state.config_path))
      if audience_override:
        cfg.audience = audience_override
      elif self.state.audience:
        cfg.audience = self.state.audience

      out_dir = Path(cfg.output_dir)

      if stage == "voice":
        manifest = await NarrationEngine(cfg).generate_all()
        res = {"status": "ok", "stage": "voice", "manifest": manifest}

      elif stage == "record":
        rec_manifest = await BrowserRecorder(cfg).run()
        res = {"status": "ok", "stage": "record", "manifest": rec_manifest}

      elif stage == "export":
        rec_path = out_dir / "recording_manifest.json"
        if rec_path.exists():
          rec_manifest = json.loads(rec_path.read_text(encoding="utf-8"))
        else:
          rec_manifest = await BrowserRecorder(cfg).run()
        docs = WrittenGuideExporter(cfg).export_all(rec_manifest)
        res = {"status": "ok", "stage": "export", "audience": cfg.audience, "written_guides": docs}

      elif stage in ("render", "all", "run"):
        voice_manifest = await NarrationEngine(cfg).generate_all()
        durations = {
            s["id"]: float(s["duration_sec"]) for s in voice_manifest.get("steps", [])
        }
        rec_manifest = await BrowserRecorder(cfg).run(step_durations=durations)
        video_path = VideoProducer(cfg).render_video(rec_manifest, voice_manifest)
        docs = WrittenGuideExporter(cfg).export_all(rec_manifest)
        res = {
            "status": "ok",
            "stage": stage,
            "audience": cfg.audience,
            "video": str(video_path),
            "subtitles_srt": voice_manifest.get("srt_path"),
            "subtitles_vtt": voice_manifest.get("vtt_path"),
            "written_guides": docs,
            "warnings": warnings,
        }
      else:
        res = {"status": "error", "error": f"Unknown pipeline stage: {stage}"}

      self.state.status = "idle"
      self.state.last_stage = stage
      self.state.last_result = res
      self.state.log(f"Finished pipeline stage '{stage}' (status={res.get('status')})")
      return res
    except Exception as exc:
      self.state.status = "idle"
      err_res = {"status": "error", "stage": stage, "error": str(exc)}
      self.state.last_stage = stage
      self.state.last_result = err_res
      self.state.log(f"Error in pipeline stage '{stage}': {exc}")
      return err_res


# ==============================================================================
# 3. NICEGUI WEB FRONTEND + FASTAPI AGENT CONTROL ENDPOINTS
# ==============================================================================

def launch_nicegui_controller(
    config_path: Path = Path("guide.yaml"),
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = False,
) -> int:
  """Starts the NiceGUI frontend alongside the `/api/v1/*` REST control API for CLI agents."""
  controller = GuideForgeController(config_path=config_path)

  try:
    from fastapi import Body
    from nicegui import app, ui
  except ImportError:
    logger.error(
        "NiceGUI is not installed in the current environment. Install it with: uv sync --extra ui (or uv pip install nicegui)"
    )
    return 1

  # ----------------------------------------------------------------------------
  # A. FastAPI Control Endpoints for Antigravity CLI & External CLI Agents
  # ----------------------------------------------------------------------------
  @app.get("/api/v1/status")
  async def api_status() -> Dict[str, Any]:
    return {
        "status": "ok",
        "controller": asdict(controller.state),
        "open_source_licenses": OPEN_SOURCE_LICENSE_MANIFEST,
    }

  @app.get("/api/v1/agent-manifest")
  async def api_agent_manifest() -> Dict[str, Any]:
    return UNIVERSAL_AGENT_MANIFEST

  @app.post("/api/v1/config")
  async def api_update_config(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    yaml_text = str(payload.get("yaml", ""))
    if not yaml_text:
      return {"status": "error", "error": "Missing 'yaml' field in request body."}
    return controller.save_config_text(yaml_text)

  @app.post("/api/v1/validate")
  async def api_validate() -> Dict[str, Any]:
    return controller.validate_current()

  @app.post("/api/v1/stack")
  async def api_stack(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    project_dir = str(payload.get("project_dir", "."))
    return controller.inspect_stack(project_dir)

  @app.post("/api/v1/exec")
  async def api_exec(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    lang = str(payload.get("language", "python"))
    code = str(payload.get("code", ""))
    workdir = str(payload.get("workdir", "."))
    return controller.execute_code(lang, code, workdir)

  @app.post("/api/v1/discover")
  async def api_discover(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    url = str(payload.get("url", "http://localhost:3000"))
    goal = str(payload.get("goal", "Sign in and explore dashboard"))
    model = str(payload.get("model", "llama3.1:8b"))
    return await controller.discover_workflow(url=url, goal=goal, model=model)

  @app.post("/api/v1/pipeline/{stage}")
  async def api_pipeline(stage: str, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    aud = payload.get("audience")
    return await controller.run_pipeline_stage(stage, audience_override=aud)

  # ----------------------------------------------------------------------------
  # B. Interactive NiceGUI Web Dashboard (`/`)
  # ----------------------------------------------------------------------------
  @ui.page("/")
  def index_page() -> None:
    ui.colors(primary="#2563EB", secondary="#1E3A8A", accent="#F59E0B")

    with ui.header().classes("items-center justify-between bg-slate-900 text-white px-6 py-3"):
      with ui.row().classes("items-center gap-3"):
        ui.icon("auto_stories", size="28px").classes("text-blue-400")
        ui.label("GuideForge Studio & Agent Control Plane").classes("text-xl font-bold")
        ui.badge("100% Open Source (MIT)", color="green").classes("ml-2")
      with ui.row().classes("items-center gap-4"):
        status_badge = ui.badge(f"State: {controller.state.status}", color="blue")
        ui.label("Antigravity CLI API: /api/v1/*").classes("text-xs text-slate-300 font-mono")

    with ui.tabs().classes("w-full bg-slate-100") as tabs:
      tab_pipeline = ui.tab("1. Guide Editor & Pipeline")
      tab_polyglot = ui.tab("2. Polyglot Code Runner (Node/Python/Go/Rust)")
      tab_discover = ui.tab("3. AI Browser-Use Discovery (Ollama)")
      tab_agents = ui.tab("4. Antigravity & CLI Agent Bridge")

    with ui.tab_panels(tabs, value=tab_pipeline).classes("w-full p-4"):
      # TAB 1: Guide Editor & Pipeline Controls
      with ui.tab_panel(tab_pipeline):
        with ui.row().classes("w-full gap-4 items-center mb-3"):
          aud_select = ui.select(
              ["both", "client", "developer"],
              value=controller.state.audience,
              label="Target Audience",
              on_change=lambda e: setattr(controller.state, "audience", e.value),
          ).classes("w-48")
          yaml_editor = ui.textarea(
              label=f"Configuration ({controller.state.config_path})",
              value=controller.get_config_text(),
          ).classes("w-full font-mono text-sm").props("rows=16 outlined")

        result_box = ui.code(
            json.dumps(controller.state.last_result or {"ready": True}, indent=2),
            language="json",
        ).classes("w-full")

        async def _save_and_run(stage: str) -> None:
          controller.save_config_text(yaml_editor.value)
          status_badge.set_text(f"State: running {stage}...")
          res = await controller.run_pipeline_stage(stage, audience_override=aud_select.value)
          result_box.set_content(json.dumps(res, indent=2))
          status_badge.set_text(f"State: {controller.state.status}")

        with ui.row().classes("gap-3 mt-2"):
          ui.button(
              "Save & Validate",
              on_click=lambda: result_box.set_content(
                  json.dumps(controller.save_config_text(yaml_editor.value), indent=2)
              ),
              color="primary",
          )
          ui.button("Synthesize Voice (Open-Source TTS)", on_click=lambda: _save_and_run("voice"))
          ui.button("Record Browser & Polyglot Steps", on_click=lambda: _save_and_run("record"))
          ui.button("Export Manuals (HTML/PDF/DOCX/MD)", on_click=lambda: _save_and_run("export"))
          ui.button("Run Full Pipeline (All)", on_click=lambda: _save_and_run("all"), color="green")

      # TAB 2: Polyglot Stack & Live Code Runner
      with ui.tab_panel(tab_polyglot):
        ui.label("Inspect Repository Stack & Run Code in Node.js, Python, Go, Rust, or Bash").classes(
            "text-lg font-semibold mb-2"
        )
        with ui.row().classes("w-full gap-4 items-center"):
          proj_dir_input = ui.input("Project Directory", value=".").classes("w-64")
          lang_select = ui.select(
              ["python", "node", "typescript", "go", "rust", "bash"],
              value="python",
              label="Language Runtime",
          ).classes("w-48")
        code_input = ui.textarea(
            label="Code Snippet",
            value='import platform\nprint(f"Hello from Python {platform.python_version()}!")',
        ).classes("w-full font-mono").props("rows=6 outlined")
        poly_out = ui.code("{}", language="json").classes("w-full")

        with ui.row().classes("gap-3 mt-2"):
          ui.button(
              "Inspect Project Stack",
              on_click=lambda: poly_out.set_content(
                  json.dumps(controller.inspect_stack(proj_dir_input.value), indent=2)
              ),
          )
          ui.button(
              "Execute Code Snippet",
              color="primary",
              on_click=lambda: poly_out.set_content(
                  json.dumps(
                      controller.execute_code(lang_select.value, code_input.value, proj_dir_input.value),
                      indent=2,
                  )
              ),
          )

      # TAB 3: AI Browser-Use Discovery (Local Ollama)
      with ui.tab_panel(tab_discover):
        ui.label("Autonomous Workflow Discovery via browser-use (MIT) + Local Ollama").classes(
            "text-lg font-semibold mb-2"
        )
        disc_url = ui.input("Application URL", value="http://localhost:3000").classes("w-full")
        disc_goal = ui.input(
            "Plain-Language Goal",
            value="Sign in, open the Billing tab, and download the latest monthly invoice",
        ).classes("w-full")
        disc_model = ui.input("Local Ollama Model", value="llama3.1:8b").classes("w-64")
        disc_out = ui.code("{}", language="json").classes("w-full")

        async def _run_discovery() -> None:
          res = await controller.discover_workflow(disc_url.value, disc_goal.value, disc_model.value)
          disc_out.set_content(json.dumps(res, indent=2))
          yaml_editor.set_value(controller.get_config_text())

        ui.button("Discover & Populate guide.yaml", on_click=_run_discovery, color="primary")

      # TAB 4: Antigravity CLI & External Agent Bridge
      with ui.tab_panel(tab_agents):
        ui.label("Universal Control Schema for Antigravity CLI, Claude Code, Codex & Shell Agents").classes(
            "text-lg font-semibold mb-2"
        )
        ui.code(json.dumps(UNIVERSAL_AGENT_MANIFEST, indent=2), language="json").classes("w-full")

    # Live Activity Log Footer
    with ui.card().classes("w-full mt-4 bg-slate-950 text-green-400 font-mono text-xs p-3"):
      ui.label("Live Controller & CLI Agent Event Stream").classes("text-slate-400 font-bold mb-1")
      log_label = ui.label("\n".join(controller.state.logs[-10:]) or "Ready.").classes("whitespace-pre-wrap")
      ui.timer(1.0, lambda: log_label.set_text("\n".join(controller.state.logs[-10:]) or "Ready."))

  logger.info("Launching GuideForge NiceGUI Frontend & Agent API at http://%s:%d", host, port)
  ui.run(host=host, port=port, title="GuideForge Studio", show=open_browser, reload=False)
  return 0


# ==============================================================================
# 4. REMOTE CLI CLIENT (`guideforge control`) FOR CLI AGENTS
# ==============================================================================

def send_remote_agent_command(
    server_url: str,
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
  """Sends a command from Antigravity CLI (or any shell agent) to a running NiceGUI server."""
  base = server_url.rstrip("/")
  route_map = {
      "status": ("GET", f"{base}/api/v1/status"),
      "manifest": ("GET", f"{base}/api/v1/agent-manifest"),
      "validate": ("POST", f"{base}/api/v1/validate"),
      "stack": ("POST", f"{base}/api/v1/stack"),
      "exec": ("POST", f"{base}/api/v1/exec"),
      "discover": ("POST", f"{base}/api/v1/discover"),
      "voice": ("POST", f"{base}/api/v1/pipeline/voice"),
      "record": ("POST", f"{base}/api/v1/pipeline/record"),
      "export": ("POST", f"{base}/api/v1/pipeline/export"),
      "render": ("POST", f"{base}/api/v1/pipeline/render"),
      "all": ("POST", f"{base}/api/v1/pipeline/all"),
      "run": ("POST", f"{base}/api/v1/pipeline/all"),
  }
  if action not in route_map:
    return {"status": "error", "error": f"Unsupported remote action '{action}'."}

  method, url = route_map[action]
  data = json.dumps(payload or {}).encode("utf-8") if method == "POST" else None
  req = urllib.request.Request(
      url,
      data=data,
      headers={"Content-Type": "application/json"},
      method=method,
  )
  try:
    with urllib.request.urlopen(req, timeout=60) as resp:
      return json.loads(resp.read().decode("utf-8"))
  except Exception as exc:
    return {
        "status": "error",
        "server": base,
        "action": action,
        "error": f"Could not reach NiceGUI controller at {base} ({exc}). You can also run the action directly via headless CLI: `uv run guideforge {action} ... --json`.",
    }
