"""Mniejsza próbka Mety z jawnym kryterium (wersja S1). Wynik to zwykły plik JSONL, więc `load.py meta --file` ładuje go bez zmian.

    .venv/bin/python graph/sample.py                       # -> data/meta/sample_s1.jsonl + artifacts/samples/sample_s1.json
    .venv/bin/python graph/load.py meta --file ../data/meta/sample_s1.jsonl

Kryterium S1 (opis i uzasadnienie: docs/13_BAZA_GRAFOWA.md, „Próbka Mety”):
1. Jednostka losowania to TWÓRCA (page_id), nie pojedyncza reklama: do próbki wchodzi twórca z (przyciętym) kompletem reklam.
2. Grupa SCAM = twórcy z co najmniej jedną reklamą zdjętą przez Metę (`meta_flag`). Biorę WSZYSTKICH „mieszanych” (część reklam
   zdjęta, część nie: tylko u nich zostaje tekst przy znanej etykiecie) i dobieram losowo „w pełni zdjętych” z >= 2 reklamami.
3. Grupa KONTROLA = twórcy bez żadnej zdjętej reklamy, z >= 2 reklamami, dobrani tak, żeby rozkład tematów (zapytanie, którym ich
   znaleziono) był taki sam jak w grupie SCAM. Inaczej model nauczyłby się „kasyno = scam” zamiast rozpoznawać twórcę.
4. Twórca ma najwyżej CAP reklam (losowo), żeby kilku gigantów nie zdominowało próbki.
5. Zawsze wchodzą twórcy powiązani z materiałami NASK (strona o nazwie z ANCHOR_PAGES), żeby było co łączyć z NASK-10.
Losowanie jest deterministyczne (ziarno), więc każdy w zespole dostaje ten sam plik.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from load import ADS, FLAGS, ROOT, as_list

NAME = "s1"
ANCHOR_PAGES = ("Sharon Coleman", "Evelyn Johnson")  # nazwy stron twórców powiązanych z przypadkami NASK 48 i 47


def page_stats(path: Path) -> tuple[dict[str, list[str]], dict[str, dict]]:
    """page_id -> surowe linie reklam oraz page_id -> {n, flagged, topic, anchor}."""
    lines: dict[str, list[str]] = defaultdict(list)
    st: dict[str, dict] = defaultdict(lambda: {"n": 0, "flagged": 0, "topics": Counter(), "anchor": False})
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        p = r["page_id"]
        text = " ".join(str(x) for k in ("ad_creative_bodies", "ad_creative_link_captions", "ad_creative_link_titles")
                        for x in as_list(r.get(k)))
        s = st[p]
        s["n"] += 1
        s["flagged"] += any(k in text for k in FLAGS)
        s["topics"][r.get("_query") or "?"] += 1
        s["anchor"] |= (r.get("page_name") or "") in ANCHOR_PAGES
        lines[p].append(line)
    for s in st.values():
        s["topic"] = s.pop("topics").most_common(1)[0][0]
        s["kind"] = "kontrola" if not s["flagged"] else "scam_pełny" if s["flagged"] == s["n"] else "scam_mieszany"
    return lines, st


def choose(st: dict[str, dict], n_scam: int, rng: random.Random) -> dict[str, str]:
    """page_id -> powód wyboru."""
    picked = {p: "kotwica_nask" for p, s in st.items() if s["anchor"]}
    mixed = sorted(p for p, s in st.items() if s["kind"] == "scam_mieszany")
    full = sorted(p for p, s in st.items() if s["kind"] == "scam_pełny" and s["n"] >= 2)
    rng.shuffle(full)
    for p in mixed + full[: max(0, n_scam - len(mixed))]:
        picked.setdefault(p, st[p]["kind"])
    # kontrola: tyle samo twórców w każdym temacie, co w grupie scam
    need = Counter(st[p]["topic"] for p, why in picked.items() if why.startswith("scam"))
    pool: dict[str, list[str]] = defaultdict(list)
    for p, s in sorted(st.items()):
        if s["kind"] == "kontrola" and s["n"] >= 2 and p not in picked:
            pool[s["topic"]].append(p)
    rest: list[str] = []
    for t in sorted(pool):
        rng.shuffle(pool[t])
        for p in pool[t][: need[t]]:
            picked[p] = "kontrola"
        rest += pool[t][need[t]:]
    short = sum(need.values()) - sum(1 for w in picked.values() if w == "kontrola")
    rng.shuffle(rest)
    for p in rest[:max(0, short)]:  # temat bez dość kontroli: uzupełnij z innych tematów
        picked[p] = "kontrola"
    return picked


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scam", type=int, default=1000, help="ilu twórców w grupie scam (mieszani wchodzą wszyscy)")
    ap.add_argument("--cap", type=int, default=20, help="maks. reklam na twórcę")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    lines, st = page_stats(ADS)
    picked = choose(st, a.scam, rng)
    out_rows: list[str] = []
    for p in sorted(picked):
        ls = lines[p]
        out_rows += ls if len(ls) <= a.cap else rng.sample(ls, a.cap)
    out = ADS.parent / f"sample_{NAME}.jsonl"
    out.write_text("".join(out_rows), encoding="utf-8")
    n_flag = sum(any(k in ln for k in FLAGS) for ln in out_rows)
    summary = {
        "kryterium": NAME, "ziarno": a.seed, "cap": a.cap, "scam_docelowo": a.scam,
        "twórców": dict(Counter(picked.values())), "reklam": len(out_rows), "reklam_zdjętych": n_flag,
        "tematy_scam": dict(Counter(st[p]["topic"] for p, w in picked.items() if w.startswith("scam")).most_common()),
        "tematy_kontrola": dict(Counter(st[p]["topic"] for p, w in picked.items() if w == "kontrola").most_common()),
        "twórcy": picked,
    }
    man = ROOT / "artifacts" / "samples" / f"sample_{NAME}.json"
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print({k: v for k, v in summary.items() if k not in ("twórcy", "tematy_scam", "tematy_kontrola")})
    print("plik:", out, "\nopis:", man)


if __name__ == "__main__":
    main()
