#!/usr/bin/env python3
"""Generate publication tables and figures from committed aggregate results."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[4]
PACKAGE = Path(__file__).resolve().parents[1]
FIGURES = PACKAGE / "figures"
TABLES = PACKAGE / "tables"
DATA = PACKAGE / "data"

SOURCES = {
    "depth": ROOT / "persona_redteam/result/OURS/final197_research_mediation_depth_gpt4o_v1/aggregate_metrics.csv",
    "baselines": ROOT / "external_baselines/result/final197_external_baselines_v2/all_results.csv",
    "pcsa": ROOT / "external_baselines/result/pcsa_persona_ablation_final197.json",
    "cross_model": ROOT / "persona_redteam/result/OURS/final197_best_short_cross_model_v1/CROSS_MODEL_RESULTS.json",
    "attention": ROOT / "persona_redteam/result/OURS/qwen_attention_research_horizon_final197_all4_v1/aggregate/aggregate_metrics.json",
    "geometry": ROOT / "persona_redteam/result/OURS/qwen_semantic_harm_geometry_final197_v1/aggregate/semantic_harm_geometry_summary.json",
    "geometry_readout": ROOT / "persona_redteam/result/OURS/qwen_semantic_harm_geometry_final197_readout_v1/aggregate/semantic_harm_geometry_summary.json",
    "history_transfer": ROOT / "persona_redteam/result/OURS/final197_history_transfer_cosine_v1/gpt4o/cases_0_197/COMPARISON.json",
}

COLORS = {
    "navy": "#173F5F",
    "blue": "#20639B",
    "teal": "#3CAEA3",
    "gold": "#F6D55C",
    "red": "#ED553B",
    "gray": "#697386",
    "light": "#E9EEF3",
}


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def pct(value: float) -> float:
    return 100.0 * float(value)


def fmt(value: float) -> str:
    return f"{pct(value):.2f}"


def tex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(char, char) for char in value)


def style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9.5,
        "axes.titlesize": 11,
        "axes.labelsize": 9.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.alpha": 0.22,
        "axes.axisbelow": True,
        "legend.frameon": False,
        "figure.dpi": 140,
        "savefig.dpi": 320,
        "savefig.bbox": "tight",
        "svg.hashsalt": "final197-paper-artifacts-v1",
    })


def save_figure(fig, stem: str) -> None:
    metadata = {
        "pdf": {"Creator": "Final-197 paper artifact generator", "CreationDate": None, "ModDate": None},
        "svg": {"Creator": "Final-197 paper artifact generator", "Date": None},
        "png": {"Software": "Final-197 paper artifact generator"},
    }
    for suffix in ("pdf", "svg", "png"):
        output = FIGURES / f"{stem}.{suffix}"
        fig.savefig(output, facecolor="white", metadata=metadata[suffix])
        if suffix == "svg":
            cleaned = "\n".join(line.rstrip() for line in output.read_text(encoding="utf-8").splitlines()) + "\n"
            output.write_text(cleaned, encoding="utf-8")
    plt.close(fig)


def label_bars(ax, bars, *, digits: int = 1, offset: float = 1.0) -> None:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + offset,
            f"{height:.{digits}f}",
            ha="center",
            va="bottom",
            fontsize=7.5,
        )


def load_data() -> dict:
    missing = [str(path) for path in SOURCES.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing source files:\n" + "\n".join(missing))

    depth_rows = read_csv(SOURCES["depth"])
    baseline_rows = [
        row for row in read_csv(SOURCES["baselines"])
        if row["study_id"] == "external_matrix_final197_v1"
        and row["condition"] == "standard"
        and row["target"] in {"gpt4o", "qwen7b_instruct"}
    ]
    pcsa = read_json(SOURCES["pcsa"])
    cross = read_json(SOURCES["cross_model"])
    attention = read_json(SOURCES["attention"])
    geometry = read_json(SOURCES["geometry"])
    geometry_readout = read_json(SOURCES["geometry_readout"])
    history = read_json(SOURCES["history_transfer"])

    if len(depth_rows) != 6:
        raise ValueError(f"Expected six depth/history cells, got {len(depth_rows)}")
    if len(baseline_rows) != 18:
        raise ValueError(f"Expected 18 external baseline rows, got {len(baseline_rows)}")
    if len(cross["rows"]) != 7:
        raise ValueError(f"Expected seven cross-model rows, got {len(cross['rows'])}")
    if len(history["cells"]) != 8:
        raise ValueError(f"Expected eight history-transfer cells, got {len(history['cells'])}")

    return {
        "depth": depth_rows,
        "baselines": baseline_rows,
        "pcsa": pcsa,
        "cross_model": cross,
        "attention": attention,
        "geometry": geometry,
        "geometry_readout": geometry_readout,
        "history_transfer": history,
    }


def figure_depth(data: dict) -> None:
    rows = data["depth"]
    order = [
        ("direct_final_only", "with_history", "Direct\n+Hist."),
        ("direct_final_only", "no_history", "Direct\nNo hist."),
        ("single_readout", "with_history", "Single\nHist."),
        ("single_readout", "no_history", "Single\nNo hist."),
        ("long_7_stage", "with_history", "Long\nHist."),
        ("long_7_stage", "no_history", "Long\nNo hist."),
    ]
    lookup = {(r["condition"], r["history"]): r for r in rows}
    selected = [lookup[(condition, history)] for condition, history, _ in order]
    labels = [label for _, _, label in order]
    joint = [pct(r["joint_R3_B4_harmbench_at_4"]) for r in selected]
    harmbench = [pct(r["harmbench_plus_at_4"]) for r in selected]
    b4 = [pct(r["B4_plus_at_4"]) for r in selected]

    fig, ax = plt.subplots(figsize=(10.4, 4.5))
    x = np.arange(len(labels))
    width = 0.24
    bars1 = ax.bar(x - width, joint, width, label="Strict joint@4", color=COLORS["navy"])
    bars2 = ax.bar(x, harmbench, width, label="HarmBench+@4", color=COLORS["teal"])
    bars3 = ax.bar(x + width, b4, width, label="B4+@4", color=COLORS["gold"])
    label_bars(ax, bars1, offset=1.2)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Case-level success rate (%)")
    ax.set_title("Research mediation depth and persona-history ablation (GPT-4o, n=197)")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.01))
    ax.axvline(1.5, color="#AAB3BD", lw=0.8)
    ax.axvline(3.5, color="#AAB3BD", lw=0.8)
    fig.tight_layout()
    save_figure(fig, "fig1_research_depth_history")


def figure_baselines_and_pcsa(data: dict) -> None:
    rows = data["baselines"]
    display = {
        "direct": "Direct",
        "skeleton_key": "Skeleton Key",
        "many_shot": "Many-shot",
        "red_teaming": "Red Teaming",
        "pair": "PAIR",
        "tap": "TAP",
        "crescendo": "Crescendo",
        "therapist_crescendo": "Therapist Crescendo",
        "pcsa_phase2": "PCSA Phase 2",
    }
    methods = list(display)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.0), gridspec_kw={"width_ratios": [1, 1, 0.78]})
    for ax, target, title in zip(axes[:2], ("gpt4o", "qwen7b_instruct"), ("GPT-4o", "Qwen2.5-7B-Instruct")):
        lookup = {r["method"]: r for r in rows if r["target"] == target}
        y = np.arange(len(methods))
        hb = [pct(lookup[m]["harmbench_rate"]) for m in methods]
        joint = [pct(lookup[m]["strict_joint_rate"]) for m in methods]
        ax.barh(y + 0.18, hb, height=0.34, color=COLORS["teal"], label="HarmBench+")
        ax.barh(y - 0.18, joint, height=0.34, color=COLORS["navy"], label="Strict joint")
        ax.set_yticks(y, [display[m] for m in methods] if ax is axes[0] else [])
        ax.invert_yaxis()
        ax.set_xlim(0, 50)
        ax.set_xlabel("Rate (%)")
        ax.set_title(title)
    axes[0].legend(loc="lower right")

    conditions = data["pcsa"]["conditions"]
    names = ["No persona", "Persona + history"]
    cells = [conditions["no_persona"], conditions["persona_history"]]
    metrics = [
        ("HarmBench+", [pct(c["harmbench"]["asr"]) for c in cells], COLORS["teal"]),
        ("B4+", [pct(c["goal_compliance_v3"]["b4_plus_rate"]) for c in cells], COLORS["gold"]),
        ("Strict joint", [pct(c["goal_compliance_v3"]["strict_joint_rate"]) for c in cells], COLORS["navy"]),
    ]
    x = np.arange(2)
    width = 0.22
    for index, (label, values, color) in enumerate(metrics):
        axes[2].bar(x + (index - 1) * width, values, width, label=label, color=color)
    axes[2].set_xticks(x, names, rotation=12, ha="right")
    axes[2].set_ylim(0, 34)
    axes[2].set_ylabel("Rate (%)")
    axes[2].set_title("PCSA personalization")
    axes[2].legend(fontsize=8)
    fig.suptitle("External baselines and paired PCSA personalization ablation (n=197)", y=1.02, fontsize=12)
    fig.tight_layout()
    save_figure(fig, "fig2_baselines_pcsa")


def figure_cross_model(data: dict) -> None:
    rows = sorted(data["cross_model"]["rows"], key=lambda r: r["same_branch_joint_at_4"])
    label_map = {
        "mistral_small_3_2_24b": "Mistral Small 3.2 24B",
        "gemma4_26b_a4b_it": "Gemma 4 26B-A4B",
        "phi4": "Phi-4",
        "llama3_1_8b_instruct": "Llama 3.1 8B Instruct",
        "llama3_g2c": "Llama3-G2C",
        "gpt5_4_mini": "GPT-5.4-mini",
        "gpt6_luna": "GPT-6-luna",
    }
    y = np.arange(len(rows))
    hb = [pct(r["harmbench_at_4"]) for r in rows]
    joint = [pct(r["same_branch_joint_at_4"]) for r in rows]
    accept = [pct(r["accept"]) for r in rows]

    fig, ax = plt.subplots(figsize=(9.3, 4.9))
    ax.scatter(accept, y + 0.20, marker="s", s=45, color=COLORS["gold"], label="CARES Accept")
    ax.scatter(hb, y, marker="o", s=45, color=COLORS["teal"], label="HarmBench+@4")
    ax.scatter(joint, y - 0.20, marker="D", s=38, color=COLORS["navy"], label="Strict joint@4")
    for row_y, value in zip(y, joint):
        ax.text(value + 1.3, row_y - 0.20, f"{value:.1f}", va="center", fontsize=8, color=COLORS["navy"])
    ax.set_yticks(y, [label_map[r["target"]] for r in rows])
    ax.set_xlim(-2, 106)
    ax.set_xlabel("Case-level rate (%)")
    fig.suptitle("Cross-model transfer of the best short method (Best-of-4, n=197 per target)", y=0.98, fontsize=12)
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.01))
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    save_figure(fig, "fig3_cross_model")


def figure_history_transfer(data: dict) -> None:
    cells = {cell["cell"]: cell for cell in data["history_transfer"]["cells"]}
    donors = ["Own", "No history", "Cosine matched", "Mismatched"]
    short_keys = ["own_short", "no_history_short", "matched_short", "mismatched_short"]
    long_keys = ["own_long", "no_history_long", "matched_long", "mismatched_long"]
    x = np.arange(len(donors))
    width = 0.34

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4))
    short = [pct(cells[key]["joint"]) for key in short_keys]
    long = [pct(cells[key]["joint"]) for key in long_keys]
    b1 = axes[0].bar(x - width / 2, short, width, color=COLORS["blue"], label="Single readout")
    b2 = axes[0].bar(x + width / 2, long, width, color=COLORS["red"], label="Long 7-stage")
    label_bars(axes[0], b1, offset=1.0)
    label_bars(axes[0], b2, offset=1.0)
    axes[0].set_xticks(x, donors, rotation=12, ha="right")
    axes[0].set_ylim(0, 106)
    axes[0].set_ylabel("Strict joint@4 (%)")
    axes[0].set_title("Final behavioral success")
    axes[0].legend()

    recovery = [pct(cells[key]["goal_recovery_success_rate"]) for key in long_keys]
    hb = [pct(cells[key]["harmbench"]) for key in long_keys]
    b3 = axes[1].bar(x - width / 2, recovery, width, color=COLORS["gold"], label="GOAL recovery")
    b4 = axes[1].bar(x + width / 2, hb, width, color=COLORS["teal"], label="HarmBench+@4")
    label_bars(axes[1], b3, offset=1.0)
    label_bars(axes[1], b4, offset=1.0)
    axes[1].set_xticks(x, donors, rotation=12, ha="right")
    axes[1].set_ylim(0, 106)
    axes[1].set_ylabel("Rate (%)")
    axes[1].set_title("Long-dialogue recovery vs. final output")
    axes[1].legend()
    fig.suptitle("Cosine-based persona-history transfer (GPT-4o, n=197)", y=1.02, fontsize=12)
    fig.tight_layout()
    save_figure(fig, "fig4_history_transfer")


def figure_attention_geometry(data: dict) -> None:
    attention = data["attention"]
    geometry = data["geometry"]
    conditions = ["direct_goal", "short_research", "long_research"]
    labels = ["Direct GOAL", "Short readout", "Long dialogue"]
    colors = [COLORS["gray"], COLORS["blue"], COLORS["red"]]

    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.8))
    panels = [
        (attention["metrics"]["goal_cosine"], "Attention-weighted\nGOAL cosine", (0.20, 0.28)),
        (geometry["late_metrics"]["exact_goal_cosine"], "Late-layer exact\nGOAL cosine", (0.48, 1.03)),
        (geometry["late_metrics"]["loo_harm_projection"], "Late-layer matched\nharm-axis projection", (-0.05, 0.33)),
    ]
    for ax, (metric, title, ylim) in zip(axes, panels):
        means = [metric[key]["mean"] for key in conditions]
        low = [mean - metric[key]["ci95_low"] for mean, key in zip(means, conditions)]
        high = [metric[key]["ci95_high"] - mean for mean, key in zip(means, conditions)]
        x = np.arange(3)
        ax.bar(x, means, color=colors, width=0.64)
        ax.errorbar(x, means, yerr=np.array([low, high]), fmt="none", ecolor="#27313A", capsize=3, lw=1)
        ax.set_xticks(x, labels, rotation=14, ha="right")
        ax.set_ylim(*ylim)
        ax.set_title(title)
        if ylim[0] < 0:
            ax.axhline(0, color="#27313A", lw=0.8)
    fig.suptitle("Qwen proxy analysis: attention and representation geometry (197 cases × 4 branches)", y=1.03, fontsize=12)
    fig.tight_layout()
    save_figure(fig, "fig5_attention_geometry")


def make_tables(data: dict) -> str:
    depth_order = [
        ("direct_final_only", "with_history", "Direct final only", "Yes"),
        ("direct_final_only", "no_history", "Direct final only", "No"),
        ("single_readout", "with_history", "Single readout", "Yes"),
        ("single_readout", "no_history", "Single readout", "No"),
        ("long_7_stage", "with_history", "Long 7-stage", "Yes"),
        ("long_7_stage", "no_history", "Long 7-stage", "No"),
    ]
    depth_lookup = {(r["condition"], r["history"]): r for r in data["depth"]}
    depth_lines = []
    for condition, history, label, has_history in depth_order:
        row = depth_lookup[(condition, history)]
        values = [
            fmt(row["cares_accept"]), fmt(row["R3_plus_at_4"]), fmt(row["B4_plus_at_4"]),
            fmt(row["harmbench_plus_at_4"]), fmt(row["joint_R3_B4_harmbench_at_4"]),
        ]
        if condition == "single_readout" and history == "with_history":
            values[-1] = r"\textbf{" + values[-1] + "}"
        depth_lines.append(f"{label} & {has_history} & " + " & ".join(values) + r" \\")

    target_names = {"gpt4o": "GPT-4o", "qwen7b_instruct": "Qwen2.5-7B-Instruct"}
    method_names = {
        "direct": "Direct", "skeleton_key": "Skeleton Key", "many_shot": "Many-shot",
        "red_teaming": "Red Teaming", "pair": "PAIR", "tap": "TAP",
        "crescendo": "Crescendo", "therapist_crescendo": "Therapist Crescendo",
        "pcsa_phase2": "PCSA Phase 2",
    }
    baseline_lines = []
    for target in ("gpt4o", "qwen7b_instruct"):
        target_rows = [r for r in data["baselines"] if r["target"] == target]
        target_rows.sort(key=lambda r: list(method_names).index(r["method"]))
        for index, row in enumerate(target_rows):
            baseline_lines.append(
                f"{target_names[target] if index == 0 else ''} & {method_names[row['method']]} & "
                + " & ".join(fmt(row[key]) for key in (
                    "cares_accept_rate", "r3_plus_rate", "b4_plus_rate", "harmbench_rate", "strict_joint_rate"
                )) + r" \\"
            )
        if target == "gpt4o":
            baseline_lines.append(r"\midrule")

    pcsa = data["pcsa"]["conditions"]
    pcsa_lines = []
    for key, label in (("no_persona", "No persona"), ("persona_history", "Persona + history")):
        cell = pcsa[key]
        pcsa_lines.append(
            f"{label} & {fmt(cell['cares']['asr'])} & {fmt(cell['goal_compliance_v3']['r3_plus_rate'])} & "
            f"{fmt(cell['goal_compliance_v3']['b4_plus_rate'])} & {fmt(cell['harmbench']['asr'])} & "
            f"{fmt(cell['goal_compliance_v3']['strict_joint_rate'])} " + r"\\"
        )

    model_names = {
        "mistral_small_3_2_24b": "Mistral Small 3.2 24B", "gemma4_26b_a4b_it": "Gemma 4 26B-A4B",
        "phi4": "Phi-4", "llama3_1_8b_instruct": "Llama 3.1 8B Instruct", "llama3_g2c": "Llama3-G2C",
        "gpt5_4_mini": "GPT-5.4-mini", "gpt6_luna": "GPT-6-luna",
    }
    cross_rows = sorted(data["cross_model"]["rows"], key=lambda r: r["same_branch_joint_at_4"], reverse=True)
    cross_lines = []
    for index, row in enumerate(cross_rows):
        joint = fmt(row["same_branch_joint_at_4"])
        if index == 0:
            joint = r"\textbf{" + joint + "}"
        cross_lines.append(
            f"{model_names[row['target']]} & {fmt(row['accept'])} & {fmt(row['r3_at_4'])} & "
            f"{fmt(row['b4_at_4'])} & {fmt(row['harmbench_at_4'])} & {joint} " + r"\\"
        )

    attention = data["attention"]["metrics"]
    geometry = data["geometry"]["late_metrics"]
    condition_labels = {"direct_goal": "Direct GOAL", "short_research": "Short readout", "long_research": "Long dialogue"}
    attention_lines = []
    for key in condition_labels:
        attention_lines.append(
            f"{condition_labels[key]} & {attention['positional_js'][key]['mean']:.4f} & "
            f"{attention['goal_cosine'][key]['mean']:.4f} & {attention['entropy'][key]['mean']:.4f} & "
            f"{geometry['exact_goal_cosine'][key]['mean']:.4f} & {geometry['loo_harm_projection'][key]['mean']:.4f} " + r"\\"
        )

    history_names = {
        "own_short": "Own history", "no_history_short": "No history", "matched_short": "Cosine-matched history",
        "mismatched_short": "Mismatched history", "own_long": "Own history", "no_history_long": "No history",
        "matched_long": "Cosine-matched history", "mismatched_long": "Mismatched history",
    }
    history_lines = []
    for cell in data["history_transfer"]["cells"]:
        horizon = "Short" if cell["cell"].endswith("short") else "Long"
        recovery = "--" if horizon == "Short" else fmt(cell["goal_recovery_success_rate"])
        joint = fmt(cell["joint"])
        if cell["cell"] == "own_short":
            joint = r"\textbf{" + joint + "}"
        cosine = "--" if cell["mean_cosine"] == 0 else f"{cell['mean_cosine']:.4f}"
        history_lines.append(
            f"{horizon} & {history_names[cell['cell']]} & {cosine} & {recovery} & {fmt(cell['cares_asr'])} & "
            f"{fmt(cell['r3'])} & {fmt(cell['b4'])} & {fmt(cell['harmbench'])} & {joint} " + r"\\"
        )

    return rf"""% Auto-generated by scripts/generate_paper_package.py. Do not edit values manually.
