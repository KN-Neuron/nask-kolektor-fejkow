"""Uczenie metryki podobieństwa na zamrożonych wektorach Qwen: głowa liniowa + strata kontrastowa, potem kalibracja progu.

    python -m embsim.metric ARTIFACTS_DIR [--steps 1500] [--dim 256]

Wejście (z grafu, zob. graph/subjects.py): ARTIFACTS_DIR/qwen_ads/{hashes.json,chunk_*.npy|vectors.npy} oraz ad_meta.jsonl
(id, h = hash tekstu, topics, fold, subject). Jednostką jest unikalny tekst reklamy.

Etykiety: dwa teksty to „ta sama kampania”, gdy ich reklamy leżą w tym samym podmiocie grafu (wspólny płatnik, reklamodawca,
domena lub identyczny tekst; huby nie łączą). Model widzi TYLKO wektor tekstu, nigdy węzłów grafu, więc etykieta nie jest cechą.
Trudne negatywy: teksty o tym samym temacie (słowo kluczowe wyszukania), ale z innego podmiotu.
Próg wybieramy NA WALIDACJI (precyzja docelowa) i mierzymy na teście, którego nie widział ani trening, ani dobór progu.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score

DEV = "mps" if torch.backends.mps.is_available() else "cpu"


# --------------------------------------------------------------------------------------------------------------------
# dane


def load_vectors(d: Path) -> tuple[list[str], np.ndarray]:
    hashes = json.loads((d / "hashes.json").read_text())
    full = d / "vectors.npy"
    if full.exists():
        V = np.load(full)
    else:  # tryb częściowy (trwa liczenie): same gotowe wsady
        V = np.concatenate([np.load(c) for c in sorted(d.glob("chunk_*.npy"))])
    hashes = hashes[: len(V)]
    V = V.astype(np.float32)
    return hashes, V / np.linalg.norm(V, axis=1, keepdims=True)


class Units:
    """Unikalne teksty z foldem, podmiotem i tematami. Teksty niejednoznaczne (wiele podmiotów/foldów) są wykluczone."""

    def __init__(self, art: Path):
        hashes, V = load_vectors(art / "qwen_ads")
        pos = {h: i for i, h in enumerate(hashes)}
        ads = defaultdict(lambda: {"folds": set(), "subj": set(), "topics": set()})
        for line in (art / "ad_meta.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            if r["h"] in pos:
                u = ads[r["h"]]
                u["folds"].add(r["fold"]); u["subj"].add(r["subject"]); u["topics"].update(r["topics"])
        keep = [h for h, u in ads.items() if len(u["subj"]) == 1 and len(u["folds"]) == 1]
        self.dropped = len(ads) - len(keep)
        self.X = V[[pos[h] for h in keep]]
        self.subject = np.array([next(iter(ads[h]["subj"])) for h in keep])
        self.fold = np.array([next(iter(ads[h]["folds"])) for h in keep])
        self.topics = [ads[h]["topics"] for h in keep]

    def idx(self, fold: str) -> np.ndarray:
        return np.where(self.fold == fold)[0]


# --------------------------------------------------------------------------------------------------------------------
# trening


class Sampler:
    def __init__(self, U: Units, rng: np.random.Generator):
        self.U, self.rng = U, rng
        tr = U.idx("train")
        by_sub = defaultdict(list)
        for i in tr:
            by_sub[U.subject[i]].append(i)
        self.multi = {s: v for s, v in by_sub.items() if len(v) >= 2}
        self.train = tr
        by_topic = defaultdict(list)
        for s, v in self.multi.items():
            for t in set().union(*(U.topics[i] for i in v)):
                by_topic[t].append(s)
        self.by_topic = {t: v for t, v in by_topic.items() if len(v) >= 8}
        self.subs = list(self.multi)

    def batch(self, B: int, n_extra: int, hard: bool):
        r = self.rng
        if hard and self.by_topic:
            t = r.choice(list(self.by_topic))
            pool = self.by_topic[t]
            S = list(r.choice(pool, size=min(B, len(pool)), replace=False))
        else:
            S = list(r.choice(self.subs, size=B, replace=False))
        a, p = [], []
        for s in S:
            i, j = r.choice(self.multi[s], size=2, replace=False)
            a.append(i); p.append(j)
        extra = r.choice(self.train, size=n_extra, replace=False)
        return np.array(a), np.array(p), extra, np.array(S)


def info_nce(head, X, a, p, extra, S, subj, tau):
    za, zp = head(X[a]), head(X[p])
    ze = head(X[extra])
    cand = torch.cat([zp, ze])                       # kandydaci: pozytywy z batcha + losowe negatywy
    logits = za @ cand.T / tau
    cand_sub = torch.cat([torch.as_tensor(S), torch.as_tensor(subj[extra])]).to(logits.device)
    same = (torch.as_tensor(S).to(logits.device)[:, None] == cand_sub[None, :])
    target = torch.arange(len(a), device=logits.device)
    same[target, target] = False                     # prawdziwy pozytyw nie jest „fałszywym negatywem”
    logits = logits.masked_fill(same, -1e4)          # reszta tego samego podmiotu też nie jest negatywem
    l1 = F.cross_entropy(logits, target)
    l2 = F.cross_entropy((zp @ za.T / tau), target)
    return (l1 + l2) / 2


class Head(torch.nn.Module):
    def __init__(self, d_in: int, d_out: int):
        super().__init__()
        self.lin = torch.nn.Linear(d_in, d_out, bias=False)
        torch.nn.init.orthogonal_(self.lin.weight)

    def forward(self, x):
        return F.normalize(self.lin(x), dim=-1)


# --------------------------------------------------------------------------------------------------------------------
# ocena


def sims(Z: np.ndarray) -> np.ndarray:
    return Z @ Z.T


def pair_labels(U: Units, idx: np.ndarray):
    s = U.subject[idx]
    pos = s[:, None] == s[None, :]
    T = [U.topics[i] for i in idx]
    topic = np.zeros_like(pos)
    inv = defaultdict(list)
    for k, ts in enumerate(T):
        for t in ts:
            inv[t].append(k)
    for ks in inv.values():
        ks = np.array(ks)
        topic[np.ix_(ks, ks)] = True
    return pos, topic & ~pos                         # (ta sama kampania, ten sam temat ale inna kampania = trudny negatyw)


def retrieval(S: np.ndarray, pos: np.ndarray) -> dict:
    S = S.copy(); np.fill_diagonal(S, -9)
    P = pos.copy(); np.fill_diagonal(P, False)
    has = P.any(1)
    order = np.argsort(-S[has], axis=1)
    hit = np.take_along_axis(P[has], order, axis=1)
    first = hit.argmax(1) + 1
    return {"n_zapytań": int(has.sum()), "R@1": float((first <= 1).mean()), "R@10": float((first <= 10).mean()),
            "MRR": float((1 / first).mean())}


def pair_scores(S, pos, hard):
    iu = np.triu_indices(len(S), 1)
    s, p, h = S[iu], pos[iu], hard[iu]
    return s, p, h


def pick_threshold(s, p, target):
    """Najniższy próg, przy którym precyzja >= target (na zbiorze, na którym go dobieramy)."""
    o = np.argsort(-s)
    tp = np.cumsum(p[o]); k = np.arange(1, len(o) + 1)
    prec = tp / k
    ok = np.where((prec >= target) & (tp >= 5))[0]
    return float(s[o][ok.max()]) if len(ok) else None


def at_threshold(s, p, t):
    pred = s >= t
    tp = int((pred & p).sum())
    return {"prog": round(t, 4), "precyzja": tp / max(int(pred.sum()), 1), "czułość": tp / max(int(p.sum()), 1),
            "połączonych_par": int(pred.sum())}


def evaluate(name, Zs: dict[str, np.ndarray], U: Units, target: float) -> dict:
    out = {}
    vi, ti = U.idx("val"), U.idx("test")
    pv, hv = pair_labels(U, vi)
    pt, ht = pair_labels(U, ti)
    sv, yv, hv_ = pair_scores(sims(Zs["val"]), pv, hv)
    st, yt, ht_ = pair_scores(sims(Zs["test"]), pt, ht)
    thr = pick_threshold(sv, yv, target)
    out["retrieval_val"] = retrieval(sims(Zs["val"]), pv)
    out["retrieval_test"] = retrieval(sims(Zs["test"]), pt)
    neg_hard = lambda s, y, h: (np.r_[s[y], s[h]], np.r_[np.ones(y.sum()), np.zeros(h.sum())])
    out["AUC_test_wszystkie_pary"] = float(roc_auc_score(yt, st))
    a, b = neg_hard(st, yt, ht_)
    out["AUC_test_trudne_negatywy"] = float(roc_auc_score(b, a))
    out["pozytywnych_par_test"] = int(yt.sum())
    out["próg_z_walidacji"] = thr
    if thr is not None:
        out["val_przy_progu"] = at_threshold(sv, yv, thr)
        out["test_przy_progu"] = at_threshold(st, yt, thr)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(sv, yv)
    out["kalibracja_p(próg)"] = float(iso.predict([thr])[0]) if thr is not None else None
    print(f"\n== {name}")
    for k, v in out.items():
        print(f"  {k}: {v}")
    return out


# --------------------------------------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("art", type=Path)
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--dim", type=int, default=256)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--tau", type=float, default=0.05)
    ap.add_argument("--target", type=float, default=0.9, help="docelowa precyzja przy wyborze progu (na walidacji)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    U = Units(a.art)
    print(f"jednostek (unikalnych tekstów): {len(U.X)}, wykluczonych jako niejednoznaczne: {U.dropped}")
    print({f: len(U.idx(f)) for f in ("train", "val", "test")})
    S = Sampler(U, np.random.default_rng(a.seed))
    print(f"podmiotów z >=2 tekstami w train: {len(S.multi)}, tematów do trudnych batchy: {len(S.by_topic)}")
    X = torch.as_tensor(U.X).to(DEV)
    head = Head(X.shape[1], a.dim).to(DEV)
    opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-4)
    vi = U.idx("val")
    pv, _ = pair_labels(U, vi)

    def val_mrr() -> float:
        with torch.no_grad():
            return retrieval(sims(head(X[vi]).cpu().numpy()), pv)["MRR"]

    best, best_sd = -1.0, None
    for step in range(1, a.steps + 1):
        aa, pp, ex, SS = S.batch(min(a.batch, len(S.multi)), 256, hard=(step % 2 == 0))
        loss = info_nce(head, X, aa, pp, ex, SS, U.subject, a.tau)
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 100 == 0:
            m = val_mrr()
            print(f"krok {step}  strata {loss.item():.3f}  val MRR {m:.3f}")
            if m > best:
                best, best_sd = m, {k: v.detach().clone() for k, v in head.state_dict().items()}
    head.load_state_dict(best_sd)
    with torch.no_grad():
        Zh = {f: head(X[U.idx(f)]).cpu().numpy() for f in ("val", "test")}
    Zr = {f: U.X[U.idx(f)] for f in ("val", "test")}
    Z1 = {f: (v[:, :1024] / np.linalg.norm(v[:, :1024], axis=1, keepdims=True)) for f, v in Zr.items()}
    rep = {"surowy_qwen": evaluate("surowy Qwen (bez uczenia)", Zr, U, a.target),
           "surowy_qwen_1024": evaluate("surowy Qwen przycięty do 1024 (jak w grafie)", Z1, U, a.target),
           "z_głową": evaluate(f"z wytrenowaną głową ({a.dim}d)", Zh, U, a.target)}
    torch.save(best_sd, a.art / "head.pt")
    (a.art / "metric_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
