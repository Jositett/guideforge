"""Configuration dataclasses, YAML parser, open-source license registry, and dual-audience validator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_ACTIONS = {
    "navigate",
    "click",
    "type",
    "scroll",
    "wait",
    "hover",
    "select",
    "screenshot",
    "run_code",
    "agent_task",
}
VALID_AUDIENCES = {"client", "developer", "both"}
VALID_BROWSER_ENGINES = {"playwright", "browser-use", "hybrid"}
VALID_CALLOUT_TYPES = {"tip", "warning", "note", "important"}
# 100% Open-Source Local / Self-Hosted TTS Engines (Zero proprietary cloud lock-in)
VALID_TTS_PROVIDERS = {"piper", "kokoro", "espeak-ng", "coqui", "pyttsx3"}
VALID_LANGUAGES = {
    "python",
    "node",
    "javascript",
    "typescript",
    "go",
    "golang",
    "rust",
    "bash",
    "sh",
}
VALID_RESOLUTIONS = {
    "1080p": (1920, 1080),
    "4k": (3840, 2160),
    "720p": (1280, 720),
}
VALID_EXPORT_FORMATS = {"html", "md", "markdown", "pdf", "docx"}

OPEN_SOURCE_LICENSE_MANIFEST: list[dict[str, str]] = [
    {
        "component": "NiceGUI + FastAPI (Web Frontend & Agent Control Plane)",
        "license": "MIT License",
        "commercial_restrictions": "None (100% Free & Open Source, by Zauberzeug / FastAPI)",
    },
    {
        "component": "Python Runtime & Standard Library",
        "license": "PSF-2.0 (OSI Approved)",
        "commercial_restrictions": "None (100% Free & Open Source)",
    },
    {
        "component": "browser-use + Ollama (Local LLM Browser Agent)",
        "license": "MIT License",
        "commercial_restrictions": "None (100% Free & Open Source, runs locally with Ollama)",
    },
    {
        "component": "Playwright + Chromium",
        "license": "Apache-2.0 / BSD-3-Clause",
        "commercial_restrictions": "None (100% Free & Open Source)",
    },
    {
        "component": "FFmpeg Media Compositor",
        "license": "LGPL-2.1+ / GPL-2.0+",
        "commercial_restrictions": "None (100% Free & Open Source)",
    },
    {
        "component": "Piper Neural TTS / Kokoro ONNX / eSpeak-NG",
        "license": "MIT / Apache-2.0 / GPL-3.0+",
        "commercial_restrictions": "None (Local offline neural voice synthesis, zero cloud fees)",
    },
    {
        "component": "Pillow (PIL Fork)",
        "license": "HPND (MIT-compatible)",
        "commercial_restrictions": "None (100% Free & Open Source)",
    },
    {
        "component": "PyYAML & python-docx",
        "license": "MIT License",
        "commercial_restrictions": "None (100% Free & Open Source)",
    },
    {
        "component": "DejaVu / Liberation Typography",
        "license": "Bitstream Vera / SIL Open Font License (OFL)",
        "commercial_restrictions": "None (Safe for commercial & client distribution)",
    },
]


@dataclass
class BrandingConfig:
  company_name: str = "OpenStack Portal"
  logo_path: str | None = None
  primary_color: str = "#2563EB"
  secondary_color: str = "#1E40AF"
  accent_color: str = "#F59E0B"
  text_color: str = "#1F2937"
  background_color: str = "#F8FAFC"
  font_family: str = "Liberation Sans, DejaVu Sans, system-ui, sans-serif"
  mono_font_family: str = "DejaVu Sans Mono, Liberation Mono, monospace"
  intro_title: str = "Welcome to Your Guide"
  intro_subtitle: str = "Client Walkthrough & Developer Reference"
  outro_title: str = "Questions or Contributions?"
  outro_contact: str = "Reach our team at support@example.org"
  background_music: str | None = None
  music_volume: float = 0.16
  ducked_volume: float = 0.04


@dataclass
class TTSConfig:
  provider: str = "piper"           # "piper" (MIT), "kokoro" (Apache-2.0), "espeak-ng" (GPL), "coqui" (MPL-2.0), "pyttsx3"
  voice: str = "en_US-lessac-medium"
  speed: float = 1.0
  burn_subtitles: bool = True
  subtitle_font_size: int = 24


@dataclass
class VideoConfig:
  resolution: str = "1080p"
  fps: int = 30
  intro_duration: float = 3.5
  outro_duration: float = 4.0
  step_padding_seconds: float = 0.8
  cursor_color: str = "#EF4444"
  ripple_color: str = "rgba(37, 99, 235, 0.45)"


@dataclass
class AgentLLMConfig:
  """Configuration for 100% open-source local LLM driving `browser-use` (via Ollama / vLLM)."""
  provider: str = "ollama"          # "ollama" (MIT) or "vllm" (Apache-2.0)
  model: str = "llama3.1:8b"        # e.g., "llama3.1:8b", "qwen2.5:7b"
  base_url: str = "http://127.0.0.1:11434"
  context_window: int = 64000
  max_steps: int = 15


@dataclass
class AppServerConfig:
  """Optional configuration to auto-start a local Node, Python, Go, or Rust server during recording."""
  enabled: bool = False
  language: str = "python"          # "node", "python", "go", "rust", "bash"
  command: str = ""                 # e.g., "npm run dev", "uv run app.py", "go run .", "cargo run"
  workdir: str = "."
  ready_url: str | None = None
  startup_timeout_sec: int = 30
  env: dict[str, str] = field(default_factory=dict)


@dataclass
class CodeSnippet:
  """Polyglot code block attached to a step for developer documentation and optional live execution."""
  language: str                     # "node", "javascript", "typescript", "python", "go", "rust", "bash"
  code: str
  filename: str | None = None
  execute: bool = True              # If true, GuideForge runs the code and captures real stdout/stderr
  workdir: str | None = None
  expected_exit_code: int = 0


@dataclass
class CalloutBox:
  kind: str                         # "tip", "warning", "note", "important"
  title: str
  text: str


@dataclass
class GuideStep:
  id: str
  title: str
  action: str
  narration: str
  instruction: str
  developer_note: str | None = None
  selector: str | None = None
  goal: str | None = None
  value: str | None = None
  url: str | None = None
  wait_ms: int = 1200
  highlight: bool = True
  zoom: float = 1.0
  annotation_label: str | None = None
  callout: CalloutBox | None = None
  code_block: CodeSnippet | None = None


@dataclass
class GuideConfig:
  title: str
  description: str
  version: str
  audience: str                     # "client", "developer", or "both"
  project_dir: str                  # Path inspected for stack metadata (Node, Python, Go, Rust)
  base_url: str
  browser_engine: str
  output_dir: str
  export_formats: list[str]
  branding: BrandingConfig
  tts: TTSConfig
  video: VideoConfig
  app_server: AppServerConfig
  agent_llm: AgentLLMConfig
  steps: list[GuideStep]

  @property
  def viewport_size(self) -> tuple[int, int]:
    return VALID_RESOLUTIONS.get(self.video.resolution.lower(), (1920, 1080))


class ConfigValidationError(Exception):
  """Raised when `guide.yaml` fails structural or semantic validation."""


def load_and_validate_config(config_path: Path) -> tuple[GuideConfig, list[str]]:
  """Loads a YAML config file, validates all fields, and returns warnings."""
  if not config_path.exists():
    raise ConfigValidationError(f"Configuration file not found: {config_path}")

  try:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
  except yaml.YAMLError as exc:
    raise ConfigValidationError(f"Invalid YAML syntax: {exc}") from exc

  if not isinstance(raw, dict):
    raise ConfigValidationError("Top-level configuration must be a YAML mapping.")

  errors: list[str] = []
  warnings: list[str] = []

  title = str(raw.get("title", "")).strip()
  if not title:
    errors.append("Missing required top-level field: 'title'.")

  audience = str(raw.get("audience", "both")).lower().strip()
  if audience not in VALID_AUDIENCES:
    errors.append(
        f"Invalid 'audience' ({audience}). Allowed: {sorted(VALID_AUDIENCES)}"
    )

  project_dir = str(raw.get("project_dir", ".")).strip()

  browser_engine = str(raw.get("browser_engine", "hybrid")).lower().strip()
  if browser_engine not in VALID_BROWSER_ENGINES:
    errors.append(
        f"Invalid 'browser_engine' ({browser_engine}). Allowed: {sorted(VALID_BROWSER_ENGINES)}"
    )

  llm_raw = raw.get("agent_llm", {}) or {}
  agent_llm = AgentLLMConfig(
      provider=str(llm_raw.get("provider", "ollama")).lower().strip(),
      model=str(llm_raw.get("model", "llama3.1:8b")).strip(),
      base_url=str(llm_raw.get("base_url", "http://127.0.0.1:11434")).strip(),
      context_window=int(llm_raw.get("context_window", 64000)),
      max_steps=int(llm_raw.get("max_steps", 15)),
  )

  base_url = str(raw.get("base_url", "http://localhost:3000")).strip()
  if not (base_url.startswith("http://") or base_url.startswith("https://")):
    errors.append(
        f"Invalid 'base_url' ({base_url}): must start with http:// or https://."
    )

  output_dir = str(raw.get("output_dir", "./dist")).strip()
  export_formats = [
      str(fmt).lower().strip()
      for fmt in raw.get("export_formats", ["html", "md", "pdf", "docx"])
  ]
  for fmt in export_formats:
    if fmt not in VALID_EXPORT_FORMATS:
      errors.append(
          f"Unsupported export format '{fmt}'. Allowed: {sorted(VALID_EXPORT_FORMATS)}"
      )

  # Branding validation
  b_raw = raw.get("branding", {}) or {}
  hex_re = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
  primary_color = str(b_raw.get("primary_color", "#2563EB"))
  if not hex_re.match(primary_color):
    errors.append(
        f"Invalid branding.primary_color '{primary_color}': must be a hex color (e.g. #2563EB)."
    )

  logo_path = b_raw.get("logo_path")
  if logo_path and not Path(logo_path).exists():
    warnings.append(
        f"branding.logo_path '{logo_path}' was not found on disk; a clean typographic badge will be used instead."
    )

  bg_music = b_raw.get("background_music")
  if bg_music and not Path(bg_music).exists():
    warnings.append(
        f"branding.background_music '{bg_music}' was not found on disk; video will render without background music."
    )

  branding = BrandingConfig(
      company_name=str(b_raw.get("company_name", "OpenStack Portal")),
      logo_path=logo_path,
      primary_color=primary_color,
      secondary_color=str(b_raw.get("secondary_color", "#1E40AF")),
      accent_color=str(b_raw.get("accent_color", "#F59E0B")),
      text_color=str(b_raw.get("text_color", "#1F2937")),
      background_color=str(b_raw.get("background_color", "#F8FAFC")),
      font_family=str(
          b_raw.get(
              "font_family",
              "Liberation Sans, DejaVu Sans, system-ui, sans-serif",
          )
      ),
      mono_font_family=str(
          b_raw.get(
              "mono_font_family",
              "DejaVu Sans Mono, Liberation Mono, monospace",
          )
      ),
      intro_title=str(b_raw.get("intro_title", title or "User & Developer Guide")),
      intro_subtitle=str(
          b_raw.get(
              "intro_subtitle",
              raw.get("description", "Step-by-step client & developer walkthrough"),
          )
      ),
      outro_title=str(b_raw.get("outro_title", "We're Here to Help!")),
      outro_contact=str(
          b_raw.get(
              "outro_contact",
              "Questions? Contact Support at support@example.org",
          )
      ),
      background_music=bg_music,
      music_volume=float(b_raw.get("music_volume", 0.16)),
      ducked_volume=float(b_raw.get("ducked_volume", 0.04)),
  )

  # Open-Source TTS validation
  t_raw = raw.get("tts", {}) or {}
  provider = str(t_raw.get("provider", "piper")).lower().strip()
  if provider not in VALID_TTS_PROVIDERS:
    errors.append(
        f"Unsupported tts.provider '{provider}'. Only 100% open-source providers are allowed: {sorted(VALID_TTS_PROVIDERS)}"
    )

  tts = TTSConfig(
      provider=provider,
      voice=str(t_raw.get("voice", "en_US-lessac-medium")),
      speed=float(t_raw.get("speed", 1.0)),
      burn_subtitles=bool(t_raw.get("burn_subtitles", True)),
      subtitle_font_size=int(t_raw.get("subtitle_font_size", 24)),
  )

  # Video validation
  v_raw = raw.get("video", {}) or {}
  res = str(v_raw.get("resolution", "1080p")).lower()
  if res not in VALID_RESOLUTIONS:
    errors.append(
        f"Unsupported video.resolution '{res}'. Allowed: {sorted(VALID_RESOLUTIONS.keys())}"
    )
  video = VideoConfig(
      resolution=res,
      fps=int(v_raw.get("fps", 30)),
      intro_duration=float(v_raw.get("intro_duration", 3.5)),
      outro_duration=float(v_raw.get("outro_duration", 4.0)),
      step_padding_seconds=float(v_raw.get("step_padding_seconds", 0.8)),
      cursor_color=str(v_raw.get("cursor_color", "#EF4444")),
      ripple_color=str(v_raw.get("ripple_color", "rgba(37, 99, 235, 0.45)")),
  )

  # App server validation
  srv_raw = raw.get("app_server", {}) or {}
  app_server = AppServerConfig(
      enabled=bool(srv_raw.get("enabled", False)),
      language=str(srv_raw.get("language", "python")).lower().strip(),
      command=str(srv_raw.get("command", "")).strip(),
      workdir=str(srv_raw.get("workdir", project_dir)).strip(),
      ready_url=srv_raw.get("ready_url") or base_url,
      startup_timeout_sec=int(srv_raw.get("startup_timeout_sec", 30)),
      env=dict(srv_raw.get("env", {}) or {}),
  )

  # Steps validation
  steps_raw = raw.get("steps", [])
  if not isinstance(steps_raw, list) or not steps_raw:
    errors.append("Configuration must include a non-empty 'steps' list.")

  steps: list[GuideStep] = []
  jargon_terms = {"dom", "selector", "xpath", "div", "span", "payload", "webhook", "crud", "regex"}

  for idx, s_raw in enumerate(steps_raw, start=1):
    if not isinstance(s_raw, dict):
      errors.append(f"Step #{idx} must be a mapping.")
      continue

    step_id = str(s_raw.get("id", f"step_{idx:02d}")).strip()
    step_title = str(s_raw.get("title", f"Step {idx}")).strip()
    action = str(s_raw.get("action", "")).lower().strip()
    narration = str(s_raw.get("narration", "")).strip()
    instruction = str(s_raw.get("instruction", narration)).strip()
    dev_note = s_raw.get("developer_note")
    selector = s_raw.get("selector")
    goal = s_raw.get("goal")
    value = s_raw.get("value")
    url = s_raw.get("url")

    if action not in VALID_ACTIONS:
      errors.append(
          f"Step #{idx} ('{step_title}'): invalid action '{action}'. Allowed: {sorted(VALID_ACTIONS)}"
      )

    if action in {"click", "type", "hover", "select"} and not selector:
      errors.append(
          f"Step #{idx} ('{step_title}'): action '{action}' requires a 'selector'."
      )

    if action == "type" and value is None:
      errors.append(
          f"Step #{idx} ('{step_title}'): action 'type' requires a 'value' to enter."
      )

    if not narration:
      errors.append(
          f"Step #{idx} ('{step_title}'): 'narration' text is required for voiceover and subtitles."
      )

    # Check client-facing narration/instruction for developer jargon (developer_note and code_block are allowed to use technical terms!)
    if audience in {"client", "both"}:
      combined_words = set(re.findall(r"[a-zA-Z]+", f"{narration} {instruction}".lower()))
      found_jargon = combined_words.intersection(jargon_terms)
      if found_jargon:
        warnings.append(
            f"Step #{idx} ('{step_title}'): detected technical jargon {sorted(found_jargon)} in client-facing text. Move technical details into 'developer_note' or 'code_block' and keep 'narration'/'instruction' plain and friendly."
        )

    callout_obj: CalloutBox | None = None
    c_raw = s_raw.get("callout")
    if isinstance(c_raw, dict):
      c_kind = str(c_raw.get("type", "tip")).lower().strip()
      if c_kind not in VALID_CALLOUT_TYPES:
        errors.append(
            f"Step #{idx} ('{step_title}'): invalid callout.type '{c_kind}'. Allowed: {sorted(VALID_CALLOUT_TYPES)}"
        )
      callout_obj = CalloutBox(
          kind=c_kind,
          title=str(c_raw.get("title", c_kind.capitalize())).strip(),
          text=str(c_raw.get("text", "")).strip(),
      )

    code_obj: CodeSnippet | None = None
    cb_raw = s_raw.get("code_block")
    if isinstance(cb_raw, dict):
      lang = str(cb_raw.get("language", "python")).lower().strip()
      if lang not in VALID_LANGUAGES:
        errors.append(
            f"Step #{idx} ('{step_title}'): unsupported code_block.language '{lang}'. Allowed: {sorted(VALID_LANGUAGES)}"
        )
      code_str = str(cb_raw.get("code", "")).strip()
      if not code_str:
        errors.append(
            f"Step #{idx} ('{step_title}'): code_block requires non-empty 'code'."
        )
      code_obj = CodeSnippet(
          language=lang,
          code=code_str,
          filename=cb_raw.get("filename"),
          execute=bool(cb_raw.get("execute", True)),
          workdir=cb_raw.get("workdir"),
          expected_exit_code=int(cb_raw.get("expected_exit_code", 0)),
      )
    elif action == "run_code":
      errors.append(
          f"Step #{idx} ('{step_title}'): action 'run_code' requires a 'code_block' mapping."
      )

    steps.append(
        GuideStep(
            id=step_id,
            title=step_title,
            action=action,
            narration=narration,
            instruction=instruction,
            developer_note=str(dev_note).strip() if dev_note else None,
            selector=str(selector) if selector else None,
            goal=str(goal) if goal else None,
            value=str(value) if value is not None else None,
            url=str(url) if url else None,
            wait_ms=int(s_raw.get("wait_ms", 1200)),
            highlight=bool(s_raw.get("highlight", True)),
            zoom=float(s_raw.get("zoom", 1.0)),
            annotation_label=s_raw.get("annotation_label"),
            callout=callout_obj,
            code_block=code_obj,
        )
    )

  if errors:
    bullet_errors = "\n  - ".join(errors)
    raise ConfigValidationError(f"Configuration validation failed:\n  - {bullet_errors}")

  config = GuideConfig(
      title=title,
      description=str(raw.get("description", "")).strip(),
      version=str(raw.get("version", "1.0")),
      audience=audience,
      project_dir=project_dir,
      base_url=base_url,
      browser_engine=browser_engine,
      output_dir=output_dir,
      export_formats=export_formats,
      branding=branding,
      tts=tts,
      video=video,
      app_server=app_server,
      agent_llm=agent_llm,
      steps=steps,
  )
  return config, warnings


SAMPLE_GUIDE_YAML = """# ==============================================================================
# GuideForge — Open-Source Client & Developer Guide Configuration (guide.yaml)
# Supports Both Non-Technical Clients AND Technical Developers + Polyglot Code
# ==============================================================================
title: "Getting Started with Your OpenStack Portal & Polyglot SDK"
description: "A friendly walkthrough for clients managing their account and a complete polyglot reference (Node.js, Python, Go, Rust) for developers."
version: "2.0"
audience: "both"                # "client" (non-technical only), "developer" (technical + code), or "both"
project_dir: "."                # Auto-inspected to detect Node, Python, Go, and Rust stacks
base_url: "http://localhost:3000"
browser_engine: "hybrid"        # "playwright" (deterministic), "browser-use" (AI agent via CDP), or "hybrid"
output_dir: "./dist"

