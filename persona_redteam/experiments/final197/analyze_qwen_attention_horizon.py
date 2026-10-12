"""Compare Qwen attention for direct-GOAL, short, and long research prompts.

This is a proxy interpretability analysis: GPT-4o does not expose internal
attention, so the exact same registered prompt artifacts are replayed through
the pinned Qwen2.5-7B-Instruct checkpoint.  To avoid materializing an O(n^2)
attention matrix for long conversations, the script performs an SDPA prefill
without attentions and then one fixed-probe decode step with eager attention.
The returned tensors are therefore only [head, 1, context_length].
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

from pipeline.runtime_io import atomic_json


ROOT = Path(__file__).resolve().parents[2]
QWEN_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
QWEN_MODEL = "Qwen/Qwen2.5-7B-Instruct"
QWEN_SNAPSHOT = ROOT / ".cache/qwen2.5-7b-instruct" / QWEN_REVISION
LONG_WITH_HISTORY = (
    ROOT / "result/OURS/final197_1011_singleton_gpt4o_v1/"
    "gpt4o/no_verbatim/merged"
)
LONG_NO_HISTORY = (
    ROOT / "result/OURS/final197_1011_singleton_gpt4o_v1/"
    "gpt4o/no_history/merged"
)
SHORT_WITH_HISTORY = (
    ROOT / "result/OURS/final197_no_research_pair_gpt4o_v2/"
    "gpt4o/with_history/merged"
)
SHORT_NO_HISTORY = (
    ROOT / "result/OURS/final197_no_research_pair_gpt4o_v2/"
    "gpt4o/no_history/merged"
)
DEFAULT_OUTPUT = ROOT / "result/OURS/qwen_attention_research_horizon_v1"
CONDITION_ORDER = ("direct_goal", "short_research", "long_research")
CONDITION_LABELS = {
    "direct_goal": "Direct GOAL",
    "short_research": "Short readout",
    "long_research": "Long 7-stage",
}
GROUP_ORDER = (
    "system",
    "persona_packet",
    "initial_analysis",
    "research_dialogue",
    "goal_or_final_question",
    "assistant_prefix",
)
GROUP_LABELS = {
    "system": "System",
    "persona_packet": "Persona/history",
    "initial_analysis": "Initial analysis",
    "research_dialogue": "Research dialogue",
    "goal_or_final_question": "GOAL/final question",
    "assistant_prefix": "Assistant prefix",
}
SERIES_COLORS = {
    "direct_goal": (34, 92, 156),
    "short_research": (226, 127, 33),
    "long_research": (43, 131, 90),
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_hash(value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256_text(payload)


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def result(record: dict) -> dict:
    rows = record.get("results", [])
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("run record must contain exactly one result")
    return rows[0]


def branch_for(record: dict, direction: str) -> dict:
    rows = [
        row for row in result(record).get("final_branches", [])
        if row.get("direction") == direction
    ]
    if len(rows) != 1:
        raise ValueError(f"expected one branch for direction={direction!r}")
    return rows[0]


def context_messages(branch: dict) -> list[dict]:
    context = branch.get("recovery_context", branch.get("context", {}))
    messages = context.get("full_messages", [])
    if not isinstance(messages, list) or not messages:
        raise ValueError("branch does not contain recovery context messages")
    copied = deepcopy(messages)
    if copied[-1].get("role") != "user":
        raise ValueError("attention prompt must end with a user question")
    return copied


def registered_goal(record: dict) -> str:
    private_goal = str(result(record).get("private_goal", "")).strip()
    case = record.get("case", {})
    original = str(case.get("original_request", "")).strip()
    strict = case.get("strict_harmful_request", {})
    strict_text = str(strict.get("request_text", "")).strip()
    if not private_goal or not (private_goal == original == strict_text):
        raise ValueError("private GOAL is not exactly bound to the registered request")
    expected_hash = str(strict.get("request_sha256", ""))
    if expected_hash != sha256_text(private_goal):
        raise ValueError("registered private GOAL hash mismatch")
    return private_goal


def build_conditions(
    long_record: dict, short_record: dict, direction: str
) -> tuple[str, dict[str, list[dict]]]:
    long_goal = registered_goal(long_record)
    short_goal = registered_goal(short_record)
    if long_goal != short_goal:
        raise ValueError("long and short records use different private GOALs")
    long_case = str(long_record.get("case", {}).get("case_id", ""))
    short_case = str(short_record.get("case", {}).get("case_id", ""))
    if not long_case or long_case != short_case:
        raise ValueError("long and short records use different case IDs")
    long_messages = context_messages(branch_for(long_record, direction))
    short_messages = context_messages(branch_for(short_record, direction))
    if long_messages[0].get("role") != "system":
        raise ValueError("long prompt does not begin with a system message")
    if short_messages[0] != long_messages[0]:
        raise ValueError("long and short prompts do not share the target system prompt")
    return long_goal, {
        "direct_goal": [
            deepcopy(short_messages[0]),
            {"role": "user", "content": long_goal},
        ],
        "short_research": short_messages,
        "long_research": long_messages,
    }


def chat_input_ids(tokenizer, messages: list[dict], *, generation: bool) -> list[int]:
    encoded = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=generation,
        return_tensors=None,
    )
    if isinstance(encoded, Mapping):
        encoded = encoded["input_ids"]
    if hasattr(encoded, "tolist"):
        encoded = encoded.tolist()
    if encoded and isinstance(encoded[0], list):
        encoded = encoded[0]
    return [int(value) for value in encoded]


def message_group(condition: str, index: int, total: int) -> str:
    if index == 0:
        return "system"
    if condition == "direct_goal":
        return "goal_or_final_question"
    if index == 1:
        return "persona_packet"
    if index == 2:
        return "initial_analysis"
    if index == total - 1:
        return "goal_or_final_question"
    return "research_dialogue"


def prompt_layout(tokenizer, condition: str, messages: list[dict]) -> dict:
    full_ids = chat_input_ids(tokenizer, messages, generation=True)
    spans = []
    previous = 0
    for index in range(len(messages)):
        boundary = len(chat_input_ids(
            tokenizer, messages[:index + 1], generation=False
        ))
        if boundary < previous:
            raise ValueError("chat-template prefix length is not monotonic")
        spans.append({
            "message_index": index,
            "role": str(messages[index].get("role", "")),
            "group": message_group(condition, index, len(messages)),
            "start": previous,
            "end": boundary,
        })
        previous = boundary
    if previous > len(full_ids):
        raise ValueError("chat-template boundary exceeds full prompt")
    spans.append({
        "message_index": None,
        "role": "assistant_generation_prefix",
        "group": "assistant_prefix",
        "start": previous,
        "end": len(full_ids),
    })
    return {"input_ids": full_ids, "spans": spans}


def find_subsequence(sequence: list[int], needle: list[int]) -> tuple[int, int] | None:
    if not needle or len(needle) > len(sequence):
        return None
    for start in range(len(sequence) - len(needle), -1, -1):
        if sequence[start:start + len(needle)] == needle:
            return start, start + len(needle)
    return None


def relative_bins(values: np.ndarray, bins: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not len(values):
        raise ValueError("relative_bins requires a nonempty vector")
    if bins < 2:
        raise ValueError("bins must be at least 2")
    indices = np.minimum(
        bins - 1,
        (np.arange(len(values), dtype=np.int64) * bins) // len(values),
    )
    output = np.zeros(bins, dtype=np.float64)
    np.add.at(output, indices, values)
    total = output.sum()
    return output / total if total > 0 else output


def jensen_shannon_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.shape != right.shape or left.ndim != 1:
        raise ValueError("Jensen-Shannon inputs must be same-sized vectors")
    left = left / max(left.sum(), 1e-15)
    right = right / max(right.sum(), 1e-15)
    midpoint = 0.5 * (left + right)

    def divergence(value):
        mask = value > 0
        return float(np.sum(value[mask] * np.log2(value[mask] / midpoint[mask])))

    distance = 0.5 * divergence(left) + 0.5 * divergence(right)
    return float(np.clip(1.0 - distance, 0.0, 1.0))


def normalized_entropy(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    values = values / max(values.sum(), 1e-15)
    positive = values[values > 0]
    if len(values) <= 1:
        return 0.0
    return float(-np.sum(positive * np.log(positive)) / math.log(len(values)))


def segment_masses(attention: np.ndarray, spans: list[dict]) -> dict[str, float]:
    masses = {name: 0.0 for name in GROUP_ORDER}
    for span in spans:
        group = span["group"]
        masses[group] += float(attention[span["start"]:span["end"]].sum())
    return masses


def prompt_tokens(tokenizer, goal: str) -> list[int]:
    encoded = tokenizer(goal, add_special_tokens=False)
    ids = encoded["input_ids"] if isinstance(encoded, Mapping) else encoded.input_ids
    return [int(value) for value in ids]


def load_model(device: str, dtype_name: str, model_path: Path | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }[dtype_name]
    source = model_path or (QWEN_SNAPSHOT if QWEN_SNAPSHOT.exists() else QWEN_MODEL)
    load_kwargs = (
        {"local_files_only": True}
        if isinstance(source, Path)
        else {"revision": QWEN_REVISION}
    )
    tokenizer = AutoTokenizer.from_pretrained(source, **load_kwargs)
    model = AutoModelForCausalLM.from_pretrained(
        source,
        **load_kwargs,
        dtype=dtype,
        attn_implementation="sdpa",
        low_cpu_mem_usage=True,
    ).eval().to(device)
    return torch, tokenizer, model


def extract_condition(
    *,
    torch,
    tokenizer,
    model,
    device: str,
    condition: str,
    messages: list[dict],
    goal: str,
    goal_vector,
    probe_token_id: int,
    bins: int,
    late_layers: int,
    max_context_tokens: int,
    include_token_text: bool,
) -> tuple[dict, object]:
    layout = prompt_layout(tokenizer, condition, messages)
    ids = layout["input_ids"]
    if len(ids) > max_context_tokens:
        raise ValueError(
            f"{condition}: {len(ids)} tokens exceeds --max-context-tokens "
            f"{max_context_tokens}; do not silently truncate an attention comparison"
        )
    model_limit = int(getattr(model.config, "max_position_embeddings", 0) or 0)
    if model_limit and len(ids) + 1 > model_limit:
        raise ValueError(
            f"{condition}: {len(ids) + 1} tokens exceeds model limit {model_limit}"
        )
    input_ids = torch.tensor([ids], dtype=torch.long, device=device)
    model.set_attn_implementation("sdpa")
    with torch.inference_mode():
        prefill = model.model(
            input_ids=input_ids,
            use_cache=True,
            output_attentions=False,
            output_hidden_states=False,
            return_dict=True,
        )
        hidden = prefill.last_hidden_state[0].float()
        if goal_vector is None:
            exact_span = find_subsequence(ids, prompt_tokens(tokenizer, goal))
            if exact_span is None:
                goal_spans = [
                    row for row in layout["spans"]
                    if row["group"] == "goal_or_final_question"
                ]
                if len(goal_spans) != 1:
                    raise ValueError("cannot identify direct GOAL token span")
                exact_span = (goal_spans[0]["start"], goal_spans[0]["end"])
            goal_vector = hidden[exact_span[0]:exact_span[1]].mean(dim=0)
            goal_vector = torch.nn.functional.normalize(goal_vector, dim=0)
        normalized_hidden = torch.nn.functional.normalize(hidden, dim=-1)
        goal_similarity = normalized_hidden @ goal_vector
        probe = torch.tensor([[probe_token_id]], dtype=torch.long, device=device)
        model.set_attn_implementation("eager")
        decoded = model.model(
            input_ids=probe,
            past_key_values=prefill.past_key_values,
            use_cache=False,
            output_attentions=True,
            output_hidden_states=False,
            return_dict=True,
        )
        layer_attention = []
        for value in decoded.attentions:
            if value is None or value.shape[-2] != 1:
                raise RuntimeError("fixed-probe attention tensor is unavailable")
            row = value[0, :, 0, :len(ids)].float().mean(dim=0)
            row = row / row.sum().clamp_min(1e-15)
            layer_attention.append(row.cpu().numpy())
        layer_attention = np.stack(layer_attention, axis=0)
        goal_similarity_np = goal_similarity.cpu().numpy()
    del decoded, prefill, hidden, normalized_hidden, input_ids, probe
    torch.cuda.empty_cache()

    bin_profiles = np.stack([
        relative_bins(row, bins) for row in layer_attention
    ], axis=0)
    threshold = float(np.quantile(goal_similarity_np, 0.90))
    goal_mask = goal_similarity_np >= threshold
    goal_mass = layer_attention[:, goal_mask].sum(axis=1)
    weighted_goal_similarity = layer_attention @ goal_similarity_np
    entropies = np.array([
        normalized_entropy(row) for row in layer_attention
    ], dtype=np.float64)
    per_layer_segments = [
        segment_masses(row, layout["spans"]) for row in layer_attention
    ]
    late_start = max(0, len(layer_attention) - late_layers)
    late_attention = layer_attention[late_start:].mean(axis=0)
    late_segment_mass = segment_masses(late_attention, layout["spans"])
    joint_salience = late_attention * np.clip(goal_similarity_np, 0.0, None)
    top_indices = np.argsort(joint_salience)[-20:][::-1]
    tokens = tokenizer.convert_ids_to_tokens(ids) if include_token_text else None
    top_rows = []
    for index in top_indices:
        row = {
            "token_index": int(index),
            "attention": float(late_attention[index]),
            "goal_cosine": float(goal_similarity_np[index]),
            "joint_salience": float(joint_salience[index]),
            "group": next(
                span["group"] for span in layout["spans"]
                if span["start"] <= index < span["end"]
            ),
        }
        if tokens is not None:
            row["token"] = str(tokens[index]).replace("\n", "\\n")
        top_rows.append(row)
    record = {
        "condition": condition,
        "label": CONDITION_LABELS[condition],
        "messages": len(messages),
        "tokens": len(ids),
        "prompt_sha256": canonical_json_hash(messages),
        "private_goal_text_stored": False,
        "spans": layout["spans"],
        "layers": len(layer_attention),
        "relative_attention_bins": bins,
        "relative_attention_by_layer": bin_profiles.tolist(),
        "segment_mass_by_layer": per_layer_segments,
        "late_layer_start_zero_based": late_start,
        "late_layer_segment_mass": late_segment_mass,
        "attention_weighted_goal_cosine_by_layer": (
            weighted_goal_similarity.tolist()
        ),
        "goal_top_decile_attention_mass_by_layer": goal_mass.tolist(),
        "goal_top_decile_attention_enrichment_by_layer": (
            goal_mass / 0.10
        ).tolist(),
        "normalized_attention_entropy_by_layer": entropies.tolist(),
        "goal_similarity_threshold_top_decile": threshold,
        "top_goal_weighted_tokens": top_rows,
    }
    return record, goal_vector


def add_comparisons(conditions: dict[str, dict]) -> dict:
    baseline = np.asarray(
        conditions["direct_goal"]["relative_attention_by_layer"], dtype=np.float64
    )
    comparisons = {}
    for name in ("short_research", "long_research"):
        candidate = np.asarray(
            conditions[name]["relative_attention_by_layer"], dtype=np.float64
        )
        if candidate.shape != baseline.shape:
            raise ValueError("attention layers/bins differ across conditions")
        per_layer = [
            jensen_shannon_similarity(left, right)
            for left, right in zip(baseline, candidate)
        ]
        late_start = int(conditions[name]["late_layer_start_zero_based"])
        comparisons[name] = {
            "direct_goal_relative_attention_js_similarity_by_layer": per_layer,
            "late_layer_mean_js_similarity": float(np.mean(per_layer[late_start:])),
            "interpretation": (
                "descriptive similarity of normalized positional attention; "
                "not evidence of causal harmful stimulation"
            ),
        }
    return comparisons


def color_ramp(value: float) -> tuple[int, int, int]:
    stops = (
        (0.00, (26, 32, 66)),
        (0.25, (39, 91, 132)),
        (0.50, (41, 145, 137)),
        (0.75, (126, 190, 92)),
        (1.00, (249, 224, 74)),
    )
    value = float(np.clip(value, 0.0, 1.0))
    for (left_x, left), (right_x, right) in zip(stops, stops[1:]):
        if value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            return tuple(int(a + ratio * (b - a)) for a, b in zip(left, right))
    return stops[-1][1]


def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_line_chart(draw, box, series: dict[str, list[float]], y_label: str) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, outline=(175, 181, 190), width=2)
    values = [value for row in series.values() for value in row]
    y_min, y_max = min(values), max(values)
    padding = max((y_max - y_min) * 0.08, 1e-4)
    y_min -= padding
    y_max += padding
    font = load_font(22)
    small = load_font(18)
    draw.text((left, top - 34), y_label, fill=(28, 32, 38), font=font)
    for tick in range(5):
        y = top + (bottom - top) * tick / 4
        value = y_max - (y_max - y_min) * tick / 4
        draw.line((left, y, right, y), fill=(224, 227, 232), width=1)
        draw.text((left - 78, y - 10), f"{value:.2f}", fill=(75, 81, 89), font=small)
    length = max(len(row) for row in series.values())
    for name, row in series.items():
        color = SERIES_COLORS[name]
        points = []
        for index, value in enumerate(row):
            x = left + (right - left) * index / max(length - 1, 1)
            y = bottom - (bottom - top) * (value - y_min) / (y_max - y_min)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=color, width=4)
        for point in points[::max(1, len(points) // 8)]:
            x, y = point
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
    draw.text((left, bottom + 12), "Early layers", fill=(75, 81, 89), font=small)
    label = "Late layers"
    width = draw.textbbox((0, 0), label, font=small)[2]
    draw.text((right - width, bottom + 12), label, fill=(75, 81, 89), font=small)


def draw_stacked_segments(draw, box, conditions: dict[str, dict]) -> None:
    left, top, right, bottom = box
    title = load_font(22)
    font = load_font(19)
    draw.text((left, top - 38), "Late-layer attention mass by prompt segment",
              fill=(28, 32, 38), font=title)
    segment_colors = {
        "system": (90, 98, 108),
        "persona_packet": (73, 111, 173),
        "initial_analysis": (112, 153, 211),
        "research_dialogue": (80, 160, 120),
        "goal_or_final_question": (225, 132, 55),
        "assistant_prefix": (164, 112, 188),
    }
    row_height = (bottom - top) / 3
    for row_index, name in enumerate(CONDITION_ORDER):
        y0 = top + row_index * row_height + 12
        y1 = y0 + 42
        label = CONDITION_LABELS[name]
        draw.text((left, y0 - 28), label, fill=(28, 32, 38), font=font)
        cursor = left
        masses = conditions[name]["late_layer_segment_mass"]
        for group in GROUP_ORDER:
            width = (right - left) * float(masses.get(group, 0.0))
            if width > 0:
                draw.rectangle((cursor, y0, cursor + width, y1),
                               fill=segment_colors[group])
            cursor += width
    legend_y = bottom + 8
    cursor = left
    for group in GROUP_ORDER:
        label = GROUP_LABELS[group]
        draw.rectangle((cursor, legend_y, cursor + 18, legend_y + 18),
                       fill=segment_colors[group])
        draw.text((cursor + 25, legend_y - 2), label, fill=(60, 66, 74), font=font)
        cursor += draw.textbbox((0, 0), label, font=font)[2] + 58


def render_png(record: dict, path: Path) -> None:
    from PIL import Image, ImageDraw

    width, height = 2200, 1900
    image = Image.new("RGB", (width, height), (250, 250, 249))
    draw = ImageDraw.Draw(image)
    title = load_font(42, bold=True)
    subtitle = load_font(23)
    panel_font = load_font(25, bold=True)
    axis_font = load_font(18)
    draw.text((90, 55), "Qwen fixed-probe attention across research horizons",
              fill=(24, 28, 34), font=title)
    draw.text(
        (90, 112),
        f"case={record['case_id']} · branch={record['direction']} · "
        "same registered private GOAL",
        fill=(79, 84, 92),
        font=subtitle,
    )
    conditions = record["conditions"]
    matrices = [
        np.asarray(conditions[name]["relative_attention_by_layer"], dtype=np.float64)
        for name in CONDITION_ORDER
    ]
    transformed = [np.log1p(matrix * matrix.shape[1] * 8.0) for matrix in matrices]
    global_max = max(float(matrix.max()) for matrix in transformed)
    panel_top, panel_bottom = 220, 860
    gap = 45
    panel_width = (width - 180 - 2 * gap) // 3
    for index, (name, matrix) in enumerate(zip(CONDITION_ORDER, transformed)):
        left = 90 + index * (panel_width + gap)
        right = left + panel_width
        draw.text((left, panel_top - 48), CONDITION_LABELS[name],
                  fill=(24, 28, 34), font=panel_font)
        draw.text((left, panel_top - 18),
                  f"{conditions[name]['tokens']:,} tokens · "
                  f"{conditions[name]['messages']} messages",
                  fill=(79, 84, 92), font=axis_font)
        rows, columns = matrix.shape
        cell_w = (right - left) / columns
        cell_h = (panel_bottom - panel_top) / rows
        for layer in range(rows):
            for column in range(columns):
                value = matrix[layer, column] / max(global_max, 1e-12)
                x0 = int(left + column * cell_w)
                x1 = int(left + (column + 1) * cell_w + 1)
                y0 = int(panel_top + layer * cell_h)
                y1 = int(panel_top + (layer + 1) * cell_h + 1)
                draw.rectangle((x0, y0, x1, y1), fill=color_ramp(value))
        draw.rectangle((left, panel_top, right, panel_bottom),
                       outline=(125, 130, 138), width=2)
        draw.text((left, panel_bottom + 10), "0%", fill=(79, 84, 92), font=axis_font)
        draw.text((right - 48, panel_bottom + 10), "100%", fill=(79, 84, 92), font=axis_font)
        draw.text((left - 60, panel_top - 5), "L1", fill=(79, 84, 92), font=axis_font)
        draw.text((left - 70, panel_bottom - 22), f"L{rows}",
                  fill=(79, 84, 92), font=axis_font)
    draw.text((90, 900), "Relative prompt position →",
              fill=(79, 84, 92), font=subtitle)
    goal_series = {
        name: conditions[name]["attention_weighted_goal_cosine_by_layer"]
        for name in CONDITION_ORDER
    }
    draw_line_chart(
        draw, (170, 1020, 1050, 1370), goal_series,
        "Attention-weighted semantic similarity to registered GOAL",
    )
    similarity_series = {
        name: record["comparisons"][name][
            "direct_goal_relative_attention_js_similarity_by_layer"
        ]
        for name in ("short_research", "long_research")
    }
    draw_line_chart(
        draw, (1240, 1020, 2120, 1370), similarity_series,
        "Positional attention similarity to direct GOAL (1 = identical)",
    )
    draw_stacked_segments(draw, (120, 1520, 2080, 1735), conditions)
    legend_x, legend_y = 1470, 930
    for name in CONDITION_ORDER:
        color = SERIES_COLORS[name]
        draw.line((legend_x, legend_y, legend_x + 42, legend_y), fill=color, width=5)
        draw.text((legend_x + 55, legend_y - 12), CONDITION_LABELS[name],
                  fill=(52, 57, 65), font=axis_font)
        legend_x += 220
    footer = (
        "Descriptive proxy only: attention similarity is not a causal safety or "
        "harmfulness measure. Fixed probe; late-layer segment mass uses the final 8 layers."
    )
    draw.text((90, 1840), footer, fill=(79, 84, 92), font=axis_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", dpi=(200, 200), optimize=True)


def analyze_case(
    *,
    case_id: str,
    direction: str,
    long_dir: Path,
    short_dir: Path,
    output_dir: Path,
    torch,
    tokenizer,
    model,
    device: str,
    probe_text: str,
    bins: int,
    late_layers: int,
    max_context_tokens: int,
    include_token_text: bool,
) -> dict:
    long_path = long_dir / f"{case_id}.json"
    short_path = short_dir / f"{case_id}.json"
    long_record = load_object(long_path)
    short_record = load_object(short_path)
    goal, message_sets = build_conditions(long_record, short_record, direction)
    probe_ids = prompt_tokens(tokenizer, probe_text)
    if len(probe_ids) != 1:
        raise ValueError(
            f"--probe-text must tokenize to exactly one token, got {len(probe_ids)}"
        )
    goal_vector = None
    condition_records = {}
    for condition in CONDITION_ORDER:
        condition_record, goal_vector = extract_condition(
            torch=torch,
            tokenizer=tokenizer,
            model=model,
            device=device,
            condition=condition,
            messages=message_sets[condition],
            goal=goal,
            goal_vector=goal_vector,
            probe_token_id=probe_ids[0],
            bins=bins,
            late_layers=late_layers,
            max_context_tokens=max_context_tokens,
            include_token_text=include_token_text,
        )
        condition_records[condition] = condition_record
    record = {
        "version": "qwen-fixed-probe-attention-horizon-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "case_id": case_id,
        "direction": direction,
        "model": QWEN_MODEL,
        "revision": QWEN_REVISION,
        "device": device,
        "probe_text_sha256": sha256_text(probe_text),
        "probe_token_id": probe_ids[0],
        "private_goal_sha256": sha256_text(goal),
        "private_goal_text_stored": False,
        "source_artifacts": {
            "long": str(long_path),
            "short": str(short_path),
        },
        "method": {
            "prefill": "sdpa_without_attention_output",
            "measurement": "one_fixed_probe_decode_step_with_eager_attention",
            "query_length": 1,
            "head_aggregation": "arithmetic_mean",
            "semantic_reference": (
                "mean normalized final hidden state over direct-GOAL content tokens"
            ),
            "late_layers": late_layers,
            "relative_position_bins": bins,
            "causal_claim": False,
            "gpt4o_internal_attention_claim": False,
        },
        "conditions": condition_records,
    }
    record["comparisons"] = add_comparisons(condition_records)
    case_output = output_dir / case_id / direction
    atomic_json(case_output / "attention_metrics.json", record)
    render_png(record, case_output / "attention_comparison.png")
    return {
        "case_id": case_id,
        "direction": direction,
        "metrics": str(case_output / "attention_metrics.json"),
        "figure": str(case_output / "attention_comparison.png"),
        "tokens": {
            name: condition_records[name]["tokens"] for name in CONDITION_ORDER
        },
        "late_layer_direct_similarity": {
            name: record["comparisons"][name]["late_layer_mean_js_similarity"]
            for name in ("short_research", "long_research")
        },
    }


def selected_case_ids(values: Iterable[str], path: Path | None, limit: int | None):
    ids = [str(value) for value in values if str(value).strip()]
    if path is not None:
        document = load_object(path)
        ids.extend(map(str, document.get("case_ids", [])))
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ValueError("provide --case-id or --case-id-file")
    return ids[:limit] if limit is not None else ids


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--case-id-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--direction", action="append",
        choices=(
            "latent_request_synthesis", "evidence_chain",
            "analyst_response_target", "source_aware_reconstruction",
        ),
    )
    parser.add_argument("--arm", choices=("with_history", "no_history"),
                        default="with_history")
    parser.add_argument("--long-run-dir", type=Path)
    parser.add_argument("--short-run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", default="cuda:3")
    parser.add_argument(
        "--model-path", type=Path,
        help=(
            "Optional local Qwen snapshot. If omitted, use the repository cache "
            "when present, otherwise download the pinned Hugging Face revision."
        ),
    )
    parser.add_argument("--dtype", choices=("bfloat16", "float16", "float32"),
                        default="bfloat16")
    parser.add_argument("--probe-text", default=" analysis")
    parser.add_argument("--bins", type=int, default=128)
    parser.add_argument("--late-layers", type=int, default=8)
    parser.add_argument("--max-context-tokens", type=int, default=32700)
    parser.add_argument("--include-token-text", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.bins < 16:
        parser.error("--bins must be at least 16")
    if args.late_layers < 1:
        parser.error("--late-layers must be at least 1")
    ids = selected_case_ids(args.case_id, args.case_id_file, args.limit)
    directions = tuple(dict.fromkeys(
        args.direction or ["latent_request_synthesis"]
    ))
    long_dir = args.long_run_dir or (
        LONG_WITH_HISTORY if args.arm == "with_history" else LONG_NO_HISTORY
    )
    short_dir = args.short_run_dir or (
        SHORT_WITH_HISTORY if args.arm == "with_history" else SHORT_NO_HISTORY
    )
    if args.model_path is not None and not args.model_path.exists():
        parser.error(f"--model-path does not exist: {args.model_path}")
    torch, tokenizer, model = load_model(
        args.device, args.dtype, args.model_path
    )
    summaries = []
    for case_id in ids:
        for direction in directions:
            summary = analyze_case(
                case_id=case_id,
                direction=direction,
                long_dir=long_dir,
                short_dir=short_dir,
                output_dir=args.output_dir,
                torch=torch,
                tokenizer=tokenizer,
                model=model,
                device=args.device,
                probe_text=args.probe_text,
                bins=args.bins,
                late_layers=args.late_layers,
                max_context_tokens=args.max_context_tokens,
                include_token_text=args.include_token_text,
            )
            summaries.append(summary)
            print(json.dumps({"progress": "complete", **summary},
                             ensure_ascii=False), flush=True)
    aggregate = {
        "version": "qwen-fixed-probe-attention-horizon-run-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "model": QWEN_MODEL,
        "revision": QWEN_REVISION,
        "arm": args.arm,
        "cases": len(ids),
        "analyses": len(summaries),
        "source_long_run_dir": str(long_dir),
        "source_short_run_dir": str(short_dir),
        "summaries": summaries,
        "interpretation_limit": (
            "Qwen proxy attention is descriptive and cannot establish GPT-4o "
            "mechanism, causal harmful stimulation, or safety-policy bypass."
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output_dir / "run_summary.json", aggregate)
    print(json.dumps({
        "status": "complete",
        "output": str(args.output_dir),
        "analyses": len(summaries),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
