"""Deterministic preservation of explicit suicide-risk state."""
from __future__ import annotations

import re


def from_text(text, fallback=None):
    value = str(text).casefold()
    state = dict(fallback or {})
    ideation = bool(re.search(r"\bsuicid|kill myself|end my life|want to die|thoughts? about dying", value))
    denied = bool(re.search(r"\b(?:won't|will not|wouldn't|do not|don't)\s+(?:commit|do it|act)|\bno (?:plan|intent)", value))
    plan = bool(re.search(r"\b(?:plan(?:ning)? to|going to|intend to|in (?:january|february|march|april|may|june|july|august|september|october|november|december)|specific plan)", value))
    preparation = bool(re.search(r"\b(?:get|getting|put|putting) my affairs in order|preparatory|preparation|goodbye (?:note|message)|recent .{0,20}attempt", value))
    if ideation:
        state["ideation"] = True
    if preparation:
        state.update(intent="present", plan="present", preparation="present")
    elif plan:
        state.update(intent="present", plan="present")
        state.setdefault("preparation", "none")
    elif denied:
        state.update(intent="denied", plan="none", preparation="none")
    for key in ("intent", "plan", "preparation"):
        state.setdefault(key, "unclear")
    state.setdefault("ideation", False)
    return state
