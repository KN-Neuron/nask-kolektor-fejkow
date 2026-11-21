"""Campaign cards (Markdown) and proposed-domains CSV for the analyst queue. The system never files anything automatically."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import ROOT
from ..embed.erase import rule_label
from .coordination import features, score


def build_cards(ads, X, labels, cfg: dict, cert: dict | None, out_dir: str | Path | None = None, with_cert_in_score: bool = True) -> pd.DataFrame:
    out = Path(out_dir or ROOT / "artifacts" / "cards")
    out.mkdir(parents=True, exist_ok=True)
    w, tau, m = cfg["coordination"]["weights"], cfg["coordination"]["tau"], cfg["coordination"]["min_ads"]
    rows, proposed = [], []
    for c, n in Counter(labels).most_common():
        if n < m:
            continue
        idx = np.where(labels == c)[0]
        sub = [ads[i] for i in idx]
        f = features(sub, X[idx], cert)
        s = score(f, w, with_cert=with_cert_in_score)
        if s < tau:
            continue
        cid = f"campaign-{c:04d}"
        cen = X[idx].mean(0)
        rep = idx[np.argsort(-(X[idx] @ cen))[:5]]
        topics = Counter(rule_label(ads[i].text_norm) for i in idx)
        days = Counter(ads[i].t.date() for i in idx)
        t0, t1 = min(a.t for a in sub), max(a.t for a in sub)
        doms = sorted({d for a in sub for d in a.domains})
        arts = sorted({(x.kind, x.value) for a in sub for x in a.artifacts if x.kind != "url"})
        dom_rows = []
        for d in doms:
            e = (cert or {}).get(d)
            dom_rows.append(f"| {d} | {'tak' if e else 'nie'} | {e['insert_date'].date() if e and e.get('insert_date') else ''} | {e['delete_date'].date() if e and e.get('delete_date') else ''} |")
            if not e:
                proposed.append({"campaign_id": cid, "domain": d, "score": round(s, 3),
                                 "reasons": f"near_dup={f['near_dup']:.2f}; start_sync={f['start_sync']:.2f}; domain_novelty={f['domain_novelty']:.2f}; adv_low_entropy={f['adv_entropy_low']:.2f}"})
        md = [f"# Karta kampanii {cid}", "",
              f"- Okno czasowe: {t0.date()} do {t1.date()}", f"- Liczba kreacji: {len(sub)}; reklamodawców: {f['n_advertisers']}; domen: {f['n_domains']}",
              f"- Wynik koordynacji (score): {s:.3f} (tau={tau})", "",
              "## Sygnały", *[f"- {k}: {f[k]:.3f}" for k in ("near_dup", "adv_entropy_low", "domain_novelty", "start_sync", "cert_hit")], "",
              "## Domeny", "| domena | na Liście CERT | data wpisu | wykreślenie |", "|---|---|---|---|", *dom_rows, "",
              "## Artefakty kontaktowe", *([f"- {k}: {v}" for k, v in arts] or ["- brak"]), "",
              f"## Tematy wykryte w klastrze (rozpiętość: {len(topics)})", *[f"- {t}: {n}" for t, n in topics.most_common()], "",
              "## Reprezentatywne kreacje", *[f"{k + 1}. {ads[i].text_norm}" for k, i in enumerate(rep)], "",
              "## Oś czasu (reklamy na dzień)", *[f"- {d}: {n}" for d, n in sorted(days.items())], "",
              "Uwaga: system tylko priorytetyzuje kolejkę analityka; decyzja o wpisie na Listę należy do człowieka."]
        (out / f"{cid}.md").write_text("\n".join(md))
        rows.append({"campaign_id": cid, "cluster": int(c), "start": t0, "end": t1, "n_ads": len(sub), "score": s,
                     "n_domains": f["n_domains"], "cert_hit": bool(f["cert_hit"]), "n_topics": len(topics),
                     "purity_campaign": (Counter(a.truth_campaign for a in sub).most_common(1)[0][1] / len(sub)) if any(a.truth_campaign for a in sub) else None})
    pd.DataFrame(proposed, columns=["campaign_id", "domain", "score", "reasons"]).to_csv(out / "proposed_domains.csv", index=False)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "artifacts" / "tables" / "campaigns.csv", index=False)
    return df
