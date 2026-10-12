#!/usr/bin/env python3
"""Render the full-context and isolated-readout geometry analyses side by side."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CONDITIONS = ("direct_goal", "short_research", "long_research")
LABELS = {
    "direct_goal": "Direct GOAL",
    "short_research": "Short readout",
    "long_research": "Long 7-stage",
}
COLORS = {
    "direct_goal": (43, 96, 160),
    "short_research": (224, 126, 39),
    "long_research": (42, 137, 94),
}


def font(size: int, bold: bool = False):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def y_position(value: float, low: float, high: float,
               chart_top: float, chart_bottom: float) -> float:
    return chart_bottom - (value - low) / max(high - low, 1e-12) * (
        chart_bottom - chart_top
    )


def metric_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                 summary: dict, metric: str, title: str,
                 subtitle: str, lower_is_better: bool = False) -> None:
    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=18, fill=(255, 255, 255),
                           outline=(224, 228, 233), width=2)
    draw.text((left + 28, top + 22), title, font=font(22, True), fill=(27, 33, 42))
    draw.text((left + 28, top + 56), subtitle, font=font(15), fill=(90, 97, 107))
    rows = [summary["late_metrics"][metric][name] for name in CONDITIONS]
    low = min(row["ci95_low"] for row in rows)
    high = max(row["ci95_high"] for row in rows)
    padding = max((high - low) * 0.16, 0.006)
    axis_low, axis_high = low - padding, high + padding
    chart_left, chart_right = left + 92, right - 24
    chart_top, chart_bottom = top + 103, bottom - 68
    for tick in range(5):
        value = axis_low + tick * (axis_high - axis_low) / 4
        y = y_position(value, axis_low, axis_high, chart_top, chart_bottom)
        draw.line((chart_left, y, chart_right, y), fill=(232, 235, 239), width=1)
        draw.text((left + 18, y - 9), f"{value:.2f}", font=font(13),
                  fill=(91, 98, 108))
    draw.line((chart_left, chart_top, chart_left, chart_bottom),
              fill=(162, 168, 177), width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom),
              fill=(162, 168, 177), width=2)
    slot = (chart_right - chart_left) / len(CONDITIONS)
    for index, name in enumerate(CONDITIONS):
        row = summary["late_metrics"][metric][name]
        x = chart_left + slot * (index + 0.5)
        mean_y = y_position(row["mean"], axis_low, axis_high, chart_top, chart_bottom)
        low_y = y_position(row["ci95_low"], axis_low, axis_high, chart_top, chart_bottom)
        high_y = y_position(row["ci95_high"], axis_low, axis_high, chart_top, chart_bottom)
        draw.line((x, high_y, x, low_y), fill=COLORS[name], width=5)
        draw.line((x - 10, high_y, x + 10, high_y), fill=COLORS[name], width=3)
        draw.line((x - 10, low_y, x + 10, low_y), fill=COLORS[name], width=3)
        draw.ellipse((x - 9, mean_y - 9, x + 9, mean_y + 9), fill=COLORS[name])
        label = {"direct_goal": "Direct", "short_research": "Short",
                 "long_research": "Long"}[name]
        label_box = draw.textbbox((0, 0), label, font=font(15))
        draw.text((x - (label_box[2] - label_box[0]) / 2, chart_bottom + 14),
                  label, font=font(15), fill=(63, 70, 80))
    cue = "↓ lower is farther from harm axis" if lower_is_better else "↑ higher is closer"
    draw.text((right - 270, bottom - 31), cue, font=font(13, True),
              fill=(57, 91, 80) if lower_is_better else (65, 78, 103))


def render(full: dict, readout: dict, output: Path) -> None:
    image = Image.new("RGB", (2300, 1570), (247, 249, 251))
    draw = ImageDraw.Draw(image)
    draw.text((92, 45), "Qwen representation geometry: full context vs isolated readout",
              font=font(39, True), fill=(22, 28, 37))
    draw.text((92, 100),
              "197 cases × 4 branches; branch means within case; late layers L24/L28; 95% case-bootstrap CI",
              font=font(20), fill=(74, 82, 93))
    panels = (
        (full, "exact_goal_cosine", "A. Full context · exact GOAL", "Meaning retained from the source request", False),
        (full, "loo_harm_projection", "B. Full context · matched harm axis", "Leave-one-case-out A−B direction", True),
        (full, "ood_harm_cosine", "C. Full context · OOD harm", "Six unrelated public harm categories", True),
        (readout, "matched_harm_cosine", "D. Isolated readout · matched case", "Target's last research statement only", False),
        (readout, "loo_harm_projection", "E. Isolated readout · matched harm axis", "Length-controlled target statement", True),
        (readout, "ood_harm_cosine", "F. Isolated readout · OOD harm", "Length-controlled sensitivity check", True),
    )
    boxes = (
        (92, 175, 786, 765), (803, 175, 1497, 765), (1514, 175, 2208, 765),
        (92, 790, 786, 1380), (803, 790, 1497, 1380), (1514, 790, 2208, 1380),
    )
    for box, panel in zip(boxes, panels):
        metric_panel(draw, box, *panel)
    x = 92
    for name in CONDITIONS:
        draw.line((x, 1450, x + 40, 1450), fill=COLORS[name], width=7)
        draw.text((x + 53, 1437), LABELS[name], font=font(17), fill=(50, 58, 68))
        x += 315
    draw.text((92, 1503),
              "Hidden-state geometry is a descriptive Qwen proxy, not evidence that generated answers are safe or causal.",
              font=font(16), fill=(90, 97, 106))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-summary", type=Path, required=True)
    parser.add_argument("--readout-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    render(load(args.full_summary), load(args.readout_summary), args.output)
    print(args.output)


if __name__ == "__main__":
    main()