# 100% Open-Source Local LLM for `browser-use` autonomous steps (via Ollama)
agent_llm:
  provider: "ollama"
  model: "llama3.1:8b"
  base_url: "http://127.0.0.1:11434"
  context_window: 64000
  max_steps: 15
export_formats:
  - html
  - md
  - pdf
  - docx

branding:
  company_name: "Northwind Open Platform"
  logo_path: null
  primary_color: "#2563EB"
  secondary_color: "#1E3A8A"
  accent_color: "#F59E0B"
  text_color: "#1F2937"
  background_color: "#F8FAFC"
  font_family: "Liberation Sans, DejaVu Sans, system-ui, sans-serif"
  mono_font_family: "DejaVu Sans Mono, Liberation Mono, monospace"
  intro_title: "Welcome to Northwind Open Platform"
  intro_subtitle: "Client Portal Walkthrough & Polyglot Developer Reference"
  outro_title: "Need a Hand or Building an Integration?"
  outro_contact: "Client Support: care@northwind.example.org | Dev Docs: git.northwind.example.org"
  background_music: null
  music_volume: 0.16
  ducked_volume: 0.04

# 100% Open-Source Local TTS (No commercial cloud copyright or API keys required)
tts:
  provider: "piper"             # Options: "piper" (MIT), "kokoro" (Apache-2.0), "espeak-ng" (GPL), "coqui" (MPL-2.0), "pyttsx3"
  voice: "en_US-lessac-medium"
  speed: 1.0
  burn_subtitles: true
  subtitle_font_size: 24

