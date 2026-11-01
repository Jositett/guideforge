"""Dual-audience (Client + Developer) written guide exporter for HTML, Markdown, PDF, and DOCX."""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from guideforge.config import GuideConfig, OPEN_SOURCE_LICENSE_MANIFEST
from guideforge.utils import PIL_AVAILABLE, _hex_to_rgb

if PIL_AVAILABLE:
  from PIL import Image

logger = logging.getLogger("guideforge")


class WrittenGuideExporter:
  """Generates branded Client, Developer, or Dual-Audience manuals in HTML, Markdown, PDF, and DOCX."""

  def __init__(self, config: GuideConfig):
    self.config = config
    self.out_dir = Path(config.output_dir)

  def export_all(
      self,
      recording_manifest: Dict[str, Any],
      formats: Optional[List[str]] = None,
  ) -> Dict[str, str]:
    target_formats = [
        f.lower() for f in (formats or self.config.export_formats)
    ]
    exported: Dict[str, str] = {}

    html_path = self.out_dir / "user_manual.html"
    html_content = self._build_html(recording_manifest)
    html_path.write_text(html_content, encoding="utf-8")
    if "html" in target_formats:
      exported["html"] = str(html_path)
      logger.info("Exported standalone HTML manual (%s audience): %s", self.config.audience, html_path)

    if "md" in target_formats or "markdown" in target_formats:
      md_path = self.out_dir / "user_manual.md"
      md_path.write_text(
          self._build_markdown(recording_manifest), encoding="utf-8"
      )
      exported["markdown"] = str(md_path)
      logger.info("Exported Markdown manual: %s", md_path)

    if "pdf" in target_formats:
      pdf_path = self.out_dir / "user_manual.pdf"
      self._export_pdf(html_path, pdf_path)
      exported["pdf"] = str(pdf_path)
      logger.info("Exported PDF manual: %s", pdf_path)

    if "docx" in target_formats:
      docx_path = self.out_dir / "user_manual.docx"
      self._export_docx(recording_manifest, docx_path)
      exported["docx"] = str(docx_path)
      logger.info("Exported DOCX manual: %s", docx_path)

    return exported

  def _build_html(self, recording_manifest: Dict[str, Any]) -> str:
    b = self.config.branding
    audience = self.config.audience
    rec_steps = {s["id"]: s for s in recording_manifest.get("steps", [])}
    stack_report = recording_manifest.get("stack_report", {})

    # Optional Developer Stack Banner (shown when audience is 'developer' or 'both')
    stack_html = ""
    if audience in ("developer", "both") and stack_report:
      detected = stack_report.get("detected_stacks", [])
      runtimes = stack_report.get("host_runtimes", {})
      rows = "".join(
          f"<tr><td><strong>{html.escape(s['language'])}</strong></td>"
          f"<td><code>{html.escape(', '.join(s['manifest_files']))}</code></td>"
          f"<td>{html.escape(s['package_manager'])}</td>"
          f"<td><code>{html.escape(s['run_command_hint'])}</code></td></tr>"
          for s in detected
      )
      rt_badges = " • ".join(
          f"<span><strong>{html.escape(k.upper())}</strong>: {html.escape(v)}</span>"
          for k, v in runtimes.items()
      )
      stack_html = f"""
      <section class="dev-stack-card">
        <h2>🛠️ Polyglot Code Stack & Runtime Environment</h2>
        <p class="runtime-bar">{rt_badges}</p>
        {f'<table class="stack-table"><thead><tr><th>Language</th><th>Manifests</th><th>Package Manager</th><th>Run Command</th></tr></thead><tbody>{rows}</tbody></table>' if rows else ''}
      </section>
      """

    steps_html: List[str] = []
    for idx, step in enumerate(self.config.steps, start=1):
      s_meta = rec_steps.get(step.id, {})
      shot_path = s_meta.get(
          "screenshot", f"screenshots/{idx:02d}_{step.id}.png"
      )
      try:
        rel_shot = os.path.relpath(shot_path, self.out_dir)
      except ValueError:
        rel_shot = shot_path

      callout_html = ""
      if step.callout and audience in ("client", "both"):
        c_kind = step.callout.kind
        callout_html = f"""
        <div class="callout callout-{html.escape(c_kind)}">
          <div class="callout-title">{html.escape(step.callout.title)}</div>
          <div class="callout-body">{html.escape(step.callout.text)}</div>
        </div>
        """

      dev_section_html = ""
      if audience in ("developer", "both") and (step.developer_note or step.code_block):
        code_exec = s_meta.get("code_execution") or {}
        code_html = ""
        if step.code_block:
          stdout_text = code_exec.get("stdout") or code_exec.get("stderr") or ""
          output_block = (
              f'<div class="code-output"><strong>Live Output ({code_exec.get("duration_ms", 0)} ms, exit {code_exec.get("exit_code", 0)}):</strong><pre>{html.escape(stdout_text)}</pre></div>'
              if stdout_text
              else ""
          )
          code_html = f"""
          <div class="code-panel">
            <div class="code-header">
              <span>{html.escape(step.code_block.language.upper())}</span>
              <span>{html.escape(step.code_block.filename or 'snippet')}</span>
            </div>
            <pre><code>{html.escape(step.code_block.code)}</code></pre>
            {output_block}
          </div>
          """
        dev_note_p = (
            f'<p class="dev-note"><strong>Developer Note:</strong> {html.escape(step.developer_note)}</p>'
            if step.developer_note
            else ""
        )
        dev_section_html = f"""
        <div class="developer-box">
          {dev_note_p}
          {code_html}
        </div>
        """

      steps_html.append(f"""
      <section class="step-card" id="{html.escape(step.id)}">
        <div class="step-header">
          <span class="step-number">{idx}</span>
          <h2 class="step-title">{html.escape(step.title)}</h2>
        </div>
        <p class="step-instruction">{html.escape(step.instruction)}</p>
        {callout_html}
        {dev_section_html}
        <figure class="screenshot-frame">
          <img src="{html.escape(rel_shot)}" alt="Step {idx}: {html.escape(step.title)}" loading="lazy" />
          <figcaption>Figure {idx} — {html.escape(step.annotation_label or step.title)}</figcaption>
        </figure>
      </section>
      """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(self.config.title)} — {html.escape(b.company_name)}</title>
  <style>
    :root {{
      --primary: {b.primary_color};
      --secondary: {b.secondary_color};
      --accent: {b.accent_color};
      --text: {b.text_color};
      --bg: {b.background_color};
      --font: {b.font_family};
      --mono: {b.mono_font_family};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      font-family: var(--font);
      color: var(--text);
      background: var(--bg);
      line-height: 1.65;
    }}
    .hero {{
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      color: #FFFFFF;
      padding: 3.5rem 2rem;
      text-align: center;
      border-bottom: 6px solid var(--accent);
    }}
    .hero .brand-pill {{
      display: inline-block;
      background: rgba(255, 255, 255, 0.16);
      padding: 0.35rem 1rem;
      border-radius: 999px;
      font-size: 0.9rem;
      font-weight: 600;
      margin-bottom: 1rem;
    }}
    .hero h1 {{ margin: 0 0 0.75rem; font-size: 2.3rem; }}
    .hero p {{ margin: 0 auto; max-width: 720px; font-size: 1.12rem; opacity: 0.94; }}
    .container {{ max-width: 960px; margin: 2.5rem auto; padding: 0 1.5rem; }}
    .dev-stack-card {{
      background: #0F172A;
      color: #F8FAFC;
      border-radius: 16px;
      padding: 1.75rem 2rem;
      margin-bottom: 2rem;
      border: 1px solid #334155;
    }}
    .dev-stack-card h2 {{ margin: 0 0 0.75rem; font-size: 1.3rem; color: #38BDF8; }}
    .runtime-bar {{ font-size: 0.92rem; color: #CBD5E1; margin-bottom: 1rem; }}
    .stack-table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    .stack-table th, .stack-table td {{ padding: 0.6rem 0.8rem; border-bottom: 1px solid #334155; text-align: left; }}
    .stack-table th {{ color: #94A3B8; }}
    .step-card {{
      background: #FFFFFF;
      border-radius: 16px;
      padding: 2rem;
      margin-bottom: 2rem;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.06);
      border: 1px solid #E2E8F0;
      page-break-inside: avoid;
    }}
    .step-header {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }}
    .step-number {{
      width: 40px; height: 40px; border-radius: 50%;
      background: var(--primary); color: #FFFFFF;
      font-weight: 700; font-size: 1.15rem;
      display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
    }}
    .step-title {{ margin: 0; font-size: 1.45rem; color: #0F172A; }}
    .step-instruction {{ font-size: 1.08rem; margin: 0 0 1.25rem; color: #334155; }}
    .callout {{
      border-left: 5px solid var(--primary);
      background: #EFF6FF;
      padding: 1rem 1.25rem;
      border-radius: 8px;
      margin-bottom: 1.25rem;
    }}
    .callout-tip {{ border-left-color: #10B981; background: #ECFDF5; }}
    .callout-warning {{ border-left-color: #F59E0B; background: #FFFBEB; }}
    .callout-important {{ border-left-color: #EF4444; background: #FEF2F2; }}
    .callout-title {{ font-weight: 700; margin-bottom: 0.25rem; color: #0F172A; }}
    .developer-box {{
      background: #F8FAFC;
      border: 1px solid #CBD5E1;
      border-radius: 12px;
      padding: 1rem 1.25rem;
      margin-bottom: 1.25rem;
    }}
    .dev-note {{ margin: 0 0 0.75rem; color: #1E293B; font-size: 0.96rem; }}
    .code-panel {{ background: #0F172A; color: #E2E8F0; border-radius: 10px; overflow: hidden; }}
    .code-header {{
      display: flex; justify-content: space-between;
      background: #1E293B; padding: 0.45rem 1rem;
      font-size: 0.82rem; font-family: var(--mono); color: #38BDF8;
    }}
    .code-panel pre {{ margin: 0; padding: 1rem; overflow-x: auto; font-family: var(--mono); font-size: 0.9rem; }}
    .code-output {{
      border-top: 1px solid #334155;
      background: #020617;
      padding: 0.75rem 1rem;
      color: #4ADE80;
      font-family: var(--mono);
      font-size: 0.86rem;
    }}
    .screenshot-frame {{
      margin: 1rem 0 0;
      border: 1px solid #CBD5E1;
      border-radius: 12px;
      overflow: hidden;
      background: #F1F5F9;
    }}
    .screenshot-frame img {{ display: block; width: 100%; height: auto; }}
    .screenshot-frame figcaption {{
      padding: 0.65rem 1rem; font-size: 0.9rem; color: #475569;
      background: #F8FAFC; border-top: 1px solid #E2E8F0; text-align: center;
    }}
    .footer-card {{
      text-align: center; padding: 2.5rem 1.5rem;
      background: #FFFFFF; border-radius: 16px;
      border: 1px solid #E2E8F0; margin-top: 3rem;
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="brand-pill">{html.escape(b.company_name)} • Version {html.escape(self.config.version)} • Audience: {html.escape(audience.capitalize())}</div>
    <h1>{html.escape(self.config.title)}</h1>
    <p>{html.escape(self.config.description)}</p>
  </header>
  <main class="container">
    {stack_html}
    {"".join(steps_html)}
    <footer class="footer-card">
      <h3>{html.escape(b.outro_title)}</h3>
      <p>{html.escape(b.outro_contact)}</p>
    </footer>
  </main>
</body>
</html>
"""

  def _build_markdown(self, recording_manifest: Dict[str, Any]) -> str:
    b = self.config.branding
    audience = self.config.audience
    rec_steps = {s["id"]: s for s in recording_manifest.get("steps", [])}
    stack_report = recording_manifest.get("stack_report", {})

    lines: List[str] = [
        f"# {self.config.title}",
        "",
        f"**{b.company_name}** | Version {self.config.version} | Audience: `{audience}`",
        "",
        f"{self.config.description}",
        "",
    ]

    if audience in ("developer", "both") and stack_report:
      lines.append("## Polyglot Stack & Host Runtimes")
      lines.append("")
      runtimes = stack_report.get("host_runtimes", {})
      for k, v in runtimes.items():
        lines.append(f"- **{k.upper()}**: `{v}`")
      lines.append("")
      detected = stack_report.get("detected_stacks", [])
      if detected:
        lines.append("| Language | Manifests | Package Manager | Run Command |")
        lines.append("| :--- | :--- | :--- | :--- |")
        for s in detected:
          lines.append(
              f"| {s['language']} | `{', '.join(s['manifest_files'])}` | {s['package_manager']} | `{s['run_command_hint']}` |"
          )
        lines.append("")

    for idx, step in enumerate(self.config.steps, start=1):
      s_meta = rec_steps.get(step.id, {})
      shot_path = s_meta.get(
          "screenshot", f"screenshots/{idx:02d}_{step.id}.png"
      )
      try:
        rel_shot = os.path.relpath(shot_path, self.out_dir)
      except ValueError:
        rel_shot = shot_path

      lines.append(f"## Step {idx}: {step.title}")
      lines.append("")
      lines.append(step.instruction)
      lines.append("")

      if step.callout and audience in ("client", "both"):
        badge = step.callout.kind.upper()
        lines.append(f"> **{badge} — {step.callout.title}:** {step.callout.text}")
        lines.append("")

      if audience in ("developer", "both"):
        if step.developer_note:
          lines.append(f"**Developer Note:** {step.developer_note}")
          lines.append("")
        if step.code_block:
          lines.append(f"```{step.code_block.language}")
          lines.append(step.code_block.code)
          lines.append("```")
          lines.append("")
          code_exec = s_meta.get("code_execution") or {}
          out = code_exec.get("stdout") or code_exec.get("stderr")
          if out:
            lines.append(f"**Execution Output ({code_exec.get('duration_ms', 0)} ms):**")
            lines.append("```text")
            lines.append(out)
            lines.append("```")
            lines.append("")

      lines.append(f"![Step {idx}: {step.title}]({rel_shot})")
      lines.append("")

    lines.append("## Open-Source License Compliance")
    lines.append("")
    lines.append("| Component | License | Commercial Restrictions |")
    lines.append("| :--- | :--- | :--- |")
    for item in OPEN_SOURCE_LICENSE_MANIFEST:
      lines.append(
          f"| {item['component']} | `{item['license']}` | {item['commercial_restrictions']} |"
      )
    lines.append("")
    lines.append(f"## {b.outro_title}")
    lines.append("")
    lines.append(b.outro_contact)
    lines.append("")
    return "\n".join(lines)

  def _export_pdf(self, html_path: Path, pdf_path: Path) -> None:
    for chrome_bin in ("chromium", "chromium-browser", "google-chrome"):
      if shutil.which(chrome_bin) and not os.environ.get("GUIDEFORGE_OFFLINE"):
        try:
          res = subprocess.run(
              [
                  chrome_bin,
                  "--headless",
                  "--disable-gpu",
                  "--no-sandbox",
                  f"--print-to-pdf={pdf_path.resolve()}",
                  f"file://{html_path.resolve()}",
              ],
              capture_output=True,
              text=True,
              timeout=6,
          )
          if res.returncode == 0 and pdf_path.exists():
            return
        except Exception:
          pass

    if PIL_AVAILABLE:
      pages: List[Image.Image] = []
      for idx, step in enumerate(self.config.steps, start=1):
        shot = self.out_dir / "screenshots" / f"{idx:02d}_{step.id}.png"
        if shot.exists():
          pages.append(Image.open(shot).convert("RGB"))
      if pages:
        pages[0].save(
            pdf_path, save_all=True, append_images=pages[1:], resolution=150.0
        )

  def _export_docx(
      self, recording_manifest: Dict[str, Any], docx_path: Path
  ) -> None:
    try:
      import docx
      from docx.shared import Inches, Pt, RGBColor
    except ImportError:
      logger.warning("python-docx not installed; skipping DOCX generation.")
      return

    doc = docx.Document()
    b = self.config.branding
    audience = self.config.audience
    primary_rgb = _hex_to_rgb(b.primary_color)

    title_heading = doc.add_heading(self.config.title, level=0)
    for run in title_heading.runs:
      run.font.color.rgb = RGBColor(*primary_rgb)

    subtitle_p = doc.add_paragraph(
        f"{b.company_name} • Version {self.config.version} • Audience: {audience.capitalize()}\n{self.config.description}"
    )
    subtitle_p.style.font.size = Pt(11)

    rec_steps = {s["id"]: s for s in recording_manifest.get("steps", [])}

    for idx, step in enumerate(self.config.steps, start=1):
      h = doc.add_heading(f"Step {idx}: {step.title}", level=1)
      for run in h.runs:
        run.font.color.rgb = RGBColor(*primary_rgb)

      doc.add_paragraph(step.instruction)

      if step.callout and audience in ("client", "both"):
        cp = doc.add_paragraph()
        r_bold = cp.add_run(f"{step.callout.title}: ")
        r_bold.bold = True
        cp.add_run(step.callout.text)

      if audience in ("developer", "both"):
        if step.developer_note:
          dp = doc.add_paragraph()
          dr = dp.add_run("Developer Note: ")
          dr.bold = True
          dp.add_run(step.developer_note)
        if step.code_block:
          code_p = doc.add_paragraph(
              f"[{step.code_block.language.upper()}] {step.code_block.filename or 'snippet'}:\n{step.code_block.code}"
          )
          code_p.style.font.size = Pt(9.5)
          s_meta = rec_steps.get(step.id, {})
          code_exec = s_meta.get("code_execution") or {}
          out = code_exec.get("stdout") or code_exec.get("stderr")
          if out:
            out_p = doc.add_paragraph(f"Output ({code_exec.get('duration_ms', 0)} ms): {out}")
            out_p.style.font.size = Pt(9.5)

      s_meta = rec_steps.get(step.id, {})
      shot_path = Path(
          s_meta.get(
              "screenshot",
              self.out_dir / "screenshots" / f"{idx:02d}_{step.id}.png",
          )
      )
      if shot_path.exists():
        doc.add_picture(str(shot_path), width=Inches(6.0))

    doc.add_heading(b.outro_title, level=2)
    doc.add_paragraph(b.outro_contact)
    doc.save(str(docx_path))
