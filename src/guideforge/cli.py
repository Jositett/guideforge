"""Command-line interface entry point (`guideforge`) for Client, Developer, and Antigravity CLI use."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from guideforge.browser_agent import BrowserUseRunner
from guideforge.config import (
  OPEN_SOURCE_LICENSE_MANIFEST,
  SAMPLE_GUIDE_YAML,
  AgentLLMConfig,
  CodeSnippet,
  ConfigValidationError,
  GuideConfig,
  load_and_validate_config,
)
from guideforge.exporter import WrittenGuideExporter
from guideforge.polyglot import PolyglotCodeRunner, PolyglotStackDetector
from guideforge.recorder import BrowserRecorder
from guideforge.ui_controller import (
  UNIVERSAL_AGENT_MANIFEST,
  GuideForgeController,
  launch_nicegui_controller,
  send_remote_agent_command,
)
from guideforge.video import VideoProducer
from guideforge.voice import NarrationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("guideforge")


def _load_or_exit(
    config_arg: str,
    audience_override: str | None = None,
    json_output: bool = False,
) -> GuideConfig:
  try:
    cfg, warnings = load_and_validate_config(Path(config_arg))
    if audience_override:
      cfg.audience = audience_override
    for w in warnings:
      logger.warning(w)
    return cfg
  except ConfigValidationError as exc:
    if json_output:
      print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
    else:
      logger.error(str(exc))
    sys.exit(1)


def cmd_init(output_path: Path, force: bool = False) -> int:
  if output_path.exists() and not force:
    logger.error("File '%s' already exists. Pass --force to overwrite.", output_path)
    return 1
  output_path.write_text(SAMPLE_GUIDE_YAML, encoding="utf-8")
  logger.info("Created sample open-source client & developer configuration at %s", output_path)
  return 0


def cmd_validate(config_path: Path, json_output: bool = False) -> int:
  try:
    cfg, warnings = load_and_validate_config(config_path)
    polyglot_langs = sorted({s.code_block.language for s in cfg.steps if s.code_block})
    summary = {
        "status": "valid",
        "config": str(config_path),
        "title": cfg.title,
        "audience": cfg.audience,
        "base_url": cfg.base_url,
        "resolution": cfg.video.resolution,
        "tts_provider": cfg.tts.provider,
        "open_source_compliant": True,
        "polyglot_languages_in_steps": polyglot_langs,
        "steps_count": len(cfg.steps),
        "export_formats": cfg.export_formats,
        "warnings": warnings,
    }
    if json_output:
      print(json.dumps(summary, indent=2))
    else:
      logger.info(
          "Configuration '%s' is valid (audience=%s, %d steps, polyglot=%s, tts=%s).",
          config_path,
          cfg.audience,
          len(cfg.steps),
          polyglot_langs,
          cfg.tts.provider,
      )
      for w in warnings:
        logger.warning("Hint: %s", w)
    return 0
  except ConfigValidationError as exc:
    if json_output:
      print(json.dumps({"status": "invalid", "error": str(exc)}, indent=2))
    else:
      logger.error("%s", exc)
    return 1


def cmd_stack(project_dir: Path, json_output: bool = False) -> dict[str, Any]:
  detector = PolyglotStackDetector(project_dir)
  report = detector.inspect()
  if json_output:
    print(json.dumps({"status": "ok", "stage": "stack", "stack_report": report}, indent=2))
  else:
    logger.info("Inspected project directory: %s", report["project_dir"])
    for s in report["detected_stacks"]:
      logger.info(
          "  • %s (%s) — manifests=%s | run: %s",
          s["language"],
          s["runtime_version"],
          s["manifest_files"],
          s["run_command_hint"],
      )
  return report


def cmd_exec(
    language: str,
    code_or_file: str,
    workdir: str = ".",
    json_output: bool = False,
) -> dict[str, Any]:
  p = Path(code_or_file)
  if p.exists() and p.is_file():
    code_text = p.read_text(encoding="utf-8")
    fname = p.name
  else:
    code_text = code_or_file
    fname = None

  runner = PolyglotCodeRunner()
  snippet = CodeSnippet(
      language=language,
      code=code_text,
      filename=fname,
      execute=True,
      workdir=workdir,
  )
  result = runner.run_snippet(snippet, default_workdir=Path(workdir))
  res_dict = asdict(result)
  if json_output:
    print(json.dumps({"status": "ok", "stage": "exec", "result": res_dict}, indent=2))
  else:
    logger.info(
        "[%s] Exit=%d (%.1f ms) | Output: %s",
        result.language.upper(),
        result.exit_code,
        result.duration_ms,
        result.stdout or result.stderr,
    )
  return res_dict


def cmd_licenses(json_output: bool = False) -> list[dict[str, str]]:
  if json_output:
    print(
        json.dumps(
            {
                "status": "ok",
                "open_source_only": True,
                "licenses": OPEN_SOURCE_LICENSE_MANIFEST,
            },
            indent=2,
        )
    )
  else:
    logger.info("GuideForge Open-Source License Compliance Manifest:")
    for item in OPEN_SOURCE_LICENSE_MANIFEST:
      logger.info(
          "  • %-40s | %-28s | %s",
          item["component"],
          item["license"],
          item["commercial_restrictions"],
      )
  return OPEN_SOURCE_LICENSE_MANIFEST


def cmd_voice(cfg: GuideConfig, json_output: bool = False) -> dict[str, Any]:
  engine = NarrationEngine(cfg)
  manifest = asyncio.run(engine.generate_all())
  if json_output:
    print(json.dumps({"status": "ok", "stage": "voice", "manifest": manifest}, indent=2))
  return manifest


def cmd_record(
    cfg: GuideConfig,
    step_durations: dict[str, float] | None = None,
    json_output: bool = False,
) -> dict[str, Any]:
  if step_durations is None:
    v_path = Path(cfg.output_dir) / "voice_manifest.json"
    if v_path.exists():
      try:
        v_data = json.loads(v_path.read_text(encoding="utf-8"))
        step_durations = {
            s["id"]: float(s["duration_sec"]) for s in v_data.get("steps", [])
        }
      except Exception:
        pass

  recorder = BrowserRecorder(cfg)
  manifest = asyncio.run(recorder.run(step_durations=step_durations))
  if json_output:
    print(json.dumps({"status": "ok", "stage": "record", "manifest": manifest}, indent=2))
  return manifest


def cmd_render(
    cfg: GuideConfig,
    formats: list[str] | None = None,
    json_output: bool = False,
) -> dict[str, Any]:
  out_dir = Path(cfg.output_dir)
  rec_manifest_path = out_dir / "recording_manifest.json"
  voice_manifest_path = out_dir / "voice_manifest.json"

  if not voice_manifest_path.exists():
    voice_manifest = cmd_voice(cfg, json_output=False)
  else:
    voice_manifest = json.loads(voice_manifest_path.read_text(encoding="utf-8"))

  if not rec_manifest_path.exists():
    durations = {
        s["id"]: float(s["duration_sec"]) for s in voice_manifest.get("steps", [])
    }
    rec_manifest = cmd_record(cfg, step_durations=durations, json_output=False)
  else:
    rec_manifest = json.loads(rec_manifest_path.read_text(encoding="utf-8"))

  producer = VideoProducer(cfg)
  video_path = producer.render_video(rec_manifest, voice_manifest)

  exporter = WrittenGuideExporter(cfg)
  docs = exporter.export_all(rec_manifest, formats=formats)

  result = {
      "status": "ok",
      "stage": "render",
      "audience": cfg.audience,
      "video": str(video_path),
      "subtitles_srt": voice_manifest.get("srt_path"),
      "subtitles_vtt": voice_manifest.get("vtt_path"),
      "written_guides": docs,
  }
  if json_output:
    print(json.dumps(result, indent=2))
  return result


def build_arg_parser() -> argparse.ArgumentParser:
  common = argparse.ArgumentParser(add_help=False)
  common.add_argument(
      "--json",
      action="store_true",
      help="Emit machine-readable JSON output for Antigravity CLI / CI pipelines.",
  )
  common.add_argument(
      "--audience",
      choices=["client", "developer", "both"],
      default=None,
      help="Override target audience ('client', 'developer', or 'both').",
  )

  parser = argparse.ArgumentParser(
      prog="guideforge",
      parents=[common],
      description="GuideForge — 100% Open-Source Client & Developer Manual Generator with Polyglot Code Runner",
  )
  sub = parser.add_subparsers(dest="command", required=True)

  # init
  p_init = sub.add_parser("init", parents=[common], help="Create a sample client + developer guide.yaml.")
  p_init.add_argument("-o", "--output", default="guide.yaml", help="Output path (default: guide.yaml).")
  p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing file.")

  # validate
  p_val = sub.add_parser("validate", parents=[common], help="Validate guide.yaml, open-source TTS, and jargon rules.")
  p_val.add_argument("config", help="Path to guide.yaml.")

  # ui / serve (New: launch NiceGUI web frontend + FastAPI agent control server)
  for ui_alias in ("ui", "serve"):
    p_ui = sub.add_parser(
        ui_alias,
        parents=[common],
        help="Launch the NiceGUI web frontend and `/api/v1/*` REST controller for CLI agents.",
    )
    p_ui.add_argument("-c", "--config", default="guide.yaml", help="Path to guide.yaml (default: guide.yaml).")
    p_ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    p_ui.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080).")
    p_ui.add_argument("--open", action="store_true", help="Open browser tab automatically.")

  # control (New: let Antigravity CLI or any other CLI agent control the NiceGUI controller)
  p_ctrl = sub.add_parser(
      "control",
      parents=[common],
      help="Control a running NiceGUI instance (or local controller via --local) from Antigravity CLI or other CLI agents.",
  )
  p_ctrl.add_argument(
      "action",
      choices=["status", "manifest", "validate", "stack", "exec", "discover", "voice", "record", "export", "render", "all", "run"],
      help="Controller action to trigger.",
  )
  p_ctrl.add_argument("--server", default="http://127.0.0.1:8080", help="NiceGUI controller URL (default: http://127.0.0.1:8080).")
  p_ctrl.add_argument("-c", "--config", default="guide.yaml", help="Config path when using --local.")
  p_ctrl.add_argument("--local", action="store_true", help="Execute directly on local GuideForgeController state without requiring a running HTTP server.")
  p_ctrl.add_argument("-l", "--language", default="python", help="Language for exec action.")
  p_ctrl.add_argument("--code", default="print('OK')", help="Code snippet for exec action.")
  p_ctrl.add_argument("--project-dir", default=".", help="Project dir for stack action.")
  p_ctrl.add_argument("--url", default="http://localhost:3000", help="Target URL for discover action.")
  p_ctrl.add_argument("--goal", default="Sign in and explore dashboard", help="Goal for discover action.")

  # agent-manifest (New: machine-readable capability schema for Antigravity CLI & other CLI agents)
  sub.add_parser(
      "agent-manifest",
      parents=[common],
      help="Emit the universal JSON capability & endpoint schema for Antigravity CLI and other CLI agents.",
  )

  # discover (New: auto-discover workflow using open-source browser-use + Ollama)
  p_disc = sub.add_parser(
      "discover",
      parents=[common],
      help="Autonomously explore a URL using open-source browser-use + local Ollama and generate guide.yaml.",
  )
  p_disc.add_argument("--url", required=True, help="Target application URL (e.g. http://localhost:3000).")
  p_disc.add_argument("--goal", required=True, help="Plain-language goal for the browser-use agent.")
  p_disc.add_argument("--model", default="llama3.1:8b", help="Local Ollama model (default: llama3.1:8b).")
  p_disc.add_argument("-o", "--output", default="guide.yaml", help="Output YAML path (default: guide.yaml).")

  # stack (New: polyglot stack detector for developers & clients)
  p_stack = sub.add_parser(
      "stack",
      parents=[common],
      help="Detect project code stack (Node.js, Python, Go, Rust) and available host runtimes.",
  )
  p_stack.add_argument("project_dir", nargs="?", default=".", help="Project directory to inspect (default: .)")

  # exec (New: run any code from Node, Python, Go, Rust, or Bash)
  p_exec = sub.add_parser(
      "exec",
      parents=[common],
      help="Execute a code snippet or source file in Node.js, Python, Go, Rust, or Bash.",
  )
  p_exec.add_argument(
      "-l",
      "--language",
      required=True,
      choices=["python", "node", "javascript", "typescript", "go", "golang", "rust", "bash", "sh"],
      help="Target language runtime.",
  )
  p_exec.add_argument("code_or_file", help="Inline code string or path to source file.")
  p_exec.add_argument("-w", "--workdir", default=".", help="Working directory.")

  # licenses (New: audit open-source compliance)
  sub.add_parser(
      "licenses",
      parents=[common],
      help="Display the 100% open-source, zero-commercial-restriction license manifest.",
  )

  # record
  p_rec = sub.add_parser("record", parents=[common], help="Record browser session, run polyglot snippets, and annotate screenshots.")
  p_rec.add_argument("config", help="Path to guide.yaml.")

  # voice
  p_voice = sub.add_parser("voice", parents=[common], help="Synthesize open-source local TTS audio and SRT/VTT subtitles.")
  p_voice.add_argument("config", help="Path to guide.yaml.")

  # render
  p_ren = sub.add_parser("render", parents=[common], help="Render final MP4 video and written manuals.")
  p_ren.add_argument("config", help="Path to guide.yaml.")

  # export
  p_exp = sub.add_parser("export", parents=[common], help="Export written manuals (HTML, Markdown, PDF, DOCX).")
  p_exp.add_argument("config", help="Path to guide.yaml.")
  p_exp.add_argument("--formats", nargs="+", default=None, help="Override formats (html pdf docx md).")

  # all / run
  for alias in ("all", "run"):
    p_all = sub.add_parser(alias, parents=[common], help="Run full pipeline (validate -> voice -> record -> render).")
    p_all.add_argument("config", help="Path to guide.yaml.")

  return parser


def main(argv: list[str] | None = None) -> int:
  parser = build_arg_parser()
  args = parser.parse_args(argv)

  if args.command == "init":
    return cmd_init(Path(args.output), force=args.force)

  if args.command == "validate":
    return cmd_validate(Path(args.config), json_output=args.json)

  if args.command in ("ui", "serve"):
    return launch_nicegui_controller(
        config_path=Path(args.config),
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )

  if args.command == "agent-manifest":
    print(json.dumps(UNIVERSAL_AGENT_MANIFEST, indent=2))
    return 0

  if args.command == "control":
    if args.local:
      ctrl = GuideForgeController(config_path=Path(args.config))
      if args.audience:
        ctrl.state.audience = args.audience
      if args.action == "status":
        res = {"status": "ok", "controller": asdict(ctrl.state)}
      elif args.action == "manifest":
        res = UNIVERSAL_AGENT_MANIFEST
      elif args.action == "validate":
        res = ctrl.validate_current()
      elif args.action == "stack":
        res = ctrl.inspect_stack(args.project_dir)
      elif args.action == "exec":
        res = ctrl.execute_code(args.language, args.code, args.project_dir)
      elif args.action == "discover":
        res = asyncio.run(ctrl.discover_workflow(args.url, args.goal))
      else:
        res = asyncio.run(ctrl.run_pipeline_stage(args.action, audience_override=args.audience))
    else:
      payload = {
          "language": args.language,
          "code": args.code,
          "project_dir": args.project_dir,
          "url": args.url,
          "goal": args.goal,
          "audience": args.audience,
      }
      res = send_remote_agent_command(args.server, args.action, payload)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") in ("ok", "valid") or "tool_name" in res else 1

  if args.command == "discover":
    runner = BrowserUseRunner(AgentLLMConfig(model=args.model))
    info = asyncio.run(
        runner.discover_guide_from_goal(
            url=args.url,
            goal=args.goal,
            output_yaml_path=Path(args.output),
            audience=args.audience or "both",
        )
    )
    if args.json:
      print(json.dumps({"status": "ok", "stage": "discover", "discovery": info}, indent=2))
    else:
      logger.info("Discovered workflow via browser-use and wrote config to %s", info["output_yaml"])
    return 0

  if args.command == "stack":
    cmd_stack(Path(args.project_dir), json_output=args.json)
    return 0

  if args.command == "exec":
    res = cmd_exec(args.language, args.code_or_file, workdir=args.workdir, json_output=args.json)
    return 0 if res["exit_code"] == 0 else 1

  if args.command == "licenses":
    cmd_licenses(json_output=args.json)
    return 0

  cfg = _load_or_exit(args.config, audience_override=args.audience, json_output=args.json)

  if args.command == "voice":
    cmd_voice(cfg, json_output=args.json)
    return 0

  if args.command == "record":
    cmd_record(cfg, json_output=args.json)
    return 0

  if args.command == "export":
    out_dir = Path(cfg.output_dir)
    rec_manifest_path = out_dir / "recording_manifest.json"
    if rec_manifest_path.exists():
      rec_manifest = json.loads(rec_manifest_path.read_text(encoding="utf-8"))
    else:
      rec_manifest = cmd_record(cfg, json_output=False)
    exporter = WrittenGuideExporter(cfg)
    docs = exporter.export_all(rec_manifest, formats=args.formats)
    if args.json:
      print(json.dumps({"status": "ok", "stage": "export", "audience": cfg.audience, "written_guides": docs}, indent=2))
    return 0

  if args.command == "render":
    cmd_render(cfg, json_output=args.json)
    return 0

  if args.command in ("all", "run"):
    voice_manifest = cmd_voice(cfg, json_output=False)
    durations = {
        s["id"]: float(s["duration_sec"]) for s in voice_manifest.get("steps", [])
    }
    cmd_record(cfg, step_durations=durations, json_output=False)
    cmd_render(cfg, json_output=args.json)
    return 0

  return 0


if __name__ == "__main__":
  sys.exit(main())
