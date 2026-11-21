"""Synthetic comments (placeholders only) and the comment-layer analysis (E8)."""
from __future__ import annotations

import hashlib
import hmac
import random
from collections import Counter, defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd
from datasketch import MinHashLSH

from ..process.extract import extract_artifacts
from ..process.hashing import components, minhash
from ..process.normalize import comment_key
from ..schema import Ad, Comment

CAMP_TEMPLATES = ["Dziękuję, wypłata przyszła już dziś, polecam!", "Jak zacząć? Napisz na {contact}", "Działa naprawdę, sprawdziłem na własnym koncie",
                  "Kontakt do opiekuna: {contact}", "Też zarobiłam, dzięki za wskazówki!", "Pytanie: czy trzeba coś wpłacać na start? {contact}"]
ORGANIC = ["ładne zdjęcie", "ktoś już kupował w tym sklepie?", "przesyłka dotarła szybciej niż myślałem", "czy jest dostępny w innym kolorze",
           "fajna promocja, ale u konkurencji taniej", "dzięki za info", "gdzie można zobaczyć regulamin?", "mam podobny model od roku, jestem zadowolony",
           "a ile trwa dostawa do Gdańska", "super oferta na weekend", "nie polecam, długo czekałem na zwrot", "ciekawe, sprawdzę jutro"]
SYN = {"Dziękuję": "Dzięki", "polecam": "gorąco polecam", "naprawdę": "faktycznie", "Kontakt": "Numer"}


def hash_author(author: str, salt: str) -> str:
    return hmac.new(salt.encode(), author.encode(), hashlib.sha256).hexdigest()[:24]


def gen_comments(ads: list[Ad], seed: int, salt: str = "demo-salt", per_ad: tuple[int, int] = (3, 8)) -> list[Comment]:
    rng = random.Random(seed)
    out: list[Comment] = []
    pools: dict[str, list[str]] = {}
    contacts: dict[str, str] = {}
    for a in ads:
        camp = a.truth_campaign
        if camp:
            pools.setdefault(camp, [hash_author(f"{camp}-bot{i}", salt) for i in range(25)])
            contacts.setdefault(camp, f"t.me/test_{camp.lower()}{rng.randint(10, 99)}")
        k = rng.randint(*per_ad)
        for j in range(k):
            if camp:
                t = rng.choice(CAMP_TEMPLATES)
                txt = t.format(contact=contacts[camp])
                if rng.random() < 0.5:
                    for w, s in SYN.items():
                        txt = txt.replace(w, s)
                author = rng.choice(pools[camp])
                ts = a.t + timedelta(minutes=rng.uniform(1, 25))
            else:
                txt = rng.choice(ORGANIC) + rng.choice(["", "!", " :)", "."])
                author = hash_author(f"org{rng.randint(0, 5000)}", salt)
                ts = a.t + timedelta(minutes=rng.uniform(5, 2000))
            out.append(Comment(comment_id=f"synthetic:{a.ad_id}-{j}", ad_id=a.ad_id, source="synthetic", author_hash=author, text=txt, ts=ts,
                               artifacts=extract_artifacts(txt), truth_campaign=camp))
    return out


def comment_templates(comments: list[Comment], threshold: float = 0.6, perm: int = 64) -> np.ndarray:
    keys = [comment_key(c.text) for c in comments]
    lsh = MinHashLSH(threshold=threshold, num_perm=perm)
    mhs = [minhash(k, perm) for k in keys]
    for i, m in enumerate(mhs):
        lsh.insert(str(i), m)
    edges = [(i, int(j)) for i, m in enumerate(mhs) for j in lsh.query(m) if int(j) > i]
    return np.array(components(len(comments), edges))


def sync_accounts(comments: list[Comment], ads: dict[str, Ad], window_min: float, min_ads: int = 3) -> dict[str, float]:
    """Accounts that comment on many ads, each shortly after the ad start. Reported as aggregate clusters only."""
    per = defaultdict(list)
    for c in comments:
        a = ads.get(c.ad_id or "")
        if a:
            per[c.author_hash].append((c.ad_id, (c.ts - a.t).total_seconds() / 60))
    return {h: float(np.mean([m <= window_min for _, m in v])) for h, v in per.items() if len({x for x, _ in v}) >= min_ads}


def run_comment_demo(cfg: dict, seed: int = 1) -> pd.DataFrame:
    from ..eval.experiments import _save, load_ads

    ads = [a for a in load_ads(cfg) if a.source != "synthetic_background" or a.meta.get("split") != "fit"][:2500]
    cs = gen_comments(ads, seed, "demo-salt")
    ad_by = {a.ad_id: a for a in ads}
    lab = comment_templates(cs, cfg["comments"]["lsh_threshold"])
    truth = np.array([c.truth_campaign or "organic" for c in cs])
    # template purity: share of comments whose template cluster is dominated by one campaign
    pur = []
    for t in set(lab):
        m = lab == t
        if m.sum() >= 5:
            pur.append(Counter(truth[m]).most_common(1)[0][1] / m.sum())
    arts = Counter(a.value for c in cs for a in c.artifacts if a.kind in ("telegram", "whatsapp", "phone"))
    art_camp = defaultdict(set)
    for c in cs:
        for a in c.artifacts:
            art_camp[a.value].add(c.truth_campaign)
    sync = sync_accounts(cs, ad_by, cfg["comments"]["sync_window_minutes"])
    camp_acc = {h for c in cs if c.truth_campaign for h in [c.author_hash]}
    flagged = {h for h, v in sync.items() if v >= 0.8}
    df = pd.DataFrame([{"n_comments": len(cs), "n_templates_ge5": len(pur), "template_purity_mean": float(np.mean(pur)) if pur else float("nan"),
                        "artifacts_found": len(arts), "artifacts_single_campaign": sum(len(v) == 1 for v in art_camp.values()),
                        "sync_accounts_flagged": len(flagged), "flagged_precision_campaign_accounts": len(flagged & camp_acc) / max(len(flagged), 1),
                        "note": "SYNTHETIC comments, placeholder contacts"}])
    _save("E8_comments", df, cfg, seed)
    return df
