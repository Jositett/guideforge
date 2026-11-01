"""Playwright browser automation, polyglot code execution capture, and screenshot annotation."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from guideforge.browser_agent import BrowserUseRunner
from guideforge.config import GuideConfig, GuideStep
from guideforge.polyglot import (
  AppServerLifecycle,
  PolyglotCodeRunner,
  PolyglotStackDetector,
)
from guideforge.utils import PIL_AVAILABLE, _hex_to_rgb, _load_font

if PIL_AVAILABLE:
  from PIL import Image, ImageDraw

logger = logging.getLogger("guideforge")

CURSOR_AND_EFFECTS_JS = """
(() => {
  if (window.__guideforgeInitialized) return;
  window.__guideforgeInitialized = true;

  const style = document.createElement('style');
  style.textContent = `
    #gf-cursor {
      position: fixed;
      top: 0;
      left: 0;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: __CURSOR_COLOR__;
      border: 3px solid #FFFFFF;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
      pointer-events: none;
      z-index: 2147483647;
      transform: translate(-50%, -50%);
      transition: top 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                  left 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                  transform 0.15s ease;
    }
    .gf-ripple {
      position: fixed;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: __RIPPLE_COLOR__;
      border: 2px solid __PRIMARY_COLOR__;
      pointer-events: none;
      z-index: 2147483646;
      transform: translate(-50%, -50%) scale(1);
      animation: gf-ripple-anim 0.65s ease-out forwards;
    }
    @keyframes gf-ripple-anim {
      0% { transform: translate(-50%, -50%) scale(0.8); opacity: 1; }
      100% { transform: translate(-50%, -50%) scale(3.6); opacity: 0; }
    }
    .gf-highlight-box {
      outline: 4px solid __PRIMARY_COLOR__ !important;
      outline-offset: 4px !important;
      box-shadow: 0 0 0 8px rgba(37, 99, 235, 0.22), 0 10px 25px rgba(0,0,0,0.18) !important;
      transition: outline 0.25s ease, box-shadow 0.25s ease !important;
      border-radius: 6px;
    }
    body {
      transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1), transform-origin 0.55s ease;
    }
  `;
  document.head.appendChild(style);

  const cursor = document.createElement('div');
  cursor.id = 'gf-cursor';
  cursor.style.left = '50%';
  cursor.style.top = '50%';
  document.body.appendChild(cursor);

  window.__gfMoveCursor = (x, y) => {
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  };

  window.__gfClickRipple = (x, y) => {
    cursor.style.transform = 'translate(-50%, -50%) scale(0.78)';
    setTimeout(() => {
      cursor.style.transform = 'translate(-50%, -50%) scale(1)';
    }, 150);
    const ripple = document.createElement('div');
    ripple.className = 'gf-ripple';
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    document.body.appendChild(ripple);
    setTimeout(() => ripple.remove(), 700);
  };

  window.__gfZoomTo = (x, y, scale) => {
    if (!scale || scale <= 1.0) {
      document.body.style.transform = 'scale(1)';
      return;
    }
    const originX = (x / window.innerWidth) * 100;
    const originY = (y / window.innerHeight) * 100;
    document.body.style.transformOrigin = `${originX}% ${originY}%`;
    document.body.style.transform = `scale(${scale})`;
  };
})();
"""


class BrowserRecorder:
  """Drives Playwright, executes polyglot code snippets (Node, Python, Go, Rust), and captures screenshots."""

  def __init__(self, config: GuideConfig):
    self.config = config
    self.out_dir = Path(config.output_dir)
    self.screenshots_dir = self.out_dir / "screenshots"
    self.raw_video_dir = self.out_dir / "raw_video"
    self.manifest_path = self.out_dir / "recording_manifest.json"
    self.code_runner = PolyglotCodeRunner()
    self.stack_detector = PolyglotStackDetector(Path(config.project_dir))
    self.browser_agent = BrowserUseRunner(config.agent_llm)

  async def run(self, step_durations: dict[str, float] | None = None) -> dict[str, Any]:
    """Executes stack inspection, optional app server boot, browser automation, and polyglot code blocks."""
    self.screenshots_dir.mkdir(parents=True, exist_ok=True)
    self.raw_video_dir.mkdir(parents=True, exist_ok=True)

    stack_report = self.stack_detector.inspect()
    code_results: dict[str, dict[str, Any]] = {}
    agent_traces: dict[str, dict[str, Any]] = {}
    for step in self.config.steps:
      if step.action == "agent_task" or (self.config.browser_engine == "browser-use" and not step.selector):
        trace = await self.browser_agent.execute_step_goal(step, base_url=self.config.base_url)
        agent_traces[step.id] = asdict(trace)
      if step.code_block:
        logger.info(
            "Executing %s code snippet for step '%s' (%s)...",
            step.code_block.language,
            step.id,
            step.code_block.filename or "inline",
        )
        res = self.code_runner.run_snippet(
            step.code_block, default_workdir=Path(self.config.project_dir)
        )
        code_results[step.id] = asdict(res)

    with AppServerLifecycle(self.config.app_server):
      return await self._record_browser_or_fallback(
          step_durations=step_durations,
          stack_report=stack_report,
          code_results=code_results,
      )

  async def _record_browser_or_fallback(
      self,
      step_durations: dict[str, float] | None,
      stack_report: dict[str, Any],
      code_results: dict[str, dict[str, Any]],
  ) -> dict[str, Any]:
    width, height = self.config.viewport_size
    manifest: dict[str, Any] = {
        "title": self.config.title,
        "audience": self.config.audience,
        "resolution": f"{width}x{height}",
        "raw_video_path": None,
        "stack_report": stack_report,
        "steps": [],
    }

    import os
    if os.environ.get("GUIDEFORGE_OFFLINE"):
      return self._run_synthetic_fallback(step_durations, stack_report, code_results)
    try:
      from playwright.async_api import async_playwright
    except ImportError:
      return self._run_synthetic_fallback(step_durations, stack_report, code_results)

    try:
      async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(self.raw_video_dir),
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        logger.info("Opening base URL: %s (%dx%d)", self.config.base_url, width, height)
        await page.goto(self.config.base_url, wait_until="networkidle", timeout=15000)
        await self._inject_visual_helpers(page)

        elapsed = 0.0
        for idx, step in enumerate(self.config.steps, start=1):
          logger.info("Executing Step %d/%d: %s (%s)", idx, len(self.config.steps), step.title, step.action)
          step_start = elapsed
          bbox = await self._execute_step(page, step)

          target_hold = (
              (step_durations or {}).get(step.id, step.wait_ms / 1000.0)
              + self.config.video.step_padding_seconds
          )
          await page.wait_for_timeout(int(target_hold * 1000))
          elapsed += target_hold

          raw_shot = self.screenshots_dir / f"{idx:02d}_{step.id}_raw.png"
          annotated_shot = self.screenshots_dir / f"{idx:02d}_{step.id}.png"
          await page.screenshot(path=str(raw_shot), full_page=False)

          if step.zoom > 1.0:
            await page.evaluate("window.__gfZoomTo(0, 0, 1.0)")

          self._annotate_screenshot(
              raw_path=raw_shot,
              output_path=annotated_shot,
              step_index=idx,
              step=step,
              bbox=bbox,
              code_result=code_results.get(step.id),
          )

          manifest["steps"].append({
              "index": idx,
              "id": step.id,
              "title": step.title,
              "start_sec": round(step_start, 2),
              "end_sec": round(elapsed, 2),
              "screenshot": str(annotated_shot),
              "bbox": bbox,
              "code_execution": code_results.get(step.id),
          })

        video_obj = page.video
        await context.close()
        await browser.close()

        if video_obj:
          recorded_path = await video_obj.path()
          final_raw_video = self.raw_video_dir / "session_recording.webm"
          shutil.copyfile(recorded_path, final_raw_video)
          manifest["raw_video_path"] = str(final_raw_video)

    except Exception as exc:
      logger.info(
          "Using offline UI & polyglot terminal compositor (%s).",
          exc,
      )
      return self._run_synthetic_fallback(step_durations, stack_report, code_results)

    self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

  async def _inject_visual_helpers(self, page: Any) -> None:
    js = (
        CURSOR_AND_EFFECTS_JS.replace("__CURSOR_COLOR__", self.config.video.cursor_color)
        .replace("__RIPPLE_COLOR__", self.config.video.ripple_color)
        .replace("__PRIMARY_COLOR__", self.config.branding.primary_color)
    )
    await page.evaluate(js)

  async def _execute_step(
      self, page: Any, step: GuideStep
  ) -> dict[str, float] | None:
    await self._inject_visual_helpers(page)
    bbox: dict[str, float] | None = None

    if step.action in ("navigate", "run_code"):
      if step.action == "navigate":
        target_url = step.url or self.config.base_url
        if not target_url.startswith("http"):
          target_url = self.config.base_url.rstrip("/") + "/" + target_url.lstrip("/")
        await page.goto(target_url, wait_until="networkidle")
        await self._inject_visual_helpers(page)
      return None

    if step.selector:
      locator = page.locator(step.selector).first
      await locator.wait_for(state="visible", timeout=12000)
      await locator.scroll_into_view_if_needed()
      bbox = await locator.bounding_box()

      if bbox:
        cx = bbox["x"] + bbox["width"] / 2.0
        cy = bbox["y"] + bbox["height"] / 2.0
        await page.evaluate(f"window.__gfMoveCursor({cx}, {cy})")
        await page.wait_for_timeout(450)

        if step.highlight:
          await locator.evaluate("el => el.classList.add('gf-highlight-box')")

        if step.zoom and step.zoom > 1.0:
          await page.evaluate(f"window.__gfZoomTo({cx}, {cy}, {step.zoom})")
          await page.wait_for_timeout(400)

        if step.action == "click":
          await page.evaluate(f"window.__gfClickRipple({cx}, {cy})")
          await locator.click()
        elif step.action == "type":
          await page.evaluate(f"window.__gfClickRipple({cx}, {cy})")
          await locator.click()
          await locator.fill("")
          await locator.type(step.value or "", delay=55)
        elif step.action == "hover":
          await locator.hover()
        elif step.action == "select":
          await locator.select_option(step.value or "")

    elif step.action == "scroll":
      amount = int(step.value or 450)
      await page.evaluate(f"window.scrollBy({{ top: {amount}, behavior: 'smooth' }})")
    elif step.action == "wait":
      await page.wait_for_timeout(step.wait_ms)

    return bbox

  def _annotate_screenshot(
      self,
      raw_path: Path,
      output_path: Path,
      step_index: int,
      step: GuideStep,
      bbox: dict[str, float] | None,
      code_result: dict[str, Any] | None = None,
  ) -> None:
    """Draws numbered callout badges, highlight frames, and optional developer terminal overlay."""
    if not PIL_AVAILABLE or not raw_path.exists():
      if raw_path.exists():
        shutil.copyfile(raw_path, output_path)
      return

    img = Image.open(raw_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    primary_rgb = _hex_to_rgb(self.config.branding.primary_color)
    accent_rgb = _hex_to_rgb(self.config.branding.accent_color)

    if bbox:
      x1 = max(0, int(bbox["x"]) - 6)
      y1 = max(0, int(bbox["y"]) - 6)
      x2 = min(img.width, int(bbox["x"] + bbox["width"]) + 6)
      y2 = min(img.height, int(bbox["y"] + bbox["height"]) + 6)

      draw.rounded_rectangle(
          [x1 - 4, y1 - 4, x2 + 4, y2 + 4],
          radius=12,
          outline=(*primary_rgb, 110),
          width=8,
      )
      draw.rounded_rectangle(
          [x1, y1, x2, y2],
          radius=8,
          outline=(*primary_rgb, 255),
          width=4,
      )

      badge_r = 22
      bx = max(badge_r + 8, x1 - 12)
      by = max(badge_r + 8, y1 - 12)
      draw.ellipse(
          [bx - badge_r, by - badge_r, bx + badge_r, by + badge_r],
          fill=(*accent_rgb, 255),
          outline=(255, 255, 255, 255),
          width=3,
      )
      font = _load_font(22, bold=True)
      draw.text(
          (bx, by),
          str(step_index),
          fill=(255, 255, 255, 255),
          font=font,
          anchor="mm",
      )

      label_text = step.annotation_label or step.title
      if label_text:
        label_font = _load_font(18, bold=True)
        lx = min(img.width - 340, x2 + 18)
        ly = max(24, y1)
        text_bbox = draw.textbbox((0, 0), label_text, font=label_font)
        tw = text_bbox[2] - text_bbox[0]
        th = text_bbox[3] - text_bbox[1]
        pill_rect = [lx, ly, lx + tw + 28, ly + th + 18]
        draw.rounded_rectangle(
            pill_rect,
            radius=10,
            fill=(*primary_rgb, 240),
            outline=(255, 255, 255, 230),
            width=2,
        )
        draw.text(
            (lx + 14, ly + 8),
            label_text,
            fill=(255, 255, 255, 255),
            font=label_font,
        )

    # If audience is developer or both and a polyglot code snippet ran, draw a sleek bottom-right terminal card
    if code_result and self.config.audience in ("developer", "both"):
      term_w, term_h = 680, 170
      tx1 = img.width - term_w - 36
      ty1 = img.height - term_h - 36
      draw.rounded_rectangle(
          [tx1, ty1, tx1 + term_w, ty1 + term_h],
          radius=12,
          fill=(15, 23, 42, 242),
          outline=(*primary_rgb, 230),
          width=2,
      )
      lang_badge = f"{code_result['language'].upper()} • {code_result['filename']} ({code_result['duration_ms']} ms)"
      draw.text(
          (tx1 + 18, ty1 + 14),
          lang_badge,
          fill=(56, 189, 248, 255),
          font=_load_font(15, bold=True),
      )
      out_line = (code_result.get("stdout") or code_result.get("stderr") or "OK (exit 0)").splitlines()[0][:72]
      draw.text(
          (tx1 + 18, ty1 + 48),
          f"$ {' '.join(str(x) for x in code_result.get('command', [])[:3])}",
          fill=(148, 163, 184, 255),
          font=_load_font(14),
      )
      draw.text(
          (tx1 + 18, ty1 + 82),
          f"→ {out_line}",
          fill=(74, 222, 128, 255),
          font=_load_font(16, bold=True),
      )

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    composed.save(output_path, quality=95)

  def _run_synthetic_fallback(
      self,
      step_durations: dict[str, float] | None,
      stack_report: dict[str, Any],
      code_results: dict[str, dict[str, Any]],
  ) -> dict[str, Any]:
    width, height = self.config.viewport_size
    manifest: dict[str, Any] = {
        "title": self.config.title,
        "audience": self.config.audience,
        "resolution": f"{width}x{height}",
        "raw_video_path": None,
        "stack_report": stack_report,
        "steps": [],
    }
    elapsed = 0.0
    for idx, step in enumerate(self.config.steps, start=1):
      step_start = elapsed
      dur = (
          (step_durations or {}).get(step.id, step.wait_ms / 1000.0)
          + self.config.video.step_padding_seconds
      )
      elapsed += dur

      raw_shot = self.screenshots_dir / f"{idx:02d}_{step.id}_raw.png"
      annotated_shot = self.screenshots_dir / f"{idx:02d}_{step.id}.png"
      bbox = self._draw_synthetic_portal_frame(raw_shot, idx, step, width, height)
      self._annotate_screenshot(
          raw_shot,
          annotated_shot,
          idx,
          step,
          bbox,
          code_result=code_results.get(step.id),
      )

      manifest["steps"].append({
          "index": idx,
          "id": step.id,
          "title": step.title,
          "start_sec": round(step_start, 2),
          "end_sec": round(elapsed, 2),
          "screenshot": str(annotated_shot),
          "bbox": bbox,
          "code_execution": code_results.get(step.id),
      })

    self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

  def _draw_synthetic_portal_frame(
      self,
      out_path: Path,
      step_index: int,
      step: GuideStep,
      width: int,
      height: int,
  ) -> dict[str, float]:
    img = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    primary_rgb = _hex_to_rgb(self.config.branding.primary_color)

    draw.rectangle([0, 0, width, 56], fill=(30, 41, 59))
    for i, col in enumerate([(239, 68, 68), (245, 158, 11), (16, 185, 129)]):
      draw.ellipse([24 + i * 24, 20, 38 + i * 24, 34], fill=col)
    draw.rounded_rectangle([120, 12, width - 220, 44], radius=8, fill=(51, 65, 85))
    draw.text(
        (140, 18),
        f"{self.config.base_url}",
        fill=(226, 232, 240),
        font=_load_font(16),
    )

    draw.rectangle([0, 56, width, 128], fill=(255, 255, 255))
    draw.line([0, 128, width, 128], fill=(226, 232, 240), width=2)
    draw.text(
        (48, 80),
        self.config.branding.company_name,
        fill=primary_rgb,
        font=_load_font(26, bold=True),
    )

    card_rect = [280, 180, width - 120, height - 110]
    draw.rounded_rectangle(
        card_rect, radius=16, fill=(255, 255, 255), outline=(226, 232, 240), width=2
    )
    draw.text(
        (320, 220),
        step.title,
        fill=(15, 23, 42),
        font=_load_font(32, bold=True),
    )
    draw.text(
        (320, 275),
        step.instruction,
        fill=(71, 85, 105),
        font=_load_font(20),
    )

    bx, by, bw, bh = 320, 360 + (step_index % 3) * 70, 460, 64
    draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=10,
        fill=(239, 246, 255) if step.action != "click" else primary_rgb,
        outline=primary_rgb,
        width=2,
    )
    label_val = step.value or step.annotation_label or step.title
    draw.text(
        (bx + 24, by + 18),
        str(label_val),
        fill=(255, 255, 255) if step.action == "click" else (30, 58, 138),
        font=_load_font(20, bold=True),
    )

    img.save(out_path, quality=95)
    return {"x": float(bx), "y": float(by), "width": float(bw), "height": float(bh)}