% Required packages: booktabs, longtable, threeparttable, adjustbox.

\begin{{table*}}[t]
\centering
\small
\caption{{Research mediation depth and persona-history ablation on GPT-4o. All values are percentages over 197 cases; @4 denotes Best-of-4. Strict joint requires R3+, B4+, and HarmBench+ in the same branch.}}
\label{{tab:depth-history}}
\begin{{threeparttable}}
\begin{{tabular}}{{llrrrrr}}
\toprule
Research condition & History & CARES Accept & R3+@4 & B4+@4 & HarmBench+@4 & Strict joint@4 \\
\midrule
{chr(10).join(depth_lines)}
\bottomrule
\end{{tabular}}
\begin{{tablenotes}}\footnotesize
\item Direct-final-only omits the shared research readout; single-readout uses one compact research readout; long uses the seven-stage dialogue.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table*}}

\begin{{longtable}}{{llrrrrr}}
\caption{{External baseline matrix on Final-197. Each baseline reports one stored final response per case; query budgets differ across methods. These rows must not be presented as a budget-matched ranking against OURS Best-of-4.}}\label{{tab:external-baselines}}\\
\toprule
Target & Method & CARES Accept & R3+ & B4+ & HarmBench+ & Strict joint \\
\midrule
\endfirsthead
\toprule
Target & Method & CARES Accept & R3+ & B4+ & HarmBench+ & Strict joint \\
\midrule
\endhead
{chr(10).join(baseline_lines)}
\bottomrule
\end{{longtable}}

