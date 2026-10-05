"""Source-fused candidate prompt pool for Phase-2 best-arm selection.

Combines two prior works:
  * PCSA (Xu et al.) — the 4 counseling interaction STRATEGIES
    (reassurance_seeking, appeal_to_expertise, intellectualization,
    metaphorical_expression) organize the pool; each strategy is one BAI arm.
  * APE (Zhou et al., "LLMs Are Human-Level Prompt Engineers") — the pool is
    *generated* by forward instruction generation: show the LLM example client
    utterances (demos/exemplars) and have it propose k diverse candidate openers
    that realize a strategy toward the goal; high-scoring candidates can be
    expanded by Monte-Carlo resampling (expand_pool).

No register dimension: candidates are tagged by (strategy) only.
Each candidate: {text, strategy, source}. Selection over the pool is in triple.py.
"""
from __future__ import annotations

from agents import invoke


def harvest_exemplars(susceptibility_matrix, probes, axis, min_wobble=6):
    """Collect probe texts that wobbled the target, grouped by strategy (APE demos)."""
    text_of = {p["probe_id"]: p["text"] for p in probes}
    out = {}
    for row in susceptibility_matrix.get(axis, []):
        if row["score"] >= min_wobble and row.get("probe_id") in text_of:
            out.setdefault(row["strategy"], []).append(text_of[row["probe_id"]])
    return out


def _susceptibility_hint(hint, strategy):
    """Context about the target's measured weakness for this strategy (on-target)."""
    if not hint:
        return {}
    return {"recommended_strategy": hint.get("recommended_strategy", ""),
            "rationale": hint.get("rationale", "")}


def build_pool(case, hint, gen_cmd, strategies, base_k=3, exemplars=None,
               weight_by_wobble=True, fused=True, demos=None):
    """Generate the candidate pool for one case, tagged by strategy (PCSA x APE).

    For each of the PCSA strategies, APE forward-generates base_k diverse candidate
    opening client utterances toward the goal (shown real client-utterance demos
    for natural style). fused=True also injects the target's on-target
    susceptibility report + harvested exemplars and gives weak strategies more
    candidates (profile-guided k). fused=False = goal-only APE baseline (equal k).
    Returns a list of {text, strategy, source}.
    """
    exemplars = exemplars or {}
    goal = {"intent": case["goal"].get("intent", ""), "masked_request": case["goal"].get("masked_request", "")}
    p1 = case.get("phase1_persona") if fused else None
    wobble = {}
    if fused:
        for r in (hint or {}).get("strategy_ranking", []):
            wobble[r["strategy"]] = r.get("wobble", 5)
    pool = []
    for s in strategies:
        k = base_k
        if fused and weight_by_wobble and wobble:
            w = wobble.get(s, 5)
            k = max(1, round(base_k * (0.5 + w / 10.0)))  # weak strategies -> more candidates
        payload = {"task": "ape_forward", "axis": case["axis"], "goal": goal,
                   "strategy": s, "k": k, "demos": demos or []}
        if fused:
            payload["susceptibility"] = _susceptibility_hint(hint, s)
            payload["exemplars"] = exemplars.get(s, [])
            if p1:
                payload["phase1_persona"] = {"system_instruction": p1.get("system_instruction", ""),
                                             "opening_utterances": p1.get("opening_utterances", []),
                                             "distortion": p1.get("distortion")}
        src = "ape_forward" if fused else "ape_vanilla"
        for text in invoke(gen_cmd, payload).get("candidates", []):
            pool.append({"text": text, "strategy": s, "source": src})
    return pool


def expand_pool(winners, gen_cmd, k=3):
    """APE Monte-Carlo resampling: add semantic variations of high-scoring openings."""
    extra = []
    for w in winners:
        out = invoke(gen_cmd, {"task": "ape_resample", "text": w["text"],
                               "strategy": w.get("strategy", ""), "k": k})
        for v in out.get("variations", []):
            extra.append({"text": v, "strategy": w.get("strategy"), "source": "ape_resample"})
    return extra


def apo_refine(case, failures, gen_cmd, k=5):
    """APO: analyze failed openings and generate improved candidates."""
    out = invoke(gen_cmd, {"task": "apo_feedback", "goal": case["goal"], "failures": failures, "k": k})
    cands = [{"text": t, "strategy": "apo", "source": "apo"} for t in out.get("candidates", [])]
    return cands, out.get("fault_reasons", [])
