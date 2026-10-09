"""Runtime persona retrieval over normalized JSONL profiles."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL_PERSONA_POOL = Path(os.environ.get(
    "PERSONA_POOL_PATH", ROOT / "data/source/personas/personas.jsonl"
))

FIELDS = (
    "core_condition", "symptoms", "functional_impairments", "cognitive_distortions",
    "stressors", "relational_stance", "communication_style", "crisis_tags",
)


def load_profiles(path):
    profiles = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        profile = json.loads(line)
        # Full 31k pool uses the public Persona schema; retain every source field while
        # exposing the normalized aliases used by the current matcher.
        profile.setdefault("persona_id", profile.get("id"))
        profile.setdefault("cognitive_distortions", profile.get("cognitive_patterns", []))
        profile.setdefault("source", profile.get("provenance", "unknown"))
        profiles.append(profile)
    return profiles


def _values(value):
    if value is None:
        return set()
    if not isinstance(value, list):
        value = [value]
    return {str(item).strip().casefold() for item in value if str(item).strip()}


def profile_score(goal_pathology, profile, crisis_label=None):
    """Return an auditable weighted overlap score without model calls."""
    weights = {"cognitive_distortions": 3, "relational_stance": 2,
               "communication_style": 2, "symptoms": 2}
    evidence = {}
    numerator = denominator = 0.0
    for field in FIELDS:
        goal = _values(goal_pathology.get(field))
        persona = _values(profile.get(field))
        weight = weights.get(field, 1)
        overlap = sorted(goal & persona)
        union = goal | persona
        value = len(overlap) / len(union) if union else 0.0
        evidence[field] = {"overlap": overlap, "score": value}
        numerator += weight * value
        denominator += weight
    crisis_match = str(crisis_label).casefold() in _values(profile.get("crisis_tags"))
    score = (numerator / denominator if denominator else 0.0) + (0.25 if crisis_match else 0.0)
    return score, {"field_evidence": evidence, "crisis_match": crisis_match}


def _tokens(value):
    return set(re.findall(r"[0-9a-z가-힣]+", str(value).casefold()))


def _profile_text(profile):
    return " ".join([
        str(profile.get("background", "")),
        " ".join(map(str, profile.get("concerns", []))),
        " ".join(map(str, profile.get("style_examples", []))),
        str(profile.get("persona_self_schema", "")),
    ])


def retrieve(goal_pathology, profiles, crisis_label=None, top_k=5, query_text=""):
    query_tokens = _tokens(query_text)
    ranked = []
    for profile in profiles:
        score, evidence = profile_score(goal_pathology, profile, crisis_label)
        profile_tokens = _tokens(_profile_text(profile))
        lexical = (len(query_tokens & profile_tokens) / len(query_tokens)
                   if query_tokens else 0.0)
        # Exact pathology overlap remains useful, while full-pool retrieval gains a
        # sample-specific semantic-text candidate stage instead of collapsing to ties.
        score += 1.5 * lexical
        evidence["goal_text_coverage"] = lexical
        ranked.append({"profile": profile, "score": round(score, 8), "evidence": evidence})
    ranked.sort(key=lambda row: (-row["score"], str(row["profile"].get("source")),
                                 str(row["profile"].get("persona_id"))))
    return ranked[:top_k]
