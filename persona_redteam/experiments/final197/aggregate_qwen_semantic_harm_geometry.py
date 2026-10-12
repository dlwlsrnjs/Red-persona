#!/usr/bin/env python3
"""Aggregate Final-197 semantic/harm geometry with case-clustered inference."""
from __future__ import annotations

import argparse
import csv
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
PRIMARY_METRICS = (
    "residual_semantic_specificity",
    "semantic_specificity",
    "loo_harm_projection",
    "ood_harm_cosine",
)
METRIC_LABELS = {
    "residual_semantic_specificity": "Goal-specific meaning (harm-axis removed)",
    "semantic_specificity": "Goal-specific meaning (raw)",
    "loo_harm_projection": "Matched generic-harm projection",
    "ood_harm_cosine": "Out-of-domain harm proximity",
    "exact_goal_cosine": "Exact-GOAL cosine",
    "matched_harm_cosine": "Matched harmful-anchor cosine",
    "matched_benign_cosine": "Matched lower-risk-anchor cosine",
    "matched_harm_preference": "Matched harm vs lower-risk preference",
    "unrelated_harm_cosine": "Unrelated in-domain harm cosine",
    "unrelated_benign_cosine": "Unrelated lower-risk cosine",
    "generic_harm_contrast": "Unrelated harm vs lower-risk contrast",
}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def bootstrap(values: np.ndarray, rng: np.random.Generator,
              repetitions: int) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    indices = rng.integers(0, len(values), size=(repetitions, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return {
        "mean": float(values.mean()),
        "ci95_low": float(low),
        "ci95_high": float(high),
        "sd_across_cases": float(values.std(ddof=1)),
        "n_cases": int(len(values)),
    }


def paired_delta(left: np.ndarray, right: np.ndarray, rng: np.random.Generator,
                 repetitions: int) -> dict[str, float]:
    return bootstrap(
        np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64),
        rng, repetitions,
    )


def font(size: int, bold: bool = False):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def map_value(value: float, low: float, high: float, bottom: float, top: float) -> float:
    return bottom - (value - low) / max(high - low, 1e-12) * (bottom - top)


def draw_metric_panel(draw, box, summary: dict, metric: str, title: str) -> None:
    left, top, right, bottom = box
    draw.text((left, top), title, fill=(25, 31, 40), font=font(23, True))
    rows = [summary["late_metrics"][metric][name] for name in CONDITIONS]
    low = min(row["ci95_low"] for row in rows)
    high = max(row["ci95_high"] for row in rows)
    padding = max((high - low) * 0.30, 0.008)
    axis_low, axis_high = low - padding, high + padding
    chart_left, chart_right = left + 90, right - 20
    chart_top, chart_bottom = top + 60, bottom - 56
    draw.line((chart_left, chart_top, chart_left, chart_bottom),
              fill=(154, 161, 170), width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom),
              fill=(154, 161, 170), width=2)
    for tick in range(5):
        value = axis_low + tick * (axis_high - axis_low) / 4
        y = map_value(value, axis_low, axis_high, chart_bottom, chart_top)
        draw.line((chart_left, y, chart_right, y), fill=(225, 228, 232), width=1)
        draw.text((left, y - 11), f"{value:.3f}", fill=(73, 80, 90), font=font(16))
    slot = (chart_right - chart_left) / len(CONDITIONS)
    for index, name in enumerate(CONDITIONS):
        row = summary["late_metrics"][metric][name]
        x = chart_left + slot * (index + 0.5)
        y = map_value(row["mean"], axis_low, axis_high, chart_bottom, chart_top)
        y_low = map_value(row["ci95_low"], axis_low, axis_high,
                          chart_bottom, chart_top)
        y_high = map_value(row["ci95_high"], axis_low, axis_high,
                           chart_bottom, chart_top)
        draw.line((x, y_high, x, y_low), fill=COLORS[name], width=5)
        draw.line((x - 10, y_high, x + 10, y_high), fill=COLORS[name], width=3)
        draw.line((x - 10, y_low, x + 10, y_low), fill=COLORS[name], width=3)
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=COLORS[name])
        short = {"direct_goal": "Direct", "short_research": "Short",
                 "long_research": "Long"}[name]
        bbox = draw.textbbox((0, 0), short, font=font(17))
        draw.text((x - (bbox[2] - bbox[0]) / 2, chart_bottom + 14), short,
                  fill=(57, 64, 73), font=font(17))