video:
  resolution: "1080p"           # Options: "720p", "1080p", "4k"
  fps: 30
  intro_duration: 3.5
  outro_duration: 4.0
  step_padding_seconds: 0.8
  cursor_color: "#EF4444"
  ripple_color: "rgba(37, 99, 235, 0.45)"

# Optional: Auto-start any Node, Python, Go, or Rust server before recording
app_server:
  enabled: false
  language: "python"
  command: "python3 -m http.server 3000"
  workdir: "."
  ready_url: "http://localhost:3000"
  startup_timeout_sec: 15

steps:
  - id: "open_sign_in"
    title: "Open Your Welcome Page"
    action: "navigate"
    url: "http://localhost:3000/login"
    narration: "Welcome to the Northwind Portal. Open the sign-in link from your welcome email to access your account."
    instruction: "Open the Northwind Portal link provided in your welcome email."
    developer_note: "The portal frontend serves a session-initialized login view over HTTP/2 and exposes `/api/v1/health` for uptime checks."
    wait_ms: 1400
    highlight: false
    zoom: 1.0
    callout:
      type: "tip"
      title: "Bookmark for One-Click Access"
      text: "Save this page to your browser bookmarks so you can return to your account anytime."
    code_block:
      language: "python"
      filename: "verify_portal_env.py"
      execute: true
      code: |
        import platform
        import sys
        print(f"[Python {platform.python_version()}] Northwind SDK environment ready on {sys.platform}")

  - id: "enter_email"
    title: "Enter Your Email Address"
    action: "type"
    selector: "input[type='email'], #email"
    value: "alex.rivera@clientcompany.org"
    annotation_label: "Type your work email here"
    narration: "Click the email box and enter the email address connected to your account."
    instruction: "Click the Email Address field and enter the email address registered with your account."
    developer_note: "For automated service-to-service workflows, authenticate via Node.js or TypeScript using a signed client token."
    wait_ms: 1200
    highlight: true
    zoom: 1.2
    code_block:
      language: "node"
      filename: "auth_check.mjs"
      execute: true
      code: |
        const payload = { user: "alex.rivera@clientcompany.org", scope: "portal:read" };
        console.log("[Node.js]", JSON.stringify(payload));

  - id: "click_continue"
    title: "Sign In to Your Dashboard"
    action: "click"
    selector: "button[type='submit'], #login-button"
    annotation_label: "Click Sign In"
    narration: "Next, click the blue Sign In button to open your personal dashboard."
    instruction: "Click the blue Sign In button to access your account overview."
    developer_note: "High-throughput backend microservices can query account summaries directly using the Go SDK."
    wait_ms: 1500
    highlight: true
    zoom: 1.15
    callout:
      type: "note"
      title: "Forgot Your Password?"
      text: "If you ever need to reset your password, click the 'Reset Password' link right below the Sign In button."
    code_block:
      language: "go"
      filename: "check_account.go"
      execute: true
      code: |
        package main
        import "fmt"
        func main() {
            fmt.Println("[Go] Account summary verified: status=ACTIVE")
        }

  - id: "download_invoice"
    title: "Download Your Latest Monthly Invoice"
    action: "click"
    selector: "#download-latest-invoice, .btn-download-invoice"
    annotation_label: "Download PDF Receipt"
    narration: "From your Billing Summary card, click Download Latest Invoice to save a PDF copy for your records."
    instruction: "Locate the Billing Summary card and click Download Latest Invoice to save a clean PDF receipt to your computer."
    developer_note: "For cryptographic invoice checksum verification, compile and run the Rust verification snippet below."
    wait_ms: 1800
    highlight: true
    zoom: 1.25
    callout:
      type: "warning"
      title: "Allow Browser Downloads"
      text: "If your receipt does not download right away, check that your browser allows file downloads from the portal."
    code_block:
      language: "rust"
      filename: "verify_invoice.rs"
      execute: true
      code: |
        fn main() {
            let invoice_id = "INV-2026-1101";
            println!("[Rust] Verified checksum for invoice {}", invoice_id);
        }
"""