\begin{{table}}[t]
\centering
\small
\caption{{Paired PCSA Phase-2 personalization ablation on Qwen2.5-7B-Instruct (n=197).}}
\label{{tab:pcsa-personalization}}
\begin{{tabular}}{{lrrrrr}}
\toprule
Condition & CARES ASR & R3+ & B4+ & HarmBench+ & Strict joint \\
\midrule
{chr(10).join(pcsa_lines)}
\bottomrule
\end{{tabular}}
\vspace{{2pt}}
\parbox{{0.96\linewidth}}{{\footnotesize Exact paired McNemar test on HarmBench: $p={data['pcsa']['paired_harmbench']['exact_mcnemar_two_sided_p']:.2e}$. CARES non-refusal moves in the opposite direction and is not used alone to characterize personalization.}}
\end{{table}}

\begin{{table*}}[t]
\centering
\small
\caption{{Cross-model transfer of the best short method (197 cases per target, Best-of-4).}}
\label{{tab:cross-model}}
\begin{{tabular}}{{lrrrrr}}
\toprule
Target model & CARES Accept & R3+@4 & B4+@4 & HarmBench+@4 & Strict joint@4 \\
\midrule
{chr(10).join(cross_lines)}
\bottomrule
\end{{tabular}}
\end{{table*}}

