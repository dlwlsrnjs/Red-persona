"""Fixed-budget best-arm-identification selectors over a candidate pool (TRIPLE).

Each selector picks the best candidate from a pool under a query budget, where a
"pull" applies a candidate to the target and returns a reward in [0,1] (we use
attack progress / 10). These are the Phase-2 selection algorithms we compare:

- ``uniform``            : evenly pull every candidate (budget/K each); pick best mean. (baseline)
- ``sequential_halving`` : TRIPLE-SH — each round pull survivors evenly, drop bottom half.
- ``continuous_reject``  : TRIPLE-CR — pull the least-pulled survivor; reject a trailing
                           candidate once the empirical gap exceeds a confidence radius.
- ``clustered``          : TRIPLE-CLST — BAI over clusters first, then within the best cluster.

Pure logic (no I/O): ``pull_fn(candidate) -> reward``. The attack glue lives elsewhere.
``warm_start`` seeds per-candidate (sum, count) from the measured profile.
"""
from __future__ import annotations

import math
import random


class _Stats:
    def __init__(self, candidates, warm_start=None):
        self.sum = {c: 0.0 for c in candidates}
        self.cnt = {c: 0 for c in candidates}
        self.pulls = 0
        if warm_start:
            for c, (s, n) in warm_start.items():
                if c in self.sum:
                    self.sum[c], self.cnt[c], self.pulls = s, n, self.pulls + n

    def record(self, c, r):
        self.sum[c] += max(0.0, min(1.0, r))
        self.cnt[c] += 1
        self.pulls += 1

    def mean(self, c):
        return self.sum[c] / self.cnt[c] if self.cnt[c] else 0.0


def _result(best, st, extra=None):
    out = {"best": best, "pulls": st.pulls,
           "means": {str(c): round(st.mean(c), 3) for c in st.sum},
           "counts": {str(c): st.cnt[c] for c in st.sum}}
    if extra:
        out.update(extra)
    return out


def uniform(candidates, pull_fn, budget, warm_start=None, **_):
    st = _Stats(candidates, warm_start)
    per = max(1, budget // max(1, len(candidates)))
    for c in candidates:
        for _i in range(per):
            if st.pulls >= budget:
                break
            st.record(c, pull_fn(c))
    best = max(candidates, key=lambda c: (st.mean(c), st.cnt[c]))
    return _result(best, st)


def sequential_halving(candidates, pull_fn, budget, warm_start=None, **_):
    st = _Stats(candidates, warm_start)
    survivors = list(candidates)
    rounds = max(1, math.ceil(math.log2(max(2, len(candidates)))))
    for _r in range(rounds):
        if len(survivors) <= 1:
            break
        per = max(1, (budget // rounds) // len(survivors))
        for c in survivors:
            for _i in range(per):
                if st.pulls >= budget:
                    break
                st.record(c, pull_fn(c))
        survivors.sort(key=lambda c: st.mean(c), reverse=True)
        survivors = survivors[:max(1, len(survivors) // 2)]
    best = max(survivors, key=lambda c: (st.mean(c), st.cnt[c]))
    return _result(best, st, {"algorithm": "sequential_halving"})


def continuous_reject(candidates, pull_fn, budget, warm_start=None, c_radius=0.7, min_active=1, **_):
    st = _Stats(candidates, warm_start)
    active = list(candidates)
    while st.pulls < budget and len(active) > max(1, min_active):
        arm = min(active, key=lambda c: st.cnt[c])  # pull the least-explored survivor
        st.record(arm, pull_fn(arm))
        best = max(active, key=st.mean)
        worst = min(active, key=st.mean)
        if best is not worst:
            radius = c_radius * (math.sqrt(math.log(st.pulls + 2) / (st.cnt[best] + 1e-9))
                                 + math.sqrt(math.log(st.pulls + 2) / (st.cnt[worst] + 1e-9)))
            if st.mean(best) - st.mean(worst) > radius:
                active.remove(worst)
    # spend any leftover budget on the current leader
    while st.pulls < budget:
        st.record(max(active, key=st.mean), pull_fn(max(active, key=st.mean)))
    best = max(active, key=lambda c: (st.mean(c), st.cnt[c]))
    return _result(best, st, {"algorithm": "continuous_reject", "survivors": len(active)})


def ucb(candidates, pull_fn, budget, warm_start=None, c=0.7, **_):
    """UCB (no clustering): pull by upper-confidence index; pick best empirical mean."""
    st = _Stats(candidates, warm_start)
    for c0 in candidates:  # one seeding pull each (within budget)
        if st.pulls >= budget:
            break
        st.record(c0, pull_fn(c0))
    while st.pulls < budget:
        arm = max(candidates, key=lambda a: st.mean(a) + c * math.sqrt(math.log(st.pulls + 2) / (st.cnt[a] + 1e-9)))
        st.record(arm, pull_fn(arm))
    best = max(candidates, key=lambda a: (st.mean(a), st.cnt[a]))
    return _result(best, st, {"algorithm": "ucb"})


def clustered(candidates, pull_fn, budget, cluster_of=None, warm_start=None, min_pool=12, **_):
    """TRIPLE-CLST: cluster candidates (embeddings via cluster_of), narrow to the best
    cluster, then pick within it. Clustering is skipped on small pools (falls back to SH)."""
    if cluster_of is None or len(candidates) < min_pool:
        return sequential_halving(candidates, pull_fn, budget, warm_start)
    cluster_of = cluster_of or (lambda c: 0)
    clusters = {}
    for c in candidates:
        clusters.setdefault(cluster_of(c), []).append(c)
    reps = {k: random.Random(k if isinstance(k, int) else hash(k)).choice(v) for k, v in clusters.items()}
    half = budget // 2 if len(clusters) > 1 else 0
    # stage 1: identify the best cluster via its representative (SH over reps)
    if half and len(reps) > 1:
        rep_res = sequential_halving(list(reps.values()), pull_fn, half, warm_start)
        best_rep = rep_res["best"]
        best_cluster = next(k for k, r in reps.items() if r == best_rep)
    else:
        best_cluster = next(iter(clusters))
    # stage 2: SH within the best cluster
    within = sequential_halving(clusters[best_cluster], pull_fn, budget - half, warm_start)
    within["algorithm"] = "clustered"
    within["best_cluster"] = str(best_cluster)
    return within


SELECTORS = {"uniform": uniform, "sequential_halving": sequential_halving,
             "continuous_reject": continuous_reject, "clustered": clustered, "ucb": ucb}
