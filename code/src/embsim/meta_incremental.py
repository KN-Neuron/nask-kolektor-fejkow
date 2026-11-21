"""Przyrostowo na Mecie: reklamy z treścią chronologicznie przez Gallery.add; proxy prawdy: twórca (page_id). Porównanie reguły rzadkiego śladu."""
import json, random, time, copy, warnings, collections, sys
import numpy as np
from sklearn.metrics import adjusted_rand_score
warnings.filterwarnings("ignore")
from embsim.api import Gallery, case_from_meta_ad
from embsim.bench import load_frozen
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
rows = [json.loads(l) for l in open("../data/meta/sample_s1.jsonl", encoding="utf-8")]
cases = []
for r in rows:
    c = case_from_meta_ad(r)
    if c.text.strip() and not c.meta.get("flagged_by_meta") and r.get("page_id"): cases.append(c)
by = collections.defaultdict(list)
for c in cases: by[c.meta["page_id"]].append(c)
rng = random.Random(7)
pages = [p for p, v in by.items() if len(v) >= 3]
rng.shuffle(pages)
N_PAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 100
sel = []
for p in pages[:N_PAGES]: sel += sorted(by[p], key=lambda c: c.meta.get("ad_creation_time", ""))[:10]
sel.sort(key=lambda c: (c.meta.get("ad_creation_time", ""), c.id))
log(f"reklam z treścią {len(cases)}, twórców >=3: {len(pages)}; próbka: {len(sel)} reklam, {min(N_PAGES,len(pages))} twórców")
truth = [c.meta["page_id"] for c in sel]
base, _ = load_frozen("v3_mixed_pca")
for t_camp in (0.95, 0.5):
    for rare in (None, 2, 4):
        for t_op in (0.25, 0.45):
            cfg = copy.deepcopy(base); cfg.op_rare_df = rare; cfg.thresholds["campaign"] = t_camp; cfg.thresholds["operator"] = t_op
            g = Gallery(cfg); t0 = time.time()
            for c in sel: g.add(copy.deepcopy(c))
            pos = {c.id: i for i, c in enumerate(sel)}; O = [None]*len(sel); K = [None]*len(sel)
            for it in g.items: O[pos[it["case"].id]] = it["operator"]; K[pos[it["case"].id]] = it["group"]
            # czystość: odsetek reklam w grupie operatora z >1 twórcą
            grp = collections.defaultdict(set)
            for o, t in zip(O, truth): grp[o].add(t)
            mixed = sum(1 for o in O if len(grp[o]) > 1) / len(O)
            log(f"t_kamp={t_camp} rare={rare} t_op={t_op}: ARI op/twórca {adjusted_rand_score(truth,O):.3f}, ARI kamp/twórca {adjusted_rand_score(truth,K):.3f}, "
                f"grup O {len(set(O))} (twórców {len(set(truth))}), reklam w mieszanych grupach {mixed:.2f}, {time.time()-t0:.0f}s")
