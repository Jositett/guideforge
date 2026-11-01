"""Shared helper utilities for media probing, font loading, colors, and subtitle timestamps."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, List, Tuple

try:
  from PIL import Image, ImageDraw, ImageFont
  PIL_AVAILABLE = True
except ImportError:
  PIL_AVAILABLE = False

logger = logging.getLogger("guideforge")

# ==============================================================================
# 7. HELPER UTILITIES
# ==============================================================================


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
  h = hex_color.lstrip("#")
  if len(h) == 3:
    h = "".join(c * 2 for c in h)
  return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _load_font(size: int, bold: bool = False) -> Any:
  if not PIL_AVAILABLE:
    return None
  candidates = (
      [
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
      ]
      if bold
      else [
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
      ]
  )
  for path in candidates:
    if os.path.exists(path):
      try:
        return ImageFont.truetype(path, size=size)
      except Exception:
        pass
  return ImageFont.load_default()


def _probe_media_duration(media_path: Path, fallback_text: str = "") -> float:
  if shutil.which("ffprobe") and media_path.exists():
    res = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
      val = float(res.stdout.strip())
      if val > 0:
        return val
    except ValueError:
      pass
  return max(2.2, len(fallback_text.split()) / 2.6)


def _generate_silent_audio(output_path: Path, duration_sec: float) -> None:
  if shutil.which("ffmpeg"):
    _run_cmd([
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{duration_sec:.2f}",
        str(output_path),
    ])
  else:
    output_path.write_bytes(b"")


def _run_cmd(cmd: List[str]) -> None:
  res = subprocess.run(cmd, capture_output=True, text=True)
  if res.returncode != 0:
    logger.debug("Command %s returned %d: %s", cmd[0], res.returncode, res.stderr)


def _split_caption_chunks(text: str, max_chars: int = 72) -> List[str]:
  words = text.split()
  chunks: List[str] = []
  current: List[str] = []
  for w in words:
    candidate = " ".join(current + [w])
    if len(candidate) > max_chars and current:
      chunks.append(" ".join(current))
      current = [w]
    else:
      current.append(w)
  if current:
    chunks.append(" ".join(current))
  return chunks or [text]


def _format_timestamp_srt(seconds: float) -> str:
  millis = int(round(seconds * 1000))
  hrs = millis // 3_600_000
  millis %= 3_600_000
  mins = millis // 60_000
  millis %= 60_000
  secs = millis // 1000
  ms = millis % 1000
  return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
  return _format_timestamp_srt(seconds).replace(",", ".")


