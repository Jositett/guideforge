from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from guideforge.cli import main
from guideforge.config import (
    CodeSnippet,
    ConfigValidationError,
    OPEN_SOURCE_LICENSE_MANIFEST,
    load_and_validate_config,
)
from guideforge.polyglot import PolyglotCodeRunner, PolyglotStackDetector


class GuideForgeOpenSourcePolyglotTestSuite(unittest.TestCase):
  def test_open_source_license_manifest(self) -> None:
    self.assertGreaterEqual(len(OPEN_SOURCE_LICENSE_MANIFEST), 5)
    for item in OPEN_SOURCE_LICENSE_MANIFEST:
      self.assertIn("None", item["commercial_restrictions"])

  def test_init_and_validate_dual_audience(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      cfg_file = Path(tmp) / "guide.yaml"
      rc = main(["init", "-o", str(cfg_file)])
      self.assertEqual(rc, 0)
      cfg, warnings = load_and_validate_config(cfg_file)
      self.assertEqual(cfg.audience, "both")
      self.assertEqual(cfg.tts.provider, "piper")
      langs = {s.code_block.language for s in cfg.steps if s.code_block}
      self.assertEqual(langs, {"python", "node", "go", "rust"})
      self.assertEqual(warnings, [])

  def test_rejects_proprietary_tts_providers(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      cfg_file = Path(tmp) / "proprietary.yaml"
      cfg_file.write_text(
          'title: "Guide"\n'
          'base_url: "http://localhost:3000"\n'
          'tts:\n'
          '  provider: "elevenlabs"\n'
          'steps:\n'
          '  - id: "s1"\n'
          '    title: "Open"\n'
          '    action: "navigate"\n'
          '    narration: "Hello client."\n'
          '    instruction: "Open page."\n',
          encoding="utf-8",
      )
      with self.assertRaises(ConfigValidationError):
        load_and_validate_config(cfg_file)

  def test_polyglot_stack_detector_all_languages(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / "pyproject.toml").write_text(
          "[project]\nname='demo'\ndependencies=['fastapi']\n", encoding="utf-8"
      )
      (root / "package.json").write_text(
          '{"dependencies": {"next": "14.0.0", "react": "18.0.0"}}',
          encoding="utf-8",
      )
      (root / "go.mod").write_text(
          "module example.com/demo\nrequire github.com/gin-gonic/gin v1.9.0\n",
          encoding="utf-8",
      )
      (root / "Cargo.toml").write_text(
          "[package]\nname='demo'\n[dependencies]\naxum='0.7'\n",
          encoding="utf-8",
      )

      detector = PolyglotStackDetector(root)
      report = detector.inspect()
      detected_names = [s["language"] for s in report["detected_stacks"]]
      self.assertIn("Python", detected_names)
      self.assertIn("Node.js / TypeScript", detected_names)
      self.assertIn("Go (Golang)", detected_names)
      self.assertIn("Rust", detected_names)

  def test_polyglot_code_runner_execution(self) -> None:
    runner = PolyglotCodeRunner()
    for lang, code in [
        ("python", 'print("PY_OK")'),
        ("node", 'console.log("NODE_OK")'),
        ("go", 'package main\nimport "fmt"\nfunc main() { fmt.Println("GO_OK") }'),
        ("rust", 'fn main() { println!("RUST_OK"); }'),
        ("bash", 'echo "BASH_OK"'),
    ]:
      res = runner.run_snippet(CodeSnippet(language=lang, code=code, execute=True))
      self.assertEqual(res.exit_code, 0)
      self.assertTrue(res.stdout)

  def test_nicegui_controller_and_cli_agent_bridge(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      cfg_file = Path(tmp) / "guide.yaml"
      main(["init", "-o", str(cfg_file)])

      # 1. Test universal agent-manifest CLI output for Antigravity CLI & other agents
      buf = io.StringIO()
      with patch("sys.stdout", buf):
        rc = main(["agent-manifest", "--json"])
      self.assertEqual(rc, 0)
      manifest = json.loads(buf.getvalue())
      self.assertEqual(manifest["tool_name"], "guideforge")
      self.assertIn("Antigravity CLI", manifest["compatible_agents"])
      self.assertGreaterEqual(len(manifest["rest_endpoints"]), 6)

      # 2. Test `guideforge control --local` for validate, stack, and exec
      for action_args, expected_stage in [
          (["control", "validate", "--local", "-c", str(cfg_file), "--json"], "valid"),
          (["control", "stack", "--local", "-c", str(cfg_file), "--project-dir", str(tmp), "--json"], "ok"),
          (["control", "exec", "--local", "-c", str(cfg_file), "-l", "python", "--code", "print(42)", "--json"], "ok"),
      ]:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
          rc = main(action_args)
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["status"], expected_stage)

  def test_browser_use_discover_and_agent_task(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
      out_yaml = Path(tmp) / "discovered_guide.yaml"
      buf = io.StringIO()
      with patch("sys.stdout", buf):
        rc = main([
            "discover",
            "--url",
            "http://localhost:3000",
            "--goal",
            "Sign in and download the latest invoice",
            "-o",
            str(out_yaml),
            "--json",
        ])
      self.assertEqual(rc, 0)
      payload = json.loads(buf.getvalue())
      self.assertEqual(payload["status"], "ok")
      self.assertTrue(out_yaml.exists())
      cfg, _ = load_and_validate_config(out_yaml)
      self.assertEqual(cfg.browser_engine, "hybrid")
      self.assertTrue(any(s.action == "agent_task" for s in cfg.steps))

  def test_export_client_and_developer_manuals(self) -> None:
    import os
    os.environ["GUIDEFORGE_OFFLINE"] = "1"
    with tempfile.TemporaryDirectory() as tmp:
      cfg_file = Path(tmp) / "guide.yaml"
      out_dir = Path(tmp) / "dist"
      main(["init", "-o", str(cfg_file)])
      text = cfg_file.read_text(encoding="utf-8").replace(
          'output_dir: "./dist"', f'output_dir: "{out_dir}"'
      )
      cfg_file.write_text(text, encoding="utf-8")

      buf = io.StringIO()
      with patch("sys.stdout", buf):
        rc = main(["export", str(cfg_file), "--audience", "both", "--json"])
      self.assertEqual(rc, 0)
      payload = json.loads(buf.getvalue())
      self.assertEqual(payload["status"], "ok")
      self.assertTrue((out_dir / "user_manual.html").exists())
      self.assertTrue((out_dir / "user_manual.md").exists())
      self.assertTrue((out_dir / "user_manual.pdf").exists())
      self.assertTrue((out_dir / "user_manual.docx").exists())
      md_text = (out_dir / "user_manual.md").read_text(encoding="utf-8")
      self.assertIn("Open-Source License Compliance", md_text)
      self.assertIn("Polyglot Stack & Host Runtimes", md_text)


if __name__ == "__main__":
  unittest.main()
