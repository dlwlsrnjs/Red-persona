#!/usr/bin/env python3
"""Aggregate case-clustered Qwen attention analyses and render a cohort figure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CONDITIONS = ("direct_goal", "short_research", "long_research")
LABELS = {
    "direct_goal": "Direct GOAL",
    "short_research": "Short readout",
    "long_research": "Long 7-stage",
}
COLORS = {
    "direct_goal": (45, 96, 160),
    "short_research": (224, 126, 39),
    "long_research": (42, 137, 94),
}
SEGMENTS = (
    "system", "persona_packet", "initial_analysis", "research_dialogue",
    "goal_or_final_question", "assistant_prefix",
)
SEGMENT_LABELS = {
    "system": "System",
    "persona_packet": "Persona/history",
    "initial_analysis": "Initial analysis",
    "research_dialogue": "Research dialogue",
    "goal_or_final_question": "GOAL/final question",
    "assistant_prefix": "Assistant prefix",
}
SEGMENT_COLORS = {
    "system": (55, 91, 145),
    "persona_packet": (86, 148, 181),
    "initial_analysis": (127, 181, 166),
    "research_dialogue": (89, 151, 96),
    "goal_or_final_question": (224, 141, 58),
    "assistant_prefix": (155, 117, 172),
}
METRICS = {
    "positional_js": "Positional JS similarity to direct GOAL",
    "goal_cosine": "Attention-weighted GOAL cosine",
    "goal_enrichment": "Top-decile GOAL-attention enrichment",
    "entropy": "Normalized attention entropy",
}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def late_mean(condition: dict, key: str) -> float:
    values = np.asarray(condition[key], dtype=np.float64)
    start = int(condition["late_layer_start_zero_based"])
    return float(values[start:].mean())


def record_metrics(record: dict) -> dict:
    conditions = record["conditions"]
    output = {}
    for name in CONDITIONS:
        condition = conditions[name]
        output[name] = {
            "goal_cosine": late_mean(
                condition, "attention_weighted_goal_cosine_by_layer"
            ),
            "goal_enrichment": late_mean(
                condition, "goal_top_decile_attention_enrichment_by_layer"
            ),
            "entropy": late_mean(
                condition, "normalized_attention_entropy_by_layer"
            ),
            "segments": {
                segment: float(condition["late_layer_segment_mass"][segment])
                for segment in SEGMENTS
            },
            "heatmap": np.asarray(
                condition["relative_attention_by_layer"], dtype=np.float64
            ),
        }
    output["direct_goal"]["positional_js"] = 1.0
    for name in ("short_research", "long_research"):
        output[name]["positional_js"] = float(
            record["comparisons"][name]["late_layer_mean_js_similarity"]
        )
    return output


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator,
                      repetitions: int) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=np.float64)
    estimate = float(values.mean())
    draws = rng.integers(0, len(values), size=(repetitions, len(values)))
    means = values[draws].mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return estimate, float(lower), float(upper)


def bootstrap_delta_ci(left: np.ndarray, right: np.ndarray,
                       rng: np.random.Generator,
                       repetitions: int) -> tuple[float, float, float]:
    return bootstrap_mean_ci(
        np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64),
        rng,
        repetitions,
    )


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


def heat_color(value: float) -> tuple[int, int, int]:
    stops = (
        (0.00, (246, 248, 250)),
        (0.25, (185, 215, 226)),
        (0.50, (87, 164, 183)),
        (0.75, (38, 112, 151)),
        (1.00, (18, 58, 99)),
    )
    value = float(np.clip(value, 0.0, 1.0))
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if value <= x1:
            ratio = (value - x0) / (x1 - x0)
            return tuple(int(a + ratio * (b - a)) for a, b in zip(c0, c1))
    return stops[-1][1]


def draw_grouped_metrics(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                         summary: dict) -> None:
    left, top, right, bottom = box
    draw.text((left, top), "A. Case-clustered late-layer means (95% bootstrap CI)",
              fill=(24, 29, 38), font=font(28, True))
    plot_top = top + 60
    panel_width = (right - left - 45) // 2
    panel_height = (bottom - plot_top - 35) // 2
    for index, (metric, label) in enumerate(METRICS.items()):
        col, row = index % 2, index // 2
        x0 = left + col * (panel_width + 45)
        y0 = plot_top + row * (panel_height + 35)
        x1, y1 = x0 + panel_width, y0 + panel_height
        draw.text((x0, y0), label, fill=(36, 42, 52), font=font(20, True))
        chart_top, chart_bottom = y0 + 35, y1 - 34
        values = [summary["metrics"][metric][name] for name in CONDITIONS]
        lower = min(row_["ci95_low"] for row_ in values)
        upper = max(row_["ci95_high"] for row_ in values)
        if metric in ("positional_js", "entropy"):
            axis_low, axis_high = max(0.0, lower - 0.08), min(1.0, upper + 0.08)
        else:
            padding = max((upper - lower) * 0.35, 0.05)
            axis_low, axis_high = lower - padding, upper + padding
        if axis_high <= axis_low:
            axis_high = axis_low + 1.0
        draw.line((x0 + 70, chart_top, x0 + 70, chart_bottom),
                  fill=(165, 171, 180), width=2)
        draw.line((x0 + 70, chart_bottom, x1 - 15, chart_bottom),
                  fill=(165, 171, 180), width=2)
        for tick in range(5):
            value = axis_low + (axis_high - axis_low) * tick / 4
            y = chart_bottom - (chart_bottom - chart_top) * tick / 4
            draw.line((x0 + 64, y, x1 - 15, y), fill=(226, 229, 233), width=1)
            draw.text((x0, y - 10), f"{value:.2f}", fill=(77, 84, 94),
                      font=font(15))
        slot = (x1 - x0 - 100) / 3
        for condition_index, name in enumerate(CONDITIONS):
            row_ = summary["metrics"][metric][name]
            center = x0 + 84 + slot * (condition_index + 0.5)
            map_y = lambda value: chart_bottom - (
                (value - axis_low) / (axis_high - axis_low)
            ) * (chart_bottom - chart_top)
            mean_y = map_y(row_["mean"])
            low_y, high_y = map_y(row_["ci95_low"]), map_y(row_["ci95_high"])
            draw.line((center, high_y, center, low_y), fill=COLORS[name], width=4)
            draw.line((center - 8, high_y, center + 8, high_y),
                      fill=COLORS[name], width=3)
            draw.line((center - 8, low_y, center + 8, low_y),
                      fill=COLORS[name], width=3)
            draw.ellipse((center - 8, mean_y - 8, center + 8, mean_y + 8),
                         fill=COLORS[name])
            label_short = ("Direct" if name == "direct_goal" else
                           "Short" if name == "short_research" else "Long")
            bbox = draw.textbbox((0, 0), label_short, font=font(15))
            draw.text((center - (bbox[2] - bbox[0]) / 2, chart_bottom + 8),
                      label_short, fill=(57, 63, 72), font=font(15))


def draw_heatmaps(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                  summary: dict) -> None:
    left, top, right, bottom = box
    draw.text((left, top), "B. Mean final-query attention by layer and relative position",
              fill=(24, 29, 38), font=font(28, True))
    heatmaps = {
        name: np.asarray(summary["mean_relative_attention_by_layer"][name],
                         dtype=np.float64)
        for name in CONDITIONS
    }
    maximum = max(float(value.max()) for value in heatmaps.values())
    panel_gap = 28
    panel_width = (right - left - panel_gap * 2) // 3
    y0, y1 = top + 62, bottom - 52
    for index, name in enumerate(CONDITIONS):
        x0 = left + index * (panel_width + panel_gap)
        x1 = x0 + panel_width
        values = heatmaps[name]
        layers, bins = values.shape
        for layer in range(layers):
            py0 = y0 + (y1 - y0) * layer / layers
            py1 = y0 + (y1 - y0) * (layer + 1) / layers
            for bin_index in range(bins):
                px0 = x0 + (x1 - x0) * bin_index / bins
                px1 = x0 + (x1 - x0) * (bin_index + 1) / bins
                draw.rectangle((px0, py0, px1 + 1, py1 + 1),
                               fill=heat_color(values[layer, bin_index] / maximum))
        draw.rectangle((x0, y0, x1, y1), outline=(114, 121, 132), width=2)
        label = LABELS[name]
        bbox = draw.textbbox((0, 0), label, font=font(20, True))
        draw.text((x0 + (panel_width - (bbox[2] - bbox[0])) / 2, y0 - 31),
                  label, fill=COLORS[name], font=font(20, True))
        draw.text((x0, y1 + 10), "Earlier", fill=(75, 81, 91), font=font(15))
        end_label = "Later"
        bbox = draw.textbbox((0, 0), end_label, font=font(15))
        draw.text((x1 - (bbox[2] - bbox[0]), y1 + 10), end_label,
                  fill=(75, 81, 91), font=font(15))
    draw.text((left - 42, y0 + (y1 - y0) / 2), "Layer →",
              fill=(75, 81, 91), font=font(16))


def draw_segments(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                  summary: dict) -> None:
    left, top, right, bottom = box
    draw.text((left, top), "C. Late-layer attention mass by prompt segment",
              fill=(24, 29, 38), font=font(28, True))
    y = top + 66
    label_width = 185
    bar_left, bar_right = left + label_width, right
    for name in CONDITIONS:
        draw.text((left, y + 9), LABELS[name], fill=COLORS[name],
                  font=font(18, True))
        x = bar_left
        for segment in SEGMENTS:
            value = summary["segments"][name][segment]["mean"]
            width = (bar_right - bar_left) * value
            if width > 0:
                draw.rectangle((x, y, x + width, y + 40),
                               fill=SEGMENT_COLORS[segment])
            x += width
        draw.rectangle((bar_left, y, bar_right, y + 40),
                       outline=(117, 124, 134), width=1)
        y += 64
    legend_y = bottom - 34
    x = left
    for segment in SEGMENTS:
        draw.rectangle((x, legend_y, x + 20, legend_y + 20),
                       fill=SEGMENT_COLORS[segment])
        x += 28
        label = SEGMENT_LABELS[segment]
        draw.text((x, legend_y), label, fill=(60, 66, 75), font=font(15))
        x += draw.textbbox((0, 0), label, font=font(15))[2] + 28


def render_figure(summary: dict, path: Path) -> None:
    image = Image.new("RGB", (2400, 2500), (250, 251, 252))
    draw = ImageDraw.Draw(image)
    draw.text((110, 65), "Qwen2.5-7B attention under three research-context depths",
              fill=(20, 25, 34), font=font(42, True))
    subtitle = (
        f"{summary['cases']} cases × {summary['directions_per_case']} branches; "
        "branches averaged within case; error bars resample cases"
    )
    draw.text((110, 122), subtitle, fill=(76, 83, 94), font=font(22))
    draw_grouped_metrics(draw, (110, 190, 2290, 1120), summary)
    draw_heatmaps(draw, (110, 1180, 2290, 1920), summary)
    draw_segments(draw, (110, 1980, 2290, 2390), summary)
    draw.text((110, 2440),
              "Descriptive Qwen proxy analysis; attention similarity is not causal evidence of harmful stimulation.",
              fill=(91, 97, 106), font=font(18))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(300, 300))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--expected-directions", type=int, default=4)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261012)
    args = parser.parse_args()

    paths = sorted(args.input_root.rglob("attention_metrics.json"))
    records = {}
    source_hashes = []
    for path in paths:
        record = load_json(path)
        key = (str(record["case_id"]), str(record["direction"]))
        if key in records:
            raise ValueError(f"duplicate case/direction: {key}")
        records[key] = record_metrics(record)
        source_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
    grouped = defaultdict(list)
    for (case_id, _direction), value in records.items():
        grouped[case_id].append(value)
    if len(grouped) != args.expected_cases:
        raise ValueError(f"expected {args.expected_cases} cases, found {len(grouped)}")
    wrong = {case_id: len(values) for case_id, values in grouped.items()
             if len(values) != args.expected_directions}
    if wrong:
        raise ValueError(f"unexpected directions per case: {wrong}")

    rng = np.random.default_rng(args.seed)
    case_ids = sorted(grouped)
    case_metrics = {
        metric: {condition: [] for condition in CONDITIONS}
        for metric in METRICS
    }
    case_segments = {
        condition: {segment: [] for segment in SEGMENTS}
        for condition in CONDITIONS
    }
    case_heatmaps = {condition: [] for condition in CONDITIONS}
    rows = []
    for case_id in case_ids:
        branches = grouped[case_id]
        row = {"case_id": case_id, "branches": len(branches)}
        for condition in CONDITIONS:
            for metric in METRICS:
                value = float(np.mean([
                    branch[condition][metric] for branch in branches
                ]))
                case_metrics[metric][condition].append(value)
                row[f"{condition}_{metric}"] = value
            for segment in SEGMENTS:
                value = float(np.mean([
                    branch[condition]["segments"][segment]
                    for branch in branches
                ]))
                case_segments[condition][segment].append(value)
            case_heatmaps[condition].append(np.mean([
                branch[condition]["heatmap"] for branch in branches
            ], axis=0))
        rows.append(row)

    summary = {
        "version": "qwen-attention-horizon-cohort-v1",
        "status": "complete",
        "cases": len(case_ids),
        "directions_per_case": args.expected_directions,
        "analyses": len(records),
        "aggregation": "mean directions within case, then mean cases",
        "bootstrap": {
            "unit": "case", "repetitions": args.bootstrap, "seed": args.seed,
            "interval": "percentile 95%",
        },
        "metrics": {},
        "paired_long_minus_short": {},
        "segments": {},
        "mean_relative_attention_by_layer": {},
        "source_manifest_sha256": hashlib.sha256(
            "\n".join(sorted(source_hashes)).encode()
        ).hexdigest(),
        "interpretation_limit": (
            "Descriptive Qwen proxy analysis. Attention similarity does not "
            "establish causal harmful stimulation or GPT-4o internal mechanism."
        ),
    }
    for metric in METRICS:
        summary["metrics"][metric] = {}
        for condition in CONDITIONS:
            estimate, lower, upper = bootstrap_mean_ci(
                np.asarray(case_metrics[metric][condition]), rng, args.bootstrap
            )
            summary["metrics"][metric][condition] = {
                "mean": estimate, "ci95_low": lower, "ci95_high": upper,
            }
        estimate, lower, upper = bootstrap_delta_ci(
            np.asarray(case_metrics[metric]["long_research"]),
            np.asarray(case_metrics[metric]["short_research"]),
            rng,
            args.bootstrap,
        )
        summary["paired_long_minus_short"][metric] = {
            "mean": estimate, "ci95_low": lower, "ci95_high": upper,
        }
    for condition in CONDITIONS:
        summary["segments"][condition] = {}
        for segment in SEGMENTS:
            estimate, lower, upper = bootstrap_mean_ci(
                np.asarray(case_segments[condition][segment]), rng,
                args.bootstrap,
            )
            summary["segments"][condition][segment] = {
                "mean": estimate, "ci95_low": lower, "ci95_high": upper,
            }
        summary["mean_relative_attention_by_layer"][condition] = np.mean(
            np.stack(case_heatmaps[condition], axis=0), axis=0
        ).tolist()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "aggregate_metrics.json", summary)
    with (args.output_dir / "case_level_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render_figure(summary, args.output_dir / "attention_cohort_comparison.png")
    print(json.dumps({
        "status": "complete",
        "cases": len(case_ids),
        "analyses": len(records),
        "output": str(args.output_dir),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
