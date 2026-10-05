"""Shared GPT-2 perplexity scorer (naturalness / stealthiness).

Used by the Phase I multi-objective fitness (penalize perturbations that raise
perplexity above a threshold, so added complexity keeps the attack natural) and
reusable anywhere a perplexity signal is needed. Lazy-loads the model on first
use so importing this module stays cheap and torch stays an optional dependency.
"""
from __future__ import annotations

import math


class PPLScorer:
    """Causal-LM perplexity of a text; low PPL = natural, evades perplexity filters."""

    def __init__(self, model_name: str = "gpt2"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self._torch = torch
        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForCausalLM.from_pretrained(model_name).eval()
        self.model_name = model_name

    def ppl(self, text: str) -> float:
        if not text or not text.strip():
            return float("inf")
        ids = self._tok(text, return_tensors="pt").input_ids
        if ids.size(1) < 2:
            return float("inf")
        with self._torch.no_grad():
            loss = self._model(ids, labels=ids).loss
        try:
            return float(math.exp(loss.item()))
        except OverflowError:
            return float("inf")

    def __call__(self, text: str) -> float:
        return self.ppl(text)


def ppl_penalty(ppl: float | None, threshold: float, weight: float) -> float:
    """Selection penalty (in progress-score points) for exceeding the PPL threshold.

    0 at or below threshold; ``weight`` when PPL is twice the threshold; grows
    linearly in the fractional overshoot. Returns 0 when PPL is unavailable.
    """
    if ppl is None or weight <= 0:
        return 0.0
    if ppl == float("inf"):
        return weight * 10.0
    return weight * max(0.0, (ppl - threshold) / threshold)
