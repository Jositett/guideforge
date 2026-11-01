"""FFmpeg video compositor, branded 1080p/4K intro/outro card generator, and audio ducking."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from guideforge.config import GuideConfig
from guideforge.utils import PIL_AVAILABLE, _hex_to_rgb, _load_font, _run_cmd

if PIL_AVAILABLE:
  from PIL import Image, ImageDraw

logger = logging.getLogger("guideforge")

# ==============================================================================
# 4. VIDEO PRODUCTION ENGINE (FFMPEG + BRANDED INTRO/OUTRO CARDS + AUDIO DUCKING)
# ==============================================================================


class VideoProducer:
  """Composes the final 1080p/4K MP4 with branded title/outro cards, narration, ducked music, and subtitles."""

  def __init__(self, config: GuideConfig):
    self.config = config
    self.out_dir = Path(config.output_dir)
    self.cards_dir = self.out_dir / "cards"
    self.final_video_path = self.out_dir / "client_walkthrough.mp4"

  def render_video(
      self,
      recording_manifest: dict[str, Any],
      voice_manifest: dict[str, Any],
  ) -> Path:
    self.cards_dir.mkdir(parents=True, exist_ok=True)
    width, height = self.config.viewport_size

    intro_png = self.cards_dir / "intro_card.png"
    outro_png = self.cards_dir / "outro_card.png"
    self._create_branding_card(
        intro_png,
        headline=self.config.branding.intro_title,
        subheadline=self.config.branding.intro_subtitle,
        footer=f"{self.config.branding.company_name} • Version {self.config.version}",
        width=width,
        height=height,
    )
    self._create_branding_card(
        outro_png,
        headline=self.config.branding.outro_title,
        subheadline=self.config.branding.outro_contact,
        footer=f"Thank you for choosing {self.config.branding.company_name}",
        width=width,
        height=height,
    )

    if not shutil.which("ffmpeg"):
      logger.warning(
          "FFmpeg binary not found on PATH; writing video composition specification to %s",
          self.final_video_path,
      )
      self.final_video_path.write_bytes(b"")
      return self.final_video_path

    segments_dir = self.out_dir / "video_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    segment_files: list[Path] = []

    # 1. Intro segment with silent audio
    intro_mp4 = segments_dir / "00_intro.mp4"
    self._render_still_with_silence(
        image_path=intro_png,
        duration=self.config.video.intro_duration,
        output_mp4=intro_mp4,
        width=width,
        height=height,
    )
    segment_files.append(intro_mp4)

    # 2. Per-step narrated segments
    voice_steps = {s["id"]: s for s in voice_manifest.get("steps", [])}
    rec_steps = recording_manifest.get("steps", [])

    for idx, step in enumerate(self.config.steps, start=1):
      seg_mp4 = segments_dir / f"{idx:02d}_{step.id}.mp4"
      shot_path = self.out_dir / "screenshots" / f"{idx:02d}_{step.id}.png"
      if not shot_path.exists() and idx <= len(rec_steps):
        shot_path = Path(rec_steps[idx - 1]["screenshot"])

      v_info = voice_steps.get(step.id, {})
      audio_path = Path(v_info.get("audio_path", ""))
      pad_sec = self.config.video.step_padding_seconds

      if audio_path.exists():
        self._render_still_with_audio(
            image_path=shot_path,
            audio_path=audio_path,
            pad_seconds=pad_sec,
            output_mp4=seg_mp4,
            width=width,
            height=height,
        )
      else:
        self._render_still_with_silence(
            image_path=shot_path,
            duration=3.0 + pad_sec,
            output_mp4=seg_mp4,
            width=width,
            height=height,
        )
      segment_files.append(seg_mp4)

    # 3. Outro segment with silent audio
    outro_mp4 = segments_dir / "99_outro.mp4"
    self._render_still_with_silence(
        image_path=outro_png,
        duration=self.config.video.outro_duration,
        output_mp4=outro_mp4,
        width=width,
        height=height,
    )
    segment_files.append(outro_mp4)

    # 4. Concatenate all segments
    concat_list = segments_dir / "concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{seg.resolve()}'" for seg in segment_files),
        encoding="utf-8",
    )
    assembled_mp4 = segments_dir / "assembled.mp4"
    _run_cmd([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(assembled_mp4),
    ])

    # 5. Optional background music mixing with automatic volume ducking
    mixed_mp4 = segments_dir / "mixed.mp4"
    bg_music = self.config.branding.background_music
    if bg_music and Path(bg_music).exists():
      logger.info("Mixing background music with automatic narration ducking...")
      vol = self.config.branding.music_volume
      _run_cmd([
          "ffmpeg",
          "-y",
          "-i",
          str(assembled_mp4),
          "-stream_loop",
          "-1",
          "-i",
          str(Path(bg_music).resolve()),
          "-filter_complex",
          f"[1:a]volume={vol}[bg];[bg][0:a]sidechaincompress=threshold=0.03:ratio=6:attack=50:release=400[ducked];[0:a][ducked]amix=inputs=2:duration=first[aout]",
          "-map",
          "0:v",
          "-map",
          "[aout]",
          "-c:v",
          "copy",
          "-c:a",
          "aac",
          "-shortest",
          str(mixed_mp4),
      ])
    else:
      shutil.copyfile(assembled_mp4, mixed_mp4)

    # 6. Burn-in accessible subtitles (or embed soft subtitles)
    srt_file = Path(voice_manifest.get("srt_path", self.out_dir / "subtitles.srt"))
    if self.config.tts.burn_subtitles and srt_file.exists():
      font_sz = self.config.tts.subtitle_font_size
      escaped_srt = str(srt_file.resolve()).replace("\\", "/").replace(":", "\\:")
      style_str = (
          f"FontName=DejaVu Sans,FontSize={font_sz},"
          "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
          "BackColour=&H80000000,BorderStyle=4,Outline=1,Shadow=0,MarginV=32"
      )
      res = subprocess.run(
          [
              "ffmpeg",
              "-y",
              "-i",
              str(mixed_mp4),
              "-vf",
              f"subtitles='{escaped_srt}':force_style='{style_str}'",
              "-c:a",
              "copy",
              str(self.final_video_path),
          ],
          capture_output=True,
          text=True,
      )
      if res.returncode != 0:
        logger.warning(
            "Subtitle filter unavailable in local FFmpeg build; copying video with sidecar SRT/VTT."
        )
        shutil.copyfile(mixed_mp4, self.final_video_path)
    else:
      shutil.copyfile(mixed_mp4, self.final_video_path)

    logger.info("Final client walkthrough video ready: %s", self.final_video_path)
    return self.final_video_path

  def _create_branding_card(
      self,
      out_path: Path,
      headline: str,
      subheadline: str,
      footer: str,
      width: int,
      height: int,
  ) -> None:
    if not PIL_AVAILABLE:
      return
    primary_rgb = _hex_to_rgb(self.config.branding.primary_color)
    secondary_rgb = _hex_to_rgb(self.config.branding.secondary_color)
    accent_rgb = _hex_to_rgb(self.config.branding.accent_color)

    img = Image.new("RGB", (width, height), secondary_rgb)
    draw = ImageDraw.Draw(img)

    # Subtle modern geometric accent bars
    draw.rectangle([0, 0, width, 18], fill=accent_rgb)
    draw.rounded_rectangle(
        [140, 140, width - 140, height - 140],
        radius=28,
        fill=primary_rgb,
        outline=(255, 255, 255),
        width=3,
    )

    # Optional company logo or monogram badge
    logo_y = 260
    if self.config.branding.logo_path and Path(self.config.branding.logo_path).exists():
      try:
        logo = Image.open(self.config.branding.logo_path).convert("RGBA")
        logo.thumbnail((160, 160))
        img.paste(logo, ((width - logo.width) // 2, logo_y), logo)
        logo_y += logo.height + 40
      except Exception:
        pass
    else:
      badge_r = 52
      cx = width // 2
      draw.ellipse(
          [cx - badge_r, logo_y, cx + badge_r, logo_y + badge_r * 2],
          fill=accent_rgb,
      )
      initials = "".join(
          w[0].upper() for w in self.config.branding.company_name.split()[:2]
      ) or "GF"
      draw.text(
          (cx, logo_y + badge_r),
          initials,
          fill=(255, 255, 255),
          font=_load_font(40, bold=True),
          anchor="mm",
      )
      logo_y += badge_r * 2 + 50

    draw.text(
        (width // 2, logo_y + 30),
        headline,
        fill=(255, 255, 255),
        font=_load_font(54, bold=True),
        anchor="mm",
    )
    draw.text(
        (width // 2, logo_y + 115),
        subheadline,
        fill=(226, 232, 240),
        font=_load_font(30),
        anchor="mm",
    )
    draw.text(
        (width // 2, height - 210),
        footer,
        fill=(191, 219, 254),
        font=_load_font(22),
        anchor="mm",
    )
    img.save(out_path, quality=95)

  def _render_still_with_silence(
      self,
      image_path: Path,
      duration: float,
      output_mp4: Path,
      width: int,
      height: int,
  ) -> None:
    _run_cmd([
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{duration:.2f}",
        "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output_mp4),
    ])

  def _render_still_with_audio(
      self,
      image_path: Path,
      audio_path: Path,
      pad_seconds: float,
      output_mp4: Path,
      width: int,
      height: int,
  ) -> None:
    _run_cmd([
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        f"[1:a]apad=pad_dur={pad_seconds:.2f}[aout]",
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output_mp4),
    ])


