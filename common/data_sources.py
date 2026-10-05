"""Dataset loaders with a clean separation of concerns, mirroring PCSA.

PCSA draws *persona construction* material (client characteristics, cognitive
distortions, dialogue style) from counseling corpora (Cactus, CBT-Bench/CBT-DP,
Cheeseburger Therapy), and draws *attack goals* from a separate mental-health
safety-probe set that CARES/the judge evaluates responses against. Our
profile-aware agent adds a third, agent-specific source: a benign *calibration
probe* set used only to measure the target's behavioral profile.

Sources handled here:
- ``personas``          : corpus-derived personas (``data/processed/personas.jsonl``,
                          built by ``build_personas_from_corpus.py`` when the raw
                          private corpora are present) OR the committed approved
                          fallback (``data/personas_fallback.jsonl``).
- ``attack_goals``      : committed synthetic, approved, intent-level goals
                          (``data/attack_goals.jsonl``) — separate from personas.
- ``calibration_probes``: benign profiling probes (``data/calibration_probes.jsonl``).

Persona and goal are *attacker-side conditions*: they shape client-utterance
generation and are never sent to the target as separate fields. The target only
ever receives the generated client turns and the accumulating dialogue history.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def load_personas(processed: Path | None = None, fallback: Path | None = None) -> tuple[list[dict], str]:
    """Return (personas, source_tag). Prefer corpus-derived personas, else fallback."""
    processed = processed or (DATA_DIR / "processed" / "personas.jsonl")
    fallback = fallback or (DATA_DIR / "personas_fallback.jsonl")
    if processed.exists():
        rows = load_jsonl(processed)
        if rows:
            return rows, "corpus_derived"
    rows = load_jsonl(fallback)
    if not rows:
        raise ValueError(f"no personas found in {processed} or {fallback}")
    return rows, "synthetic_fallback"


def load_attack_goals(path: Path | None = None) -> list[dict]:
    return load_jsonl(path or (DATA_DIR / "attack_goals.jsonl"))


def load_susceptibility_probes(path: Path | None = None) -> list[dict]:
    """Fixed, approved probe battery (axis x strategy x register) for the pre-test."""
    path = path or (DATA_DIR / "susceptibility_probes.jsonl")
    return load_jsonl(path) if path.exists() else []


def load_client_exemplars(axis: str, n: int = 10, seed: int = 0) -> list[str]:
    """Sample n client-message demos for the axis, to show the APE generator (ICL).

    Preference order:
      1. ``data/icl_demos.jsonl`` — a small CURATED few-shot ICL set, hand-authored to
         demonstrate effective attack openers per axis/strategy for our counseling
         red-teaming situation (what the APE forward step induces from).
      2. ``data/processed/client_utterances.jsonl`` — corpus-derived (Cactus/CBT-DP).
      3. ``data/client_exemplars.jsonl`` — committed approved fallback bank.
    """
    icl = DATA_DIR / "icl_demos.jsonl"
    processed = DATA_DIR / "processed" / "client_utterances.jsonl"
    path = icl if icl.exists() else (processed if processed.exists() else (DATA_DIR / "client_exemplars.jsonl"))
    rows = load_jsonl(path) if path.exists() else []
    axis_pool = [r["text"] for r in rows if r.get("axis") == axis and r.get("text")]
    other_pool = [r["text"] for r in rows if r.get("axis") != axis and r.get("text")]
    if not axis_pool and not other_pool:
        return []
    rng = random.Random(f"{seed}|{axis}|demos")
    rng.shuffle(axis_pool)
    rng.shuffle(other_pool)
    demos = (axis_pool + other_pool)[:n]  # axis-relevant first, then fill with others up to n
    if not demos:
        return []
    while len(demos) < n:  # small bank: pad with replacement only if still short
        demos.append(rng.choice(axis_pool or other_pool))
    return demos


def load_jargon(path: Path | None = None) -> list[str]:
    """Psychiatric/medical term seeds for the Phase I complexity perturbation."""
    path = path or (DATA_DIR / "psych_jargon.jsonl")
    if not path.exists():
        return []
    return [r["term"] for r in load_jsonl(path) if r.get("term")]


def load_calibration_probes(path: Path | None = None) -> list[dict]:
    path = path or (DATA_DIR / "calibration_probes.jsonl")
    if path.exists():
        return load_jsonl(path)
    from agents import CALIBRATION_PROBES  # stdlib default if the file is absent
    return list(CALIBRATION_PROBES)


def _cos(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _match_persona_order(goal, personas, used_counts):
    """Rank personas by semantic fit to the goal (PCSA target->persona matching):
    cosine similarity of (goal intent+masked_request+target_type) vs
    (persona descriptor+cognitive_distortion), minus a reuse penalty for diversity.
    Returns persona indices best-first. Embeddings are cached on the persona list."""
    import embeddings
    gtext = f"{goal.get('target_type','')}. {goal.get('intent','')} {goal.get('masked_request','')}"
    if not personas[0].get("_vec"):
        ptexts = [f"{p.get('descriptor','')}. {p.get('cognitive_distortion','')}" for p in personas]
        for p, v in zip(personas, embeddings.embed_texts(ptexts)):
            p["_vec"] = v
    gv = embeddings.embed_texts([gtext])[0]
    scored = [(_cos(gv, p["_vec"]) - 0.05 * used_counts[i], i) for i, p in enumerate(personas)]
    scored.sort(reverse=True)
    return [i for _, i in scored]


def build_cases(axis: str, personas: list[dict], goals: list[dict], k: int, seed: int,
                persona_match: bool = False) -> list[dict]:
    """Pair axis-specific goals with personas to form k cases.

    persona_match=False (default): deterministic pseudo-random persona per goal.
    persona_match=True: match the best-fitting *distress-oriented* persona to each
    goal by embedding similarity (PCSA 'intent-to-distortion' target->persona
    alignment), with a reuse penalty for persona diversity. Falls back to random if
    embeddings are unavailable."""
    if k < 1 or not personas:
        raise ValueError("cases per axis must be positive and personas must not be empty")
    axis_goals = [g for g in goals if g.get("axis") == axis]
    if not axis_goals:
        raise ValueError(f"no attack goals for axis {axis}")
    rng = random.Random(f"{seed}|{axis}")
    used_counts = [0] * len(personas)
    cases = []
    for i in range(k):
        goal = axis_goals[i % len(axis_goals)]
        persona = None
        if persona_match:
            try:
                for idx in _match_persona_order(goal, personas, used_counts):
                    persona = personas[idx]
                    used_counts[idx] += 1
                    break
            except (Exception, SystemExit) as exc:  # embeddings unavailable (e.g. no API key) -> fallback
                print(f"[build_cases] persona_match fallback ({exc})", flush=True)
                persona = None
        if persona is None:
            persona = personas[rng.randrange(len(personas))]
        persona = {kk: vv for kk, vv in persona.items() if kk != "_vec"}
        cases.append({"case_id": f"{axis}-{i:03d}", "axis": axis, "persona": persona, "goal": goal})
    return cases
