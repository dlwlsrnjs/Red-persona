"""Best-Arm-Identification selector over strategy x register arms.

Hybrid of ArtPerception-style measurement and online best-arm identification
(Efficient Prompt Optimization Through the Lens of BAI): the measured
susceptibility wobble warm-starts the arms (and gives the cluster structure), but
the best attack strategy is identified ONLINE on the real target, so a wrong Top-1
is corrected by exploration instead of being committed. Each "arm" is a
(strategy, register) cluster; pulling an arm = generate+send one client turn with
that strategy/register and observe the progress reward (1-10, normalized to 0-1).

Pure logic (no I/O) so it is unit-testable; the attack loop lives in ``pcsa.py``.
"""
from __future__ import annotations

import math

STRATEGIES = ("reassurance_seeking", "appeal_to_expertise", "intellectualization", "metaphorical_expression")
REGISTERS = ("plain", "clinical")
ARMS = tuple((s, r) for s in STRATEGIES for r in REGISTERS)


class BAISelector:
    """UCB-E selection with successive elimination and optional warm-start.

    warm_start: {(strategy, register): wobble(1-10)} -> each seeded as one pseudo
    pull of reward wobble/10. ``c`` is the exploration coefficient.
    """

    def __init__(self, arms=ARMS, warm_start=None, c=0.7, min_active=2):
        self.arms = list(arms)
        self.c = c
        self.min_active = min_active
        self.counts = {a: 0 for a in self.arms}
        self.sums = {a: 0.0 for a in self.arms}
        self.active = list(self.arms)
        self.total = 0
        if warm_start:
            for a, wobble in warm_start.items():
                if a in self.counts:
                    self.counts[a] = 1
                    self.sums[a] = max(0.0, min(1.0, wobble / 10.0))
                    self.total += 1

    def mean(self, a):
        return self.sums[a] / self.counts[a] if self.counts[a] else 0.5

    def _bonus(self, a):
        return self.c * math.sqrt(math.log(self.total + 2) / (self.counts[a] + 1e-9))

    def select(self, k):
        """Pick up to k distinct active arms by UCB-E (mean + exploration bonus)."""
        ranked = sorted(self.active, key=lambda a: self.mean(a) + self._bonus(a), reverse=True)
        return ranked[:max(1, k)]

    def update(self, a, reward):
        """Record a pull of arm a with reward in [0,1]."""
        reward = max(0.0, min(1.0, reward))
        self.counts[a] += 1
        self.sums[a] += reward
        self.total += 1

    def eliminate(self):
        """Drop arms whose UCB upper bound < the best arm's LCB (keep >= min_active)."""
        if len(self.active) <= self.min_active:
            return
        lcb_best = max((self.mean(a) - self._bonus(a)) for a in self.active)
        survivors = [a for a in self.active if self.mean(a) + self._bonus(a) >= lcb_best]
        if len(survivors) < self.min_active:  # keep the top arms by mean up to min_active
            survivors = sorted(self.active, key=self.mean, reverse=True)[:self.min_active]
        self.active = survivors

    def best(self):
        """Current best-identified arm by empirical mean (ties -> most pulled)."""
        return max(self.active, key=lambda a: (self.mean(a), self.counts[a]))

    def stats(self):
        return {f"{s}:{r}": {"mean": round(self.mean((s, r)), 3), "pulls": self.counts[(s, r)],
                             "active": (s, r) in self.active} for (s, r) in self.arms}