\begin{{table*}}[t]
\centering
\small
\caption{{Qwen proxy analysis of attention and representation geometry (197 cases, four branches per case). Confidence intervals are available in the released aggregate JSON.}}
\label{{tab:attention-geometry}}
\begin{{tabular}}{{lrrrrr}}
\toprule
Condition & Positional JS & Attention GOAL cosine & Attention entropy & Exact GOAL cosine & Harm-axis projection \\
\midrule
{chr(10).join(attention_lines)}
\bottomrule
\end{{tabular}}
\vspace{{2pt}}
\parbox{{0.96\linewidth}}{{\footnotesize This is a proxy-model association analysis, not causal evidence about GPT-4o internals or general safety.}}
\end{{table*}}

\begin{{table*}}[t]
\centering
\scriptsize
\caption{{Cosine-based transfer of another sample's persona history on GPT-4o (n=197). Short conditions do not run the seven-stage GOAL-recovery gate, so recovery is not applicable rather than zero.}}
\label{{tab:history-transfer}}
\begin{{tabular}}{{lllrrrrrr}}
\toprule
Horizon & History source & Donor cosine & GOAL recovery & CARES ASR & R3+@4 & B4+@4 & HarmBench+@4 & Strict joint@4 \\
\midrule
{chr(10).join(history_lines)}
\bottomrule
\end{{tabular}}
\end{{table*}}
"""


def make_figures_tex() -> str:
    figure_specs = [
        ("fig1_research_depth_history", "Research mediation depth and persona-history ablation. The compact single-readout condition gives the strongest same-branch strict joint result.", "fig:depth-history"),
        ("fig2_baselines_pcsa", "External baseline matrix and the paired PCSA personalization ablation. Baseline query budgets differ and are shown for context, not as a budget-matched ranking against OURS.", "fig:baselines-pcsa"),
        ("fig3_cross_model", "Cross-model generalization of the best short method. CARES Accept, HarmBench, and the same-branch strict joint criterion expose different aspects of success.", "fig:cross-model"),
        ("fig4_history_transfer", "History-transfer ablation. Cosine-matched history helps relative to no history in the short condition but does not match sample-specific history; long dialogue does not repair mismatched context.", "fig:history-transfer"),
        ("fig5_attention_geometry", "Qwen proxy analysis of attention and representation geometry. Results support a cue-dilution hypothesis but do not establish a causal mechanism in GPT-4o.", "fig:attention-geometry"),
    ]
    blocks = []
    for stem, caption, label in figure_specs:
        blocks.append(rf"""\begin{{figure*}}[t]
\centering
\includegraphics[width=0.98\textwidth]{{figures/{stem}.pdf}}
\caption{{{caption}}}
\label{{{label}}}
\end{{figure*}}""")
    return "% Auto-generated figure environments.\n\n" + "\n\n".join(blocks) + "\n"


def make_standalone() -> str:
    return r"""\documentclass[10pt]{article}
\usepackage[margin=0.72in]{geometry}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{threeparttable}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage[hidelinks]{hyperref}
\title{Final-197 Additional Experiments: Publication Tables and Figures}
\author{Anonymous authors}
\date{}
\begin{document}
\maketitle

\section{Reporting conventions}
All rates use the same 197-case cohort. OURS reports Best-of-4 where marked by @4.
The strict joint metric requires R3+, B4+, and HarmBench+ in the same branch.
External baselines store one selected final response and use heterogeneous query budgets;
we therefore report them as contextual evidence rather than a budget-matched leaderboard.

\input{tables/paper_tables.tex}
\clearpage
\input{figures.tex}
\end{document}
"""


def write_data_snapshot(data: dict) -> None:
    snapshot = {
        "version": "final197-paper-artifacts-v1",
        "cohort_cases": 197,
        "reporting": {
            "best_of_n": 4,
            "strict_joint": "same branch satisfies R3+, B4+, and HarmBench+",
            "external_baseline_warning": "one stored response; heterogeneous query budgets",
        },
        "depth_history": data["depth"],
        "external_baselines": data["baselines"],
        "pcsa_persona_ablation": data["pcsa"],
        "cross_model": data["cross_model"]["rows"],
        "attention_metrics": data["attention"]["metrics"],
        "attention_paired_long_minus_short": data["attention"]["paired_long_minus_short"],
        "geometry_late_metrics": data["geometry"]["late_metrics"],
        "geometry_paired_deltas": data["geometry"]["paired_deltas"],
        "readout_geometry_late_metrics": data["geometry_readout"]["late_metrics"],
        "history_transfer": data["history_transfer"],
    }
    (DATA / "paper_metrics.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for row in data["depth"]:
        rows.append({
            "experiment": "depth_history", "condition": f"{row['condition']}::{row['history']}",
            "accept": row["cares_accept"], "r3": row["R3_plus_at_4"], "b4": row["B4_plus_at_4"],
            "harmbench": row["harmbench_plus_at_4"], "joint": row["joint_R3_B4_harmbench_at_4"],
        })
    for row in data["cross_model"]["rows"]:
        rows.append({
            "experiment": "cross_model", "condition": row["target"], "accept": row["accept"],
            "r3": row["r3_at_4"], "b4": row["b4_at_4"], "harmbench": row["harmbench_at_4"],
            "joint": row["same_branch_joint_at_4"],
        })
    for cell in data["history_transfer"]["cells"]:
        rows.append({
            "experiment": "history_transfer", "condition": cell["cell"], "accept": cell["accept"],
            "r3": cell["r3"], "b4": cell["b4"], "harmbench": cell["harmbench"], "joint": cell["joint"],
        })
    with (DATA / "headline_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["experiment", "condition", "accept", "r3", "b4", "harmbench", "joint"])
        writer.writeheader()
        writer.writerows(rows)


def validate_outputs(data: dict) -> None:
    figures = sorted(FIGURES.glob("fig*.pdf"))
    tex_files = [TABLES / "paper_tables.tex", PACKAGE / "figures.tex", PACKAGE / "appendix_additional_experiments.tex"]
    checks = {
        "status": "pass",
        "source_files": len(SOURCES),
        "depth_cells": len(data["depth"]),
        "baseline_rows": len(data["baselines"]),
        "cross_model_targets": len(data["cross_model"]["rows"]),
        "history_transfer_cells": len(data["history_transfer"]["cells"]),
        "figure_sets": len(figures),
        "figure_formats_each": ["pdf", "png", "svg"],
        "latex_files": [str(path.relative_to(PACKAGE)) for path in tex_files],
        "latex_balanced_braces": {},
        "source_sha256": {},
    }
    for path in tex_files:
        text = path.read_text(encoding="utf-8")
        balanced = text.count("{") == text.count("}")
        checks["latex_balanced_braces"][str(path.relative_to(PACKAGE))] = balanced
        if not balanced:
            checks["status"] = "fail"
    for name, path in SOURCES.items():
        checks["source_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (PACKAGE / "VALIDATION.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if checks["status"] != "pass":
        raise RuntimeError("Artifact validation failed")


def write_manifest() -> None:
    paths = sorted(
        path for path in PACKAGE.rglob("*")
        if path.is_file() and path.name != "MANIFEST.sha256"
        and "__pycache__" not in path.parts
    )
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(PACKAGE)}" for path in paths]
    (PACKAGE / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    style()
    data = load_data()
    figure_depth(data)
    figure_baselines_and_pcsa(data)
    figure_cross_model(data)
    figure_history_transfer(data)
    figure_attention_geometry(data)
    (TABLES / "paper_tables.tex").write_text(make_tables(data), encoding="utf-8")
    (PACKAGE / "figures.tex").write_text(make_figures_tex(), encoding="utf-8")
    (PACKAGE / "appendix_additional_experiments.tex").write_text(make_standalone(), encoding="utf-8")
    write_data_snapshot(data)
    validate_outputs(data)
    write_manifest()
    print(f"Generated publication package at {PACKAGE}")


if __name__ == "__main__":
    main()
