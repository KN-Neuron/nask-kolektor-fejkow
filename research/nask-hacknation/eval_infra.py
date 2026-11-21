"""Ocena kanału infrastruktury na domenach z ___BACKUP.zip. Etykiety kampanii pochodzą z TYTUŁÓW stron (nazwy plików w zipie), bez rozpakowywania.
Uwaga: reguły dopracowano po obejrzeniu tych danych (próbka 9 domen), więc to ilustracja, nie niezależny test."""
import itertools, sys
sys.path.insert(0, "code/src")
from fejki.config import load_config
from fejki.infra.collect import InfraRecord, cache_path
from fejki.infra.link import evidence, score

LABELS = {  # tytuł strony -> kampania
    "dorquesio.click": "brzoska", "wernulio.live": "brzoska", "lundevra.live": "brzoska",
    "falmurek.live": "napasc", "grentavo.click": "napasc",
    "spiritualityinsports.org": "trudna_odp", "sfuxd.com": "trudna_odp",
    "smartcoved.pro": "olejnik", "door-focus.com": "cactus", "move-fitlum.top": "kardivix", "zenithlab.ink": "grzybica",
}
cfg = load_config().get("infra")
recs = {d: InfraRecord.model_validate_json(cache_path(d).read_text()) for d in LABELS}
pairs = [(a, b, score(evidence(recs[a], recs[b], cfg))) for a, b in itertools.combinations(sorted(LABELS), 2)]
truth = lambda a, b: LABELS[a] == LABELS[b]
print(f"pary: {len(pairs)}, prawdziwie z jednej kampanii: {sum(truth(a, b) for a, b, _ in pairs)}")
for thr in (0.5, 0.6, 0.7, 0.8):
    tp = sum(1 for a, b, s in pairs if s >= thr and truth(a, b)); fp = sum(1 for a, b, s in pairs if s >= thr and not truth(a, b))
    fn = sum(1 for a, b, s in pairs if s < thr and truth(a, b))
    p = tp / (tp + fp) if tp + fp else float("nan"); r = tp / (tp + fn) if tp + fn else float("nan")
    print(f"próg {thr}: TP={tp} FP={fp} FN={fn}  precyzja={p:.2f} recall={r:.2f}")
print("\nprawdziwe pary i ich wynik:")
for a, b, s in sorted(pairs, key=lambda x: -x[2]):
    if truth(a, b): print(f"  {a} <-> {b}: {s}")
print("\nfałszywe pary z wynikiem >= 0.5:")
for a, b, s in sorted(pairs, key=lambda x: -x[2]):
    if s >= 0.5 and not truth(a, b): print(f"  {a} ({LABELS[a]}) <-> {b} ({LABELS[b]}): {s}")
