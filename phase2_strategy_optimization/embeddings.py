"""Text embeddings + lightweight k-means, used only by TRIPLE-CLST to cluster the
candidate prompt pool (embedding clustering, not strategy labels). Other selectors
(SH/CR/UCB/uniform) do not use this. Stdlib + OpenAI embeddings API.
"""
from __future__ import annotations

import json
import math
import os
import random
import urllib.request

EMBED_URL = "https://api.openai.com/v1/embeddings"


def embed_texts(texts, model="text-embedding-3-small", batch=256):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set")
    vecs = []
    for i in range(0, len(texts), batch):
        body = json.dumps({"model": model, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(EMBED_URL, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())["data"]
        vecs.extend(e["embedding"] for e in data)
    return vecs


def _dist2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(vecs, k, iters=25, seed=0):
    """Lloyd's k-means; returns a list of cluster ids (one per vector)."""
    n = len(vecs)
    k = max(1, min(k, n))
    rng = random.Random(seed)
    centers = [vecs[i] for i in rng.sample(range(n), k)]
    assign = [0] * n
    for _ in range(iters):
        changed = False
        for i, v in enumerate(vecs):
            j = min(range(k), key=lambda c: _dist2(v, centers[c]))
            if j != assign[i]:
                assign[i], changed = j, True
        for c in range(k):
            members = [vecs[i] for i in range(n) if assign[i] == c]
            if members:
                centers[c] = [sum(col) / len(members) for col in zip(*members)]
        if not changed:
            break
    return assign


def cluster_assignment(texts, k=None):
    """Return {index: cluster_id} by embedding + k-means. k defaults to ~sqrt(n)."""
    if len(texts) < 2:
        return {i: 0 for i in range(len(texts))}
    vecs = embed_texts(texts)
    k = k or max(2, round(math.sqrt(len(texts))))
    labels = kmeans(vecs, k)
    return {i: labels[i] for i in range(len(texts))}
