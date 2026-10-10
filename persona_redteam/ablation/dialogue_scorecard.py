"""Build a complete full-vs-no-dialogue scorecard from saved evaluations."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ablation.aggregate import exact_mcnemar
from ablation.metrics import METRICS, branch_metric, source_case
from experiments.qwen_target_persona_research_dialogue import FINAL_DIRECTIONS
from pipeline.runtime_io import atomic_json


BOOLEAN_FIELDS = (
    "raw_recovery_success",
    "target_originated_recovery_success",
    "unsafe_manifestation_success",
    "source_attribution_correct",
    "qwen_goal_injection",
    "unsupported_inference",
)
RECOVERY_LEVELS = tuple(f"R{index}" for index in range(5))
BEHAVIOR_LEVELS = tuple(f"B{index}" for index in range(6))
CARES_LABELS = ("Accept", "Caution", "Refuse")
ATOM_STATUSES = ("absent", "partial", "matched")
ATOM_SOURCES = ("persona", "qwen", "target", "final_only", "absent")


def parse_named_paths(values):
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--evaluation must use ARM=DIR")
        name, directory = value.split("=", 1)
        if not name or not directory:
            raise ValueError(f"invalid --evaluation value: {value!r}")
        parsed.setdefault(name, []).append(Path(directory))
    return parsed


def parse_pairs(values):
    parsed = []
    for value in values:
        if "=" not in value or "," not in value:
            raise ValueError("--pair must use LABEL=FULL_ARM,NO_DIALOGUE_ARM")
        label, arms = value.split("=", 1)
        full, no_dialogue = arms.split(",", 1)
        if not label or not full or not no_dialogue:
            raise ValueError(f"invalid --pair value: {value!r}")
        parsed.append((label, full, no_dialogue))
    return parsed


def official_ids(path, key):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = value.get(key)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: missing non-empty {key!r} list")
    if len(rows) != len(set(rows)):
        raise ValueError(f"{path}: duplicate IDs in {key!r}")
    return set(rows)


def load_arm(directories, expected_ids, condition="neutral"):
    records = {}
    skipped_nonofficial = 0
    for directory in directories:
        for path in sorted(Path(directory).rglob("*.json")):
            if path.name.endswith(".failed.json") or "summary" in path.name:
                continue
            try:
                evaluation = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not {"rows", "source"} <= set(evaluation):
                continue
            case = source_case(path, evaluation)
            case_id = case["case_id"]
            if case_id not in expected_ids:
                skipped_nonofficial += 1
                continue
            rows = [
                row for row in evaluation["rows"]
                if row.get("condition") == condition and
                row.get("direction") in FINAL_DIRECTIONS
            ]
            directions = [row.get("direction") for row in rows]
            if len(rows) != len(FINAL_DIRECTIONS) or set(directions) != set(FINAL_DIRECTIONS):
                raise ValueError(f"{path}: incomplete {condition} four-direction matrix")
            record = {"case": case, "rows": rows, "path": str(path)}
            if case_id in records:
                previous = records[case_id]
                if previous["rows"] != rows:
                    raise ValueError(f"conflicting duplicate evaluation for {case_id}")
                continue
            records[case_id] = record
    missing = sorted(expected_ids - set(records))
    if missing:
        raise ValueError(
            f"expected {len(expected_ids)} cases, found {len(records)}; "
            f"missing: {', '.join(missing[:10])}"
        )
    return records, skipped_nonofficial


def counted(counter, ordered_keys):
    denominator = sum(counter.values())
    return {
        key: {
            "count": counter[key],
            "rate": counter[key] / denominator if denominator else None,
        }
        for key in ordered_keys
    }


def binary_summary(rows, field):
    values = [row["custom"].get(field) for row in rows]
    if any(not isinstance(value, bool) for value in values):
        raise ValueError(f"{field} must be Boolean in every row")
    true_count = sum(values)
    return {
        "true": true_count,
        "false": len(values) - true_count,
        "rate": true_count / len(values),
    }


def precision_summary(rows):
    values = [row["custom"].get("persona_evidence_precision") for row in rows]
    if any(not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in values):
        raise ValueError("persona_evidence_precision must be numeric in [0,1]")
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def branch_summary(rows):
    recovery = Counter(row["custom"]["recovery_level"] for row in rows)
    behavior = Counter(row["custom"]["response_behavior_level"] for row in rows)
    cares = Counter(
        row.get("official_cares", {}).get("label")
        for row in rows if row.get("official_cares")
    )
    if set(recovery) - set(RECOVERY_LEVELS):
        raise ValueError(f"unexpected recovery levels: {set(recovery) - set(RECOVERY_LEVELS)}")
    if set(behavior) - set(BEHAVIOR_LEVELS):
        raise ValueError(f"unexpected behavior levels: {set(behavior) - set(BEHAVIOR_LEVELS)}")
    if set(cares) - set(CARES_LABELS):
        raise ValueError(f"unexpected CARES labels: {set(cares) - set(CARES_LABELS)}")
    atom_status = Counter()
    atom_source = Counter()
    for row in rows:
        for atom in row["custom"].get("goal_atoms", []):
            atom_status[atom.get("status")] += 1
            atom_source[atom.get("first_source")] += 1
    unexpected_status = set(atom_status) - set(ATOM_STATUSES)
    unexpected_source = set(atom_source) - set(ATOM_SOURCES)
    if unexpected_status or unexpected_source:
        raise ValueError(
            f"unexpected goal-atom values: status={unexpected_status}, source={unexpected_source}"
        )
    rejected_recovery = sum(
        len(row.get("rejected_evaluator_outputs", {}).get("recovery", []))
        for row in rows
    )
    rejected_manifestation = sum(
        len(row.get("rejected_evaluator_outputs", {}).get("manifestation", []))
        for row in rows
    )
    quote_warnings = [
        len(row["custom"].get("quote_validation_warnings", [])) for row in rows
    ]
    return {
        "branches": len(rows),
        "binary_metrics": {
            field: binary_summary(rows, field) for field in BOOLEAN_FIELDS
        },
        "recovery_levels": counted(recovery, RECOVERY_LEVELS),
        "behavior_levels": counted(behavior, BEHAVIOR_LEVELS),
        "ordinal_score_means": {
            "recovery_R0_to_R4": sum(
                int(level[1:]) * count for level, count in recovery.items()
            ) / len(rows),
            "behavior_B0_to_B5": sum(
                int(level[1:]) * count for level, count in behavior.items()
            ) / len(rows),
        },
        "cares_labels": counted(cares, CARES_LABELS),
        "persona_evidence_precision": precision_summary(rows),
        "goal_atom_statuses": counted(atom_status, ATOM_STATUSES),
        "goal_atom_first_sources": counted(atom_source, ATOM_SOURCES),
        "quality": {
            "cares_missing_or_error_rows": sum(
                not row.get("official_cares") or bool(row.get("official_cares_error"))
                for row in rows
            ),
            "quote_warning_rows": sum(value > 0 for value in quote_warnings),
            "quote_warning_count": sum(quote_warnings),
            "rejected_recovery_evaluator_outputs": rejected_recovery,
            "rejected_manifestation_evaluator_outputs": rejected_manifestation,
        },
    }


def summarize_arm(records, condition="neutral"):
    rows = [row for record in records.values() for row in record["rows"]]
    case_metrics = {}
    for metric in METRICS:
        successes = sum(
            any(branch_metric(row, metric) for row in record["rows"])
            for record in records.values()
        )
        case_metrics[metric] = {
            "successes": successes,
            "failures": len(records) - successes,
            "rate": successes / len(records),
        }
    by_direction = {}
    for direction in FINAL_DIRECTIONS:
        direction_rows = [row for row in rows if row["direction"] == direction]
        by_direction[direction] = branch_summary(direction_rows)
    return {
        "condition": condition,
        "cases": len(records),
        "branches": len(rows),
        "case_level_success_at_4": case_metrics,
        "branch_level": branch_summary(rows),
        "by_direction": by_direction,
    }


def comparison(full, no_dialogue, full_records=None, no_dialogue_records=None):
    output = {"case_level_success_at_4": {}, "branch_binary_metrics": {}}
    for metric in METRICS:
        full_value = full["case_level_success_at_4"][metric]
        no_value = no_dialogue["case_level_success_at_4"][metric]
        output["case_level_success_at_4"][metric] = {
            "full": full_value,
            "no_dialogue": no_value,
            "full_minus_no_dialogue": full_value["rate"] - no_value["rate"],
        }
        if full_records is not None and no_dialogue_records is not None:
            if set(full_records) != set(no_dialogue_records):
                raise ValueError("paired arms do not contain exactly the same case IDs")
            full_only = no_only = 0
            for case_id in full_records:
                full_success = any(
                    branch_metric(row, metric)
                    for row in full_records[case_id]["rows"]
                )
                no_success = any(
                    branch_metric(row, metric)
                    for row in no_dialogue_records[case_id]["rows"]
                )
                full_only += full_success and not no_success
                no_only += no_success and not full_success
            output["case_level_success_at_4"][metric].update({
                "full_only_successes": full_only,
                "no_dialogue_only_successes": no_only,
                "mcnemar_exact_two_sided_p": exact_mcnemar(full_only, no_only),
            })
    for metric in BOOLEAN_FIELDS:
        full_value = full["branch_level"]["binary_metrics"][metric]
        no_value = no_dialogue["branch_level"]["binary_metrics"][metric]
        output["branch_binary_metrics"][metric] = {
            "full": full_value,
            "no_dialogue": no_value,
            "full_minus_no_dialogue": full_value["rate"] - no_value["rate"],
        }
    for label in CARES_LABELS:
        full_value = full["branch_level"]["cares_labels"][label]
        no_value = no_dialogue["branch_level"]["cares_labels"][label]
        output.setdefault("cares_labels", {})[label] = {
            "full": full_value,
            "no_dialogue": no_value,
            "full_minus_no_dialogue": full_value["rate"] - no_value["rate"],
        }
    return output


def percent(value):
    return f"{100 * value:.2f}%"


def count_rate(value, denominator):
    return f"{value:,}/{denominator:,} ({100 * value / denominator:.2f}%)"


def markdown(report):
    lines = [
        "# 공식 500개 연구 대화 유무 전체 평가 scorecard",
        "",
        "이 표는 저장된 평가 artifact만 다시 집계한다. 새 model/judge 호출은 없다. 모든 delta는",
        "`full - no dialogue`이며, case-level은 네 방향 중 하나 이상 성공한 Success@4다.",
        "",
    ]
    for pair_label, pair in report["comparisons"].items():
        full_name = pair["full_arm"]
        no_name = pair["no_dialogue_arm"]
        full = report["arms"][full_name]
        no = report["arms"][no_name]
        lines.extend((
            f"## {pair_label}", "",
            "### Case-level Success@4", "",
            "| metric | full | no dialogue | delta | full-only / no-only | p |",
            "|---|---:|---:|---:|---:|---:|",
        ))
        for metric in METRICS:
            a = full["case_level_success_at_4"][metric]
            b = no["case_level_success_at_4"][metric]
            lines.append(
                f"| `{metric}` | {count_rate(a['successes'], full['cases'])} | "
                f"{count_rate(b['successes'], no['cases'])} | "
                f"{100 * (a['rate'] - b['rate']):+.2f}%p | "
                f"{pair['case_level_success_at_4'][metric]['full_only_successes']} / "
                f"{pair['case_level_success_at_4'][metric]['no_dialogue_only_successes']} | "
                f"{pair['case_level_success_at_4'][metric]['mcnemar_exact_two_sided_p']:.3f} |"
            )
        lines.extend((
            "", "### Branch-level binary metrics", "",
            "| metric | full | no dialogue | delta |", "|---|---:|---:|---:|",
        ))
        for metric in BOOLEAN_FIELDS:
            a = full["branch_level"]["binary_metrics"][metric]
            b = no["branch_level"]["binary_metrics"][metric]
            lines.append(
                f"| `{metric}` | {count_rate(a['true'], full['branches'])} | "
                f"{count_rate(b['true'], no['branches'])} | "
                f"{100 * (a['rate'] - b['rate']):+.2f}%p |"
            )
        for title, key, levels in (
            ("Recovery level 분포", "recovery_levels", RECOVERY_LEVELS),
            ("Behavior level 분포", "behavior_levels", BEHAVIOR_LEVELS),
            ("CARES label 분포", "cares_labels", CARES_LABELS),
            ("Goal-atom status 분포", "goal_atom_statuses", ATOM_STATUSES),
            ("Goal-atom 최초 출처", "goal_atom_first_sources", ATOM_SOURCES),
        ):
            lines.extend((
                "", f"### {title}", "",
                "| score | full | no dialogue | delta |", "|---|---:|---:|---:|",
            ))
            for level in levels:
                a = full["branch_level"][key][level]
                b = no["branch_level"][key][level]
                lines.append(
                    f"| `{level}` | {a['count']:,} ({percent(a['rate'])}) | "
                    f"{b['count']:,} ({percent(b['rate'])}) | "
                    f"{100 * (a['rate'] - b['rate']):+.2f}%p |"
                )
        lines.extend(("", "### 연속형·QA 지표", ""))
        lines.append(
            "- ordinal level 평균 `R/B`: "
            f"full {full['branch_level']['ordinal_score_means']['recovery_R0_to_R4']:.4f}/"
            f"{full['branch_level']['ordinal_score_means']['behavior_B0_to_B5']:.4f}, "
            f"no dialogue {no['branch_level']['ordinal_score_means']['recovery_R0_to_R4']:.4f}/"
            f"{no['branch_level']['ordinal_score_means']['behavior_B0_to_B5']:.4f}"
        )
        lines.append(
            "- `persona_evidence_precision` 평균/중앙값: "
            f"full {full['branch_level']['persona_evidence_precision']['mean']:.4f}/"
            f"{full['branch_level']['persona_evidence_precision']['median']:.4f}, "
            f"no dialogue {no['branch_level']['persona_evidence_precision']['mean']:.4f}/"
            f"{no['branch_level']['persona_evidence_precision']['median']:.4f}"
        )
        for arm_label, arm in (("full", full), ("no dialogue", no)):
            qa = arm["branch_level"]["quality"]
            lines.append(
                f"- {arm_label} QA: CARES 누락/오류 {qa['cares_missing_or_error_rows']}, "
                f"quote-warning rows {qa['quote_warning_rows']:,}, warnings {qa['quote_warning_count']:,}, "
                f"rejected evaluator outputs recovery/manifestation "
                f"{qa['rejected_recovery_evaluator_outputs']}/"
                f"{qa['rejected_manifestation_evaluator_outputs']}"
            )
        lines.extend((
            "", "### 방향별 canonical branch rate", "",
            "| direction | arm | recovery | target-originated | unsafe | "
            "CARES Accept | CARES non-refuse |",
            "|---|---|---:|---:|---:|---:|---:|",
        ))
        for direction in FINAL_DIRECTIONS:
            for arm_label, arm in (("full", full), ("no dialogue", no)):
                item = arm["by_direction"][direction]
                binary = item["binary_metrics"]
                cares = item["cares_labels"]
                non_refuse = cares["Accept"]["count"] + cares["Caution"]["count"]
                lines.append(
                    f"| `{direction}` | {arm_label} | "
                    f"{percent(binary['raw_recovery_success']['rate'])} | "
                    f"{percent(binary['target_originated_recovery_success']['rate'])} | "
                    f"{percent(binary['unsafe_manifestation_success']['rate'])} | "
                    f"{percent(cares['Accept']['rate'])} | "
                    f"{100 * non_refuse / item['branches']:.2f}% |"
                )
        lines.append("")
    lines.extend((
        "## JSON 세부 산출물", "",
        "방향별 R0–R4, B0–B5, CARES label, atom provenance를 포함한 모든 원시 count는 동명의",
        "JSON의 `arms.*.by_direction`에 있다. Markdown은 전체 분포와 방향별 canonical rate를",
        "표시하고 JSON은 손실 없는 재현 산출물로 사용한다.",
        "",
        "`qwen_goal_injection`은 기존 evaluator schema의 필드명이다. Qwen target arm에서는 실제",
        "goal-aware planner가 Llama-3.1-8B였으므로 이 이름을 planner-first injection의 legacy",
        "schema label로만 해석한다.",
    ))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", action="append", required=True)
    parser.add_argument("--pair", action="append", required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--selection-key", default="final_case_ids")
    parser.add_argument("--condition", default="neutral")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    try:
        paths = parse_named_paths(args.evaluation)
        pairs = parse_pairs(args.pair)
        ids = official_ids(args.selection_manifest, args.selection_key)
    except ValueError as exc:
        parser.error(str(exc))
    arms = {}
    arm_records = {}
    audit = {}
    for name, directories in paths.items():
        records, skipped = load_arm(directories, ids, args.condition)
        arm_records[name] = records
        arms[name] = summarize_arm(records, args.condition)
        audit[name] = {
            "evaluation_directories": [str(path) for path in directories],
            "skipped_nonofficial": skipped,
        }
    comparisons = {}
    for label, full_name, no_name in pairs:
        if full_name not in arms or no_name not in arms:
            parser.error(f"pair {label!r} refers to an unknown arm")
        comparisons[label] = {
            "full_arm": full_name,
            "no_dialogue_arm": no_name,
            **comparison(
                arms[full_name], arms[no_name],
                arm_records[full_name], arm_records[no_name],
            ),
        }
    report = {
        "definition": "official-500 paired full dialogue vs no research dialogue",
        "condition": args.condition,
        "directions": list(FINAL_DIRECTIONS),
        "selection_manifest": str(args.selection_manifest),
        "selection_key": args.selection_key,
        "arms": arms,
        "comparisons": comparisons,
        "input_audit": audit,
    }
    atomic_json(args.output_json, report)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": "complete", "arms": list(arms),
        "cases_per_arm": {name: value["cases"] for name, value in arms.items()},
        "output_json": str(args.output_json), "output_md": str(args.output_md),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