def draw_layer_panel(draw, box, summary: dict) -> None:
    left, top, right, bottom = box
    draw.text((left, top), "C. Goal-specific meaning across layers",
              fill=(25, 31, 40), font=font(23, True))
    layers = summary["layers_one_based"]
    values = {
        name: [summary["by_layer"]["residual_semantic_specificity"][name][str(layer)]["mean"]
               for layer in layers]
        for name in CONDITIONS
    }
    flat = [item for row in values.values() for item in row]
    padding = max((max(flat) - min(flat)) * 0.15, 0.008)
    axis_low, axis_high = min(flat) - padding, max(flat) + padding
    chart_left, chart_right = left + 90, right - 24
    chart_top, chart_bottom = top + 60, bottom - 55
    for tick in range(5):
        value = axis_low + tick * (axis_high - axis_low) / 4
        y = map_value(value, axis_low, axis_high, chart_bottom, chart_top)
        draw.line((chart_left, y, chart_right, y), fill=(225, 228, 232), width=1)
        draw.text((left, y - 11), f"{value:.3f}", fill=(73, 80, 90), font=font(16))
    draw.line((chart_left, chart_top, chart_left, chart_bottom),
              fill=(154, 161, 170), width=2)
    draw.line((chart_left, chart_bottom, chart_right, chart_bottom),
              fill=(154, 161, 170), width=2)
    for name in CONDITIONS:
        points = []
        for index, value in enumerate(values[name]):
            x = chart_left + index * (chart_right - chart_left) / max(len(layers) - 1, 1)
            y = map_value(value, axis_low, axis_high, chart_bottom, chart_top)
            points.append((x, y))
        draw.line(points, fill=COLORS[name], width=5)
        for x, y in points:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=COLORS[name])
    for index, layer in enumerate(layers):
        x = chart_left + index * (chart_right - chart_left) / max(len(layers) - 1, 1)
        label = f"L{layer}"
        bbox = draw.textbbox((0, 0), label, font=font(16))
        draw.text((x - (bbox[2] - bbox[0]) / 2, chart_bottom + 14), label,
                  fill=(57, 64, 73), font=font(16))


def draw_geometry_panel(draw, box, summary: dict) -> None:
    left, top, right, bottom = box
    draw.text((left, top), "D. Meaning–harm geometry (late layers)",
              fill=(25, 31, 40), font=font(23, True))
    x_metric = "residual_semantic_specificity"
    y_metric = "ood_harm_cosine"
    x_rows = [summary["late_metrics"][x_metric][name] for name in CONDITIONS]
    y_rows = [summary["late_metrics"][y_metric][name] for name in CONDITIONS]
    x_low = min(row["ci95_low"] for row in x_rows)
    x_high = max(row["ci95_high"] for row in x_rows)
    y_low = min(row["ci95_low"] for row in y_rows)
    y_high = max(row["ci95_high"] for row in y_rows)
    x_pad = max((x_high - x_low) * 0.35, 0.008)
    y_pad = max((y_high - y_low) * 0.35, 0.008)
    x_low, x_high = x_low - x_pad, x_high + x_pad
    y_low, y_high = y_low - y_pad, y_high + y_pad
    chart_left, chart_right = left + 105, right - 32
    chart_top, chart_bottom = top + 62, bottom - 74
    draw.rectangle((chart_left, chart_top, chart_right, chart_bottom),
                   outline=(154, 161, 170), width=2)
    for tick in range(5):
        x_value = x_low + tick * (x_high - x_low) / 4
        x = chart_left + tick * (chart_right - chart_left) / 4
        draw.line((x, chart_top, x, chart_bottom), fill=(229, 231, 235), width=1)
        draw.text((x - 25, chart_bottom + 12), f"{x_value:.2f}",
                  fill=(73, 80, 90), font=font(15))
        y_value = y_low + tick * (y_high - y_low) / 4
        y = map_value(y_value, y_low, y_high, chart_bottom, chart_top)
        draw.line((chart_left, y, chart_right, y), fill=(229, 231, 235), width=1)
        draw.text((left + 8, y - 10), f"{y_value:.2f}",
                  fill=(73, 80, 90), font=font(15))
    for name in CONDITIONS:
        xr = summary["late_metrics"][x_metric][name]
        yr = summary["late_metrics"][y_metric][name]
        x = chart_left + (xr["mean"] - x_low) / (x_high - x_low) * (chart_right - chart_left)
        y = map_value(yr["mean"], y_low, y_high, chart_bottom, chart_top)
        x0 = chart_left + (xr["ci95_low"] - x_low) / (x_high - x_low) * (chart_right - chart_left)
        x1 = chart_left + (xr["ci95_high"] - x_low) / (x_high - x_low) * (chart_right - chart_left)
        y0 = map_value(yr["ci95_low"], y_low, y_high, chart_bottom, chart_top)
        y1 = map_value(yr["ci95_high"], y_low, y_high, chart_bottom, chart_top)
        draw.line((x0, y, x1, y), fill=COLORS[name], width=4)
        draw.line((x, y1, x, y0), fill=COLORS[name], width=4)
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=COLORS[name])
        draw.text((x + 15, y - 13), LABELS[name], fill=COLORS[name],
                  font=font(17, True))
    x_label = "Goal-specific meaning  → higher"
    bbox = draw.textbbox((0, 0), x_label, font=font(17))
    draw.text((chart_left + (chart_right - chart_left - (bbox[2] - bbox[0])) / 2,
               bottom - 30), x_label, fill=(58, 65, 75), font=font(17))
    draw.text((left, top + 35), "Lower on y = farther from unrelated harmful controls",
              fill=(83, 90, 100), font=font(16))


