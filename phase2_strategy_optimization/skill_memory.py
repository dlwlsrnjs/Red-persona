"""Cross-case skill memory for strategy selection (RedAgent-style, adapted).

Accumulates, per (axis, strategy, register), how often that combination actually
produced an UNSAFE target response across cases, and exposes a success prior that
re-weights the measured-susceptibility strategy ranking. This turns the static
pre-test wobble into an accumulating, feedback-driven prior (our adaptation of
RedAgent's memory buffer to a *measured* susceptibility signal). Thread-safe and
optionally JSON-persisted so it survives restarts and grows across runs.

Opt-in: only the ``profile_memory`` condition uses it; all other conditions and
the default method are unchanged.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class SkillMemory:
    def __init__(self, path=None, alpha=1.0, beta=1.0):
        # Beta(alpha,beta) smoothing so unseen arms start at the prior mean, not 0/1.
        self.path = Path(path) if path else None
        self.alpha, self.beta = alpha, beta
        self._lock = threading.Lock()
        self._counts = {}  # key "axis|strategy|register" -> [unsafe, total]
        if self.path and self.path.exists():
            try:
                self._counts = json.loads(self.path.read_text(encoding="utf-8")).get("counts", {})
            except (ValueError, OSError):
                self._counts = {}

    @staticmethod
    def _key(axis, strategy):
        return f"{axis}|{strategy}"

    def update(self, axis, strategy, unsafe):
        """Record one case outcome for (axis, strategy). Strategy-level: the data
        shows aware concentrates by strategy, so register is not tracked here."""
        with self._lock:
            c = self._counts.setdefault(self._key(axis, strategy), [0, 0])
            c[0] += 1 if unsafe else 0
            c[1] += 1
            if self.path:
                try:
                    tmp = self.path.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps({"counts": self._counts}, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(self.path)
                except OSError:
                    pass

    def success(self, axis, strategy):
        """Smoothed success rate (Beta posterior mean) for this (axis, strategy)."""
        with self._lock:
            u, t = self._counts.get(self._key(axis, strategy), [0, 0])
        return (u + self.alpha) / (t + self.alpha + self.beta)

    def reweight_ranking(self, axis, ranking, blend=0.5):
        """Return a copy of a strategy_ranking (list of {strategy, register, wobble})
        with wobble blended toward observed per-strategy success: new =
        (1-b)*wobble/10 + b*success, rescaled to 0-10, re-sorted. Cold start (no
        counts) -> success == prior mean for every strategy, so order is unchanged
        and this never hurts before memory accumulates."""
        if not ranking:
            return ranking
        out = []
        for r in ranking:
            s = self.success(axis, r.get("strategy", ""))
            w = float(r.get("wobble", 5)) / 10.0
            score = (1 - blend) * w + blend * s
            out.append({**r, "wobble": round(score * 10, 2), "_memory_success": round(s, 3)})
        out.sort(key=lambda r: r["wobble"], reverse=True)
        return out
