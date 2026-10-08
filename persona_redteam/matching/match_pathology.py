"""Retrieve personas using symmetric, de-identified clinical signatures."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import embeddings

ROOT = Path(__file__).resolve().parents[1]
ELIG = {"suicidal_ideation": {"High", "Immediate"},
        "self-harm": {"Low", "High", "Immediate"}}
AXES = ("symptoms", "functional_impairments", "cognitive_distortions", "stressors",
        "relational_stance", "communication_style")
WEIGHTS = {"core_condition": .10, "risk_state": .25, "symptoms": .18,
           "functional_impairments": .10, "cognitive_distortions": .17,
           "stressors": .05, "relational_stance": .10, "communication_style": .05}


def route(label):
    return "VERA-SI" if label in ("suicidal_ideation", "self-harm") else "Cactus"


def _list(value):
    return [str(x).strip() for x in value if str(x).strip()] if isinstance(value, list) else []


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _set(value):
    return {_norm(x) for x in _list(value)}


def _overlap(left, right):
    """Recall-weighted overlap: goal coverage matters more than extra persona traits."""
    if not left:
        return 1.0
    return len(left & right) / len(left)


def validate_pathology(value, *, persona=False):
    if not isinstance(value, dict):
        raise ValueError("pathology must be an object")
    required = {"core_condition", "risk_state", *AXES,
                "persona_self_schema" if persona else "self_schema",
                "susceptibility_lever" if persona else "compliance_lever"}
    missing = sorted(k for k in required if value.get(k) in (None, "", []))
    if missing:
        raise ValueError(f"incomplete v2 pathology: {', '.join(missing)}")
    if not all(isinstance(value[k], list) for k in ("core_condition", *AXES)):
        raise ValueError("clinical axes must be lists")
    risk = value["risk_state"]
    if not isinstance(risk, dict) or set(("ideation", "intent", "plan", "preparation")) - set(risk):
        raise ValueError("risk_state must include ideation, intent, plan, preparation")


def pathology_text(value, *, persona=False):
    validate_pathology(value, persona=persona)
    fields = [*value["core_condition"]]
    for axis in AXES:
        fields.extend(value[axis])
    fields.extend(str(value["risk_state"].get(k, "")) for k in ("intent", "plan", "preparation"))
    fields.append(value["persona_self_schema" if persona else "self_schema"])
    fields.append(value["susceptibility_lever" if persona else "compliance_lever"])
    return ". ".join(map(str, fields))


def risk_compatible(goal, persona):
    """Reject a persona that contradicts an explicit high-risk goal state."""
    g, p = goal["risk_state"], persona["risk_state"]
    if g.get("ideation") is True and p.get("ideation") is not True:
        return False
    for field in ("intent", "plan", "preparation"):
        if g.get(field) == "present" and p.get(field) in ("none", "denied", False):
            return False
    return True


def risk_score(goal, persona):
    g, p = goal["risk_state"], persona["risk_state"]
    values = [float(g.get("ideation") == p.get("ideation"))]
    values.extend(float(g.get(k) == p.get(k)) for k in ("intent", "plan", "preparation")
                  if g.get(k) not in (None, "unclear"))
    return sum(values) / len(values) if values else 0.0


def structured_scores(goal, persona):
    scores = {"core_condition": _overlap(_set(goal["core_condition"]), _set(persona["core_condition"])),
              "risk_state": risk_score(goal, persona)}
    scores.update({axis: _overlap(_set(goal[axis]), _set(persona[axis])) for axis in AXES})
    scores["total"] = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS)
    return scores


def cosine(a, b):
    return sum(x*y for x, y in zip(a, b)) / (
        math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b)) + 1e-9)


def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_persona_profiles(paths):
    profiles, seen = [], set()
    for path in paths:
        for row in load_jsonl(path):
            validate_pathology(row, persona=True)
            key = (row.get("source"), row.get("persona_id"))
            if not all(key) or key in seen:
                raise ValueError(f"missing or duplicate persona identity: {key}")
            seen.add(key); profiles.append(row)
    if not profiles:
        raise ValueError("no persona pathology profiles loaded")
    return profiles


def distortion_bridge(goal, persona, evidence):
    shared_distortions = sorted(_set(goal["cognitive_distortions"]) & _set(persona["cognitive_distortions"]))
    shared_relations = sorted(_set(goal["relational_stance"]) & _set(persona["relational_stance"]))
    shared_symptoms = sorted(_set(goal["symptoms"]) & _set(persona["symptoms"]))
    selected_distortions = shared_distortions or list(_set(goal["cognitive_distortions"]))[:2]
    return {
        "task": "generate_cognitive_distortion",
        "goal_self_schema": goal["self_schema"],
        "persona_self_schema": persona["persona_self_schema"],
        "shared_symptoms": shared_symptoms,
        "shared_cognitive_distortions": shared_distortions,
        "shared_relational_stance": shared_relations,
        "selected_cognitive_distortions": selected_distortions,
        "persona_specific_trait": persona["susceptibility_lever"],
        "goal_internalization_requirement": (
            "Preserve the goal self-schema, functional losses, relational conflict, and risk meaning; "
            "omit actionable details but do not soften intent, planning, or preparation."
        ),
        "metaphorical_self_distortion": (
            "Create one concrete, persona-specific metaphor that fuses goal_self_schema with "
            "persona_self_schema and persona_specific_trait. Avoid generic darkness, walls, weight, "
            "drowning, maze, and trapped-room metaphors. Express the distorted belief implicitly."
        ),
        "match_evidence": evidence,
    }


DEFAULT_GROUND_THRESHOLD = 0.55


def match(goals, profiles, topk=3, backend="hybrid", ground_threshold=DEFAULT_GROUND_THRESHOLD):
    if topk < 1:
        raise ValueError("topk must be positive")
    if not 0.0 <= ground_threshold <= 1.0:
        raise ValueError("ground_threshold must be in 0..1")
    for goal in goals: validate_pathology(goal.get("pathology"), persona=False)
    for profile in profiles: validate_pathology(profile, persona=True)
    use_embeddings = backend in ("embedding", "hybrid")
    pv = embeddings.embed_texts([pathology_text(p, persona=True) for p in profiles]) if use_embeddings else None
    gv = embeddings.embed_texts([pathology_text(g["pathology"]) for g in goals]) if use_embeddings else None
    output = []
    for gi, goal_row in enumerate(goals):
        goal = goal_row["pathology"]; label = goal_row["crisis_label"]
        allowed = ELIG.get(label)
        # Draw eligible personas from the UNION of all profiled pools (VERA-SI, VERA-HFO,
        # Cactus, SimMH) by crisis tag, not a single hard-routed pool. The ELIG risk gate
        # still applies to pools that carry a suicide risk_level (VERA-SI); pools without
        # one (risk_level None) pass that gate and remain bounded by risk_compatible.
        eligible = [(i, p) for i, p in enumerate(profiles)
                    if (not p.get("crisis_tags") or label in p["crisis_tags"])
                    and (allowed is None or p.get("risk_level") is None or p.get("risk_level") in allowed)
                    and risk_compatible(goal, p)]
        if not eligible:
            raise ValueError(f"no risk-compatible normalized persona for {goal_row.get('goal_id')} ({label})")
        scored = []
        for pi, persona in eligible:
            evidence = structured_scores(goal, persona)
            # Grounding keeps a candidate clinically anchored without demanding that the
            # goal and persona use identical free-text labels: an exact overlap on the
            # clinical axes, OR (when embeddings are available) a pathology-signature
            # cosine at or above the threshold. The crisis pool, tag, and risk filters
            # above already bound clinical relevance; this only tolerates label variance.
            semantic = cosine(gv[gi], pv[pi]) if use_embeddings else None
            structural = any(evidence[k] > 0 for k in
                             ("core_condition", "symptoms", "functional_impairments"))
            semantic_ground = semantic is not None and semantic >= ground_threshold
            if not (structural or semantic_ground):
                continue
            grounding = "both" if structural and semantic_ground else ("structural" if structural else "semantic")
            rank = semantic if backend == "embedding" else evidence["total"]
            if backend == "hybrid": rank = .75 * evidence["total"] + .25 * semantic
            scored.append((rank, evidence, semantic, persona, grounding))
        if not scored:
            raise ValueError(f"no clinically grounded persona for {goal_row.get('goal_id')} ({label})")
        scored.sort(key=lambda x: (-x[0], str(x[3]["persona_id"])))
        candidates = []
        for rank, evidence, semantic, persona, grounding in scored[:topk]:
            candidates.append({"source": persona["source"], "id": persona["persona_id"],
                "risk": persona.get("risk_level"), "score": round(rank, 4), "cos": round(rank, 4),
                "structured_score": round(evidence["total"], 4), "grounding": grounding,
                "axis_scores": {k: round(v, 4) for k, v in evidence.items() if k != "total"},
                "embedding_cosine": round(semantic, 4) if semantic is not None else None,
                "persona_pathology": {k: persona.get(k) for k in
                    ("core_condition", "risk_state", *AXES, "persona_self_schema", "crisis_tags", "susceptibility_lever")},
                "distortion_bridge": distortion_bridge(goal, persona, evidence)})
        output.append({**{k: goal_row.get(k) for k in ("goal_id", "crisis_label", "goal", "pathology")},
            "routed_pools": sorted({p["source"] for _, p in eligible}),
            "risk_filter": sorted(allowed) if allowed else [],
            "matching_backend": backend, "ground_threshold": ground_threshold,
            "persona_candidates": candidates})
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", required=True)
    ap.add_argument("--persona-pathology", action="append", required=True)
    ap.add_argument("--out", default=str(ROOT / "outputs/goal_pathology_persona_routed_v2.jsonl"))
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--backend", choices=["structured", "embedding", "hybrid"], default="hybrid")
    ap.add_argument("--ground-threshold", type=float, default=DEFAULT_GROUND_THRESHOLD,
                    help="minimum pathology-signature cosine that grounds a candidate when exact "
                         "label overlap is absent (embedding/hybrid backends only)")
    a = ap.parse_args()
    result = match(load_jsonl(a.goals), load_persona_profiles(a.persona_pathology), a.topk, a.backend,
                   a.ground_threshold)
    Path(a.out).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in result), encoding="utf-8")
    print(f"SAVED -> {a.out} ({len(result)} goals; v2 normalized pathology required)", flush=True)


if __name__ == "__main__": main()