def render(summary: dict, path: Path) -> None:
    image = Image.new("RGB", (2400, 1760), (250, 251, 252))
    draw = ImageDraw.Draw(image)
    draw.text((100, 55), "Qwen representation geometry: meaning vs generic harm",
              fill=(20, 25, 34), font=font(41, True))
    draw.text((100, 112),
              f"{summary['cases']} cases × {summary['directions_per_case']} branches; "
              "branches averaged within case; 95% case bootstrap CI",
              fill=(76, 83, 94), font=font(21))
    draw_metric_panel(draw, (100, 185, 1165, 760), summary,
                      "residual_semantic_specificity",
                      "A. Case-specific meaning after removing harm axis")
    draw_metric_panel(draw, (1230, 185, 2300, 760), summary,
                      "ood_harm_cosine",
                      "B. Proximity to unrelated out-of-domain harm")
    draw_layer_panel(draw, (100, 845, 1165, 1570), summary)
    draw_geometry_panel(draw, (1230, 845, 2300, 1570), summary)
    x = 100
    for name in CONDITIONS:
        draw.line((x, 1640, x + 42, 1640), fill=COLORS[name], width=6)
        draw.text((x + 55, 1627), LABELS[name], fill=(53, 60, 69), font=font(18))
        x += 300
    footer = (
        "Descriptive proxy using Qwen2.5-7B-Instruct hidden states. "
        "Lower generic-harm proximity does not imply safer model output or causality."
    )
    draw.text((100, 1690), footer, fill=(87, 94, 104), font=font(17))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(300, 300), optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-cases", type=int, default=197)
    parser.add_argument("--expected-directions", type=int, default=4)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261012)
    args = parser.parse_args()
    paths = sorted((args.input_root / "cases").glob("*/*.json"))
    if not paths:
        raise FileNotFoundError(f"no case records below {args.input_root / 'cases'}")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for path in paths:
        record = load_json(path)
        if record.get("status") != "complete":
            continue
        grouped[str(record["case_id"])].append(record)
    if len(grouped) != args.expected_cases:
        raise ValueError(f"expected {args.expected_cases} cases, got {len(grouped)}")
    for case_id, records in grouped.items():
        if len(records) != args.expected_directions:
            raise ValueError(
                f"{case_id}: expected {args.expected_directions} directions, got {len(records)}"
            )
    first = next(iter(grouped.values()))[0]
    layers = [int(value) for value in first["layers_one_based"]]
    metric_names = tuple(first["conditions"][CONDITIONS[0]]["metrics_by_layer"])
    case_values: dict[str, dict[str, list[np.ndarray]]] = {
        metric: {name: [] for name in CONDITIONS} for metric in metric_names
    }
    token_values = {name: [] for name in CONDITIONS}
    case_ids = sorted(grouped)
    for case_id in case_ids:
        records = grouped[case_id]
        for name in CONDITIONS:
            token_values[name].append(float(np.mean([
                record["conditions"][name]["tokens"] for record in records
            ])))
            for metric in metric_names:
                values = np.asarray([
                    record["conditions"][name]["metrics_by_layer"][metric]
                    for record in records
                ], dtype=np.float64)
                case_values[metric][name].append(values.mean(axis=0))
    arrays = {
        metric: {
            name: np.stack(rows, axis=0)
            for name, rows in conditions.items()
        }
        for metric, conditions in case_values.items()
    }
    late_indices = [index for index, layer in enumerate(layers) if layer >= 24]
    if not late_indices:
        late_indices = [len(layers) - 1]
    rng = np.random.default_rng(args.seed)
    summary = {
        "version": "qwen-semantic-harm-geometry-aggregate-v1",
        "cases": len(case_ids),
        "directions_per_case": args.expected_directions,
        "statistical_unit": "case; branches averaged before inference",
        "layers_one_based": layers,
        "late_layers_one_based": [layers[index] for index in late_indices],
        "bootstrap_repetitions": args.bootstrap,
        "metrics_definition": {
            "residual_semantic_specificity": (
                "cosine to own Case A minus mean cosine to other Case A after "
                "removing the leave-one-case-out matched harm axis"
            ),
            "semantic_specificity": (
                "cosine to own Case A minus mean cosine to other Case A"
            ),
            "loo_harm_projection": (
                "projection on leave-one-case-out mean(Case A)-mean(Case B)"
            ),
            "ood_harm_cosine": (
                "mean cosine to public out-of-domain harmful objectives"
            ),
        },
        "by_layer": {},
        "late_metrics": {},
        "paired_deltas": {},
        "tokens": {},
    }
    for metric in metric_names:
        summary["by_layer"][metric] = {}
        summary["late_metrics"][metric] = {}
        summary["paired_deltas"][metric] = {}
        late_by_condition = {}
        for name in CONDITIONS:
            matrix = arrays[metric][name]
            summary["by_layer"][metric][name] = {
                str(layer): bootstrap(matrix[:, index], rng, args.bootstrap)
                for index, layer in enumerate(layers)
            }
            late = matrix[:, late_indices].mean(axis=1)
            late_by_condition[name] = late
            summary["late_metrics"][metric][name] = bootstrap(
                late, rng, args.bootstrap
            )
        for left, right in (
            ("short_research", "direct_goal"),
            ("short_research", "long_research"),
            ("long_research", "direct_goal"),
        ):
            summary["paired_deltas"][metric][f"{left}_minus_{right}"] = paired_delta(
                late_by_condition[left], late_by_condition[right], rng, args.bootstrap
            )
    for name in CONDITIONS:
        summary["tokens"][name] = bootstrap(
            np.asarray(token_values[name]), rng, args.bootstrap
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "semantic_harm_geometry_summary.json", summary)
    with (args.output_dir / "case_level_late_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        fields = ["case_id", "condition", "mean_tokens"] + list(metric_names)
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case_index, case_id in enumerate(case_ids):
            for name in CONDITIONS:
                row = {
                    "case_id": case_id,
                    "condition": name,
                    "mean_tokens": token_values[name][case_index],
                }
                for metric in metric_names:
                    row[metric] = float(
                        arrays[metric][name][case_index, late_indices].mean()
                    )
                writer.writerow(row)
    render(summary, args.output_dir / "semantic_harm_geometry.png")
    print(json.dumps({
        "cases": summary["cases"],
        "directions_per_case": summary["directions_per_case"],
        "late_layers": summary["late_layers_one_based"],
        "figure": str(args.output_dir / "semantic_harm_geometry.png"),
    }, indent=2))


if __name__ == "__main__":
    main()
