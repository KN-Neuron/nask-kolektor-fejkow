"""Harness walidacji: kilka zbiorów, jawny podział dev / test / final, zamrożona konfiguracja, te same metryki wszędzie.

    python -m embsim.bench calibrate --name X [--family 2 --trace contain --combine noisy_or --adjust --lexical]
    python -m embsim.bench run --name adj              # dev + test (ziarna 8–10) + scenariusze odporności, konfiguracja zamrożona
    python -m embsim.bench compare                     # adj vs lex (kanał leksykalny) na zbiorach test
    python -m embsim.bench run --final                 # dodatkowo 10 przypadków NASK (odkrywać raz, na końcu)

Protokół (wymuszany kodem):
  * wzór, wagi i model są częścią konfiguracji; ich zmiana po `calibrate` unieważnia zamrożenie (run odmawia działania);
  * progi dobiera `calibrate` wyłącznie na dev (synth:1); zbiory test (synth:2..4) mają INNE konfiguracje generatora;
  * każde użycie zbiorów test/final jest dopisywane do history.jsonl, żeby było widać, ile razy na nie patrzyliśmy.

Ograniczenia, które raport wypisuje: syntetyka jest generowana pod cechy, które wyciągamy (mierzy odzyskiwanie podłożonego sygnału,
nie prawdziwych kampanii), a „prawda” dla NASK to nasze własne ustalenia (organizator nie podał etykiet).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .embed import text_vectors
from .features import Case, load_case
from .metrics import evaluate_level
from .score import DEFAULT_WEIGHTS, LEX_WEIGHTS, ROTATING, Corpus

ROOT = Path(__file__).resolve().parents[2]            # code/
ART = ROOT / "artifacts" / "bench"
HISTORY = ART / "history.jsonl"
SYNTH_DEV = ROOT.parent / "data" / "synth"
NASK_DIR = ROOT.parent / "data" / "dane" / "do_udostępnienia"
# Zbiory syntetyczne: ziarno -> konfiguracja generatora. 1 to dane z repo (6 operatorów × 2 kampanie × 3 warianty, braki 25%).
# Role: ziarna 1–10 to dev (2–4 diagnoza, 5–7 decyzja o korekcie, 8–10 potwierdzenie korekty); 11–13 to test, nigdy niewidziany.
DEV_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
TEST_SEEDS = (11, 12, 13)
SYNTH_CFG = {2: dict(n_operators=8, campaigns_per_op=3, variants=3, missing_rate=0.25),
             3: dict(n_operators=6, campaigns_per_op=2, variants=4, missing_rate=0.5),
             4: dict(n_operators=10, campaigns_per_op=2, variants=3, missing_rate=0.25),
             5: dict(n_operators=7, campaigns_per_op=3, variants=3, missing_rate=0.3),
             6: dict(n_operators=5, campaigns_per_op=3, variants=5, missing_rate=0.4),
             7: dict(n_operators=9, campaigns_per_op=2, variants=4, missing_rate=0.2),
             8: dict(n_operators=6, campaigns_per_op=3, variants=4, missing_rate=0.35),
             9: dict(n_operators=8, campaigns_per_op=2, variants=5, missing_rate=0.3),
             10: dict(n_operators=7, campaigns_per_op=2, variants=3, missing_rate=0.45),
             11: dict(n_operators=7, campaigns_per_op=3, variants=4, missing_rate=0.3),
             12: dict(n_operators=9, campaigns_per_op=2, variants=4, missing_rate=0.4),
             13: dict(n_operators=6, campaigns_per_op=2, variants=5, missing_rate=0.25)}
# Rodzina 2: syntetyka v2 (szum jak w prawdziwym HAR, embsim/synth2.py). Dev 21–29 (27–29 posłużyły do wyboru trybów), test 30–32 (nowy).
DEV_SEEDS2 = (21, 22, 23, 24, 25, 26, 27, 28, 29)
TEST_SEEDS2 = (30, 31, 32, 33, 34, 35)               # 30–32 widziane przy wyborze trybów; 33–35 nowe (potwierdzenie)
SYNTH2_CFG = {21: dict(n_operators=6, campaigns_per_op=2, variants=3, missing_rate=0.25),
              22: dict(n_operators=8, campaigns_per_op=3, variants=3, missing_rate=0.25),
              23: dict(n_operators=6, campaigns_per_op=2, variants=4, missing_rate=0.4),
              24: dict(n_operators=10, campaigns_per_op=2, variants=3, missing_rate=0.25),
              25: dict(n_operators=7, campaigns_per_op=3, variants=3, missing_rate=0.3),
              26: dict(n_operators=5, campaigns_per_op=3, variants=5, missing_rate=0.4),
              27: dict(n_operators=7, campaigns_per_op=3, variants=4, missing_rate=0.3),
              28: dict(n_operators=9, campaigns_per_op=2, variants=4, missing_rate=0.4),
              29: dict(n_operators=6, campaigns_per_op=2, variants=5, missing_rate=0.25),
              30: dict(n_operators=7, campaigns_per_op=3, variants=4, missing_rate=0.35),
              31: dict(n_operators=8, campaigns_per_op=2, variants=5, missing_rate=0.3),
              32: dict(n_operators=6, campaigns_per_op=3, variants=3, missing_rate=0.45),
              33: dict(n_operators=7, campaigns_per_op=2, variants=4, missing_rate=0.3),
              34: dict(n_operators=9, campaigns_per_op=3, variants=3, missing_rate=0.35),
              35: dict(n_operators=6, campaigns_per_op=2, variants=5, missing_rate=0.4)}
LEVELS = ("campaign", "operator")


@dataclass
class Config:
    model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    weights_campaign: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    weights_operator: dict = field(default_factory=lambda: {k: (0.0 if k == "text" else 1.0) for k in DEFAULT_WEIGHTS})
    rotating: list = field(default_factory=lambda: sorted(ROTATING))
    adjust_levels: list = field(default_factory=list)  # poziomy z korektą wyniku o dostępność dowodu (score.py)
    lexical: bool = False                              # kanał leksykalny text_lex (TF-IDF znaków) na poziomie kampanii
    trace_mode: str = "jaccard"                        # miara kanałów śladów: jaccard | contain | overlap (zob. score.Corpus)
    combine: str = "mean"                              # łączenie kanałów: mean | noisy_or
    embed_fix: str = "none"                            # korekta embeddingów tekstu: none | center | abtt1 (PCA korpusu, bez etykiet)
    trace_mode_operator: str | None = None             # miara śladów dla poziomu operatora (None = jak trace_mode)
    hub_frac: float | None = None                      # limit częstości śladów: ignoruj ślad obecny w > hub_frac galerii (score.Corpus)
    hub_abs: int | None = None                         # ... albo w > hub_abs materiałach
    op_rare_df: int | None = None                      # decyzja „operator” tylko przy wspólnym śladzie obecnym w <= tylu materiałach galerii
    thresholds: dict = field(default_factory=dict)   # {"campaign": t, "operator": t}, wypełnia calibrate

    def __post_init__(self):
        if self.lexical and "text_lex" not in self.weights_campaign:
            self.weights_campaign = dict(LEX_WEIGHTS)
    e_ref: dict = field(default_factory=dict)        # {"campaign": e, "operator": e}: dostępność dowodu przy pełnych danych (dev)

    def fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items() if k not in ("thresholds", "e_ref")}
        for k, default in (("trace_mode", "jaccard"), ("combine", "mean"), ("embed_fix", "none"), ("trace_mode_operator", None), ("hub_frac", None), ("hub_abs", None), ("op_rare_df", None)):   # wsteczna zgodność odcisków zamrożonych konfiguracji
            if core.get(k) == default:
                core.pop(k, None)
        return hashlib.sha1(json.dumps(core, sort_keys=True).encode()).hexdigest()[:10]


@dataclass
class Dataset:
    name: str
    role: str                                         # dev | test | final
    cases: list[Case]
    labels: dict[str, list]                           # poziom -> etykiety (None = bez grupy)
    note: str = ""


# --------------------------------------------------------------------------------------------------------------------
# zbiory


def _synth(name: str, role: str, d: Path) -> Dataset:
    truth = json.loads((d / "prawda.json").read_text())
    ids = sorted(truth)
    neg = lambda v: None if str(v).startswith("neg:") else v
    return Dataset(name, role, [load_case(d / i) for i in ids],
                   {"campaign": [neg(truth[i]["kampania"]) for i in ids], "operator": [neg(truth[i]["operator"]) for i in ids]},
                   "syntetyk z prawdą generatora (kampania, operator); negatywy bez grupy")


def synth_seed(seed: int) -> Dataset:
    role = "dev" if seed in DEV_SEEDS else "test"
    if seed == 1:
        return _synth("synth:1", role, SYNTH_DEV)
    d = ART / f"synth_seed{seed}"
    if not (d / "prawda.json").exists():
        from fejki.demo.synth_cases import generate

        d.mkdir(parents=True, exist_ok=True)
        generate(d, seed=seed, **SYNTH_CFG[seed])
    return _synth(f"synth:{seed}", role, d)


def synth2_seed(seed: int) -> Dataset:
    role = "dev" if seed in DEV_SEEDS2 else "test"
    d = ART / f"synth2_seed{seed}"
    if not (d / "prawda.json").exists():
        from .synth2 import generate

        d.mkdir(parents=True, exist_ok=True)
        generate(d, seed=seed, **SYNTH2_CFG[seed])
    return _synth(f"synth2:{seed}", role, d)


def nask_final() -> Dataset:
    ids = sorted((p.name for p in NASK_DIR.iterdir() if p.is_dir()), key=lambda x: int(x))
    camp = {"1": "K1", "2": "K1", "48": "K2", "61": "K2"}
    net = {"1", "2", "3", "48", "61"}
    return Dataset("nask10", "final", [load_case(NASK_DIR / i) for i in ids],
                   {"campaign": [camp.get(i) for i in ids], "operator": ["S1" if i in net else None for i in ids]},
                   "UWAGA: prawda to nasze własne ustalenia (organizator nie podał etykiet); 10 przypadków, jedna sieć")


def datasets(final: bool, family: int = 1) -> list[Dataset]:
    out = [synth_seed(s) for s in DEV_SEEDS + TEST_SEEDS] if family == 1 else [synth2_seed(s) for s in DEV_SEEDS2 + TEST_SEEDS2]
    return out + ([nask_final()] if final else [])


# --------------------------------------------------------------------------------------------------------------------
# punktowanie


def vectors(cfg: Config, cases: list[Case]) -> np.ndarray:
    key = hashlib.sha1((cfg.model + "\0" + "\0".join(c.text for c in cases)).encode()).hexdigest()[:16]
    f = ART / "vec_cache" / f"{key}.npy"
    if f.exists():
        return np.load(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    V = text_vectors(cfg.model, [c.text or " " for c in cases])
    np.save(f, V)
    return V


def corpus(cfg: Config, lv: str, cases: list[Case], V) -> Corpus:
    w = cfg.weights_campaign if lv == "campaign" else cfg.weights_operator
    ref = cfg.e_ref.get(lv) if lv in cfg.adjust_levels else None
    tm = (cfg.trace_mode_operator or cfg.trace_mode) if lv == "operator" else cfg.trace_mode
    return Corpus(copy.deepcopy(cases), V, w, rotating=set(cfg.rotating), adjust_ref=ref, trace_mode=tm,
                  combine=cfg.combine, embed_fix=cfg.embed_fix, hub_frac=cfg.hub_frac, hub_abs=cfg.hub_abs)


def score_matrices(cfg: Config, cases: list[Case], V: np.ndarray | None) -> dict[str, np.ndarray]:
    return {lv: corpus(cfg, lv, cases, V).matrix()[0] for lv in LEVELS}


def median_availability(cfg: Config, lv: str, cases: list[Case], V) -> float:
    c = corpus(cfg, lv, cases, V)
    n = len(c.cases)
    return float(np.median([c.availability(c.cases[i], c.cases[j]) for i in range(n) for j in range(i + 1, n)]))


def scenarios(ds: Dataset, V: np.ndarray):
    """(nazwa, przypadki, wektory, etykiety): odporność na braki danych i duplikaty."""
    yield "baza", ds.cases, V, ds.labels

    def strip(chs, text=False):
        cs = copy.deepcopy(ds.cases)
        for c in cs:
            for ch in chs:
                c.sets.pop(ch, None)
        return cs

    # brak HAR: znikają ślady ruchu; brak HTML: znika tekst i piksel; brak tekstu: sam kanał tekstowy
    yield "bez_HAR", strip(("kit", "scheme", "host")), V, ds.labels
    cs = strip(("pixel",))
    for c in cs:
        c.text = ""                                   # brak HTML: znika tekst (także dla kanału leksykalnego) i piksel
    yield "bez_HTML", cs, None, ds.labels
    rng = np.random.default_rng(0)
    dup = rng.choice(len(ds.cases), size=max(2, len(ds.cases) // 5), replace=False)
    cs = ds.cases + [copy.deepcopy(ds.cases[i]) for i in dup]
    lab = {lv: ds.labels[lv] + [ds.labels[lv][i] for i in dup] for lv in LEVELS}
    yield "duplikaty+20%", cs, np.vstack([V, V[dup]]), lab


SHOW = ("AUC", "AP", "ARI", "B3_F", "top1", "znany_vs_nowy_AUC", "błędnie_połączone")


def run_dataset(cfg: Config, ds: Dataset, full: bool = True) -> dict:
    V = vectors(cfg, ds.cases)
    res = {}
    for name, cs, vv, lab in (scenarios(ds, V) if full else [("baza", ds.cases, V, ds.labels)]):
        M = score_matrices(cfg, cs, vv)
        res[name] = {lv: evaluate_level(M[lv], lab[lv], cfg.thresholds.get(lv, 0.5)) for lv in LEVELS}
    return res


def fmt(res: dict, ds: Dataset) -> str:
    lines = [f"\n### {ds.name} [{ds.role}]  przypadków={len(ds.cases)}  {ds.note}"]
    for lv in LEVELS:
        lines.append(f"  poziom: {lv}")
        lines.append("    " + f"{'scenariusz':<16}" + "".join(f"{k:>16}" for k in SHOW))
        for sc, r in res.items():
            m = r[lv]
            lines.append("    " + f"{sc:<16}" + "".join(f"{m.get(k, float('nan')):>16.3f}" for k in SHOW))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------------------
# polecenia


FROZEN_DIR = ROOT / "config" / "embsim"     # zamrożone konfiguracje ŚLEDZONE w repo (artifacts/ jest w .gitignore)


def frozen_path(name: str) -> Path:
    """Lokalna (świeżo skalibrowana) konfiguracja ma pierwszeństwo; w czystym klonie czytamy tę z repo (config/embsim)."""
    local = ART / f"frozen_{name}.json"
    return local if local.exists() else FROZEN_DIR / f"frozen_{name}.json"


def calibrate(name: str, adjust_levels: list, lexical: bool = False, family: int = 1, trace_mode: str = "jaccard",
              combine: str = "mean", embed_fix: str = "none", trace_operator: str | None = None, hub_frac: float | None = None,
              hub_abs: int | None = None) -> None:
    """Progi i e_ref dobierane na PULI dev (rodzina 1: ziarna 1–10; rodzina 2: 21–29); test i final nie są używane."""
    cfg = Config(adjust_levels=adjust_levels, lexical=lexical, trace_mode=trace_mode, combine=combine, embed_fix=embed_fix,
                 trace_mode_operator=trace_operator, hub_frac=hub_frac, hub_abs=hub_abs)
    dev = [d for d in datasets(final=False, family=family) if d.role == "dev"]
    prep = [(d, d.cases, vectors(cfg, d.cases)) for d in dev]
    for lv in adjust_levels:
        cfg.e_ref[lv] = float(np.median([median_availability(cfg, lv, cs, V) for _, cs, V in prep]))
    mats = [(d, score_matrices(cfg, cs, V)) for d, cs, V in prep]
    # siatka do 0,99: konfiguracje z noisy-OR / nakładaniem kompresują wyniki blisko 1 i optimum bywa za 0,95
    grid = sorted({round(float(x), 2) for x in np.arange(0.05, 0.96, 0.05)} | {round(float(x), 2) for x in np.arange(0.96, 1.0, 0.01)})
    for lv in LEVELS:
        ari = {t: float(np.mean([evaluate_level(M[lv], d.labels[lv], t)["ARI"] for d, M in mats])) for t in grid}
        best = max(ari.values())
        plateau = [t for t in grid if ari[t] >= best - 0.02]
        cfg.thresholds[lv] = float(np.median(plateau))     # środek plateau, nie pojedynczy szczyt
        print(f"[{name}] {lv}: średnie ARI na dev={best:.3f}, plateau {plateau[0]}–{plateau[-1]} -> próg {cfg.thresholds[lv]}"
              + (f", e_ref={cfg.e_ref[lv]:.2f}" if lv in adjust_levels else ""))
    ART.mkdir(parents=True, exist_ok=True)
    # zapis zawsze lokalnie; aby konfigurację udostępnić zespołowi, skopiuj plik do code/config/embsim/ i zacommituj
    (ART / f"frozen_{name}.json").write_text(json.dumps({"config": asdict(cfg), "fingerprint": cfg.fingerprint(), "family": family,
                                             "dev": list(DEV_SEEDS if family == 1 else DEV_SEEDS2),
                                             "at": time.strftime("%F %T")}, ensure_ascii=False, indent=1))
    print(f"[{name}] zamrożono, odcisk {cfg.fingerprint()}")


def load_frozen(name: str, force: bool = False) -> tuple[Config, dict]:
    f = frozen_path(name)
    if not f.exists():
        raise SystemExit(f"brak zamrożonej konfiguracji '{name}': najpierw `calibrate --name {name}` (na dev)")
    fr = json.loads(f.read_text())
    cfg = Config(**fr["config"])
    now = Config(adjust_levels=cfg.adjust_levels, lexical=cfg.lexical, trace_mode=cfg.trace_mode, combine=cfg.combine,
                 embed_fix=cfg.embed_fix, trace_mode_operator=cfg.trace_mode_operator, hub_frac=cfg.hub_frac, hub_abs=cfg.hub_abs, op_rare_df=cfg.op_rare_df)
    if now.fingerprint() != fr["fingerprint"] and not force:
        raise SystemExit("konfiguracja (model/wagi/rotujące/korekta) zmieniona po zamrożeniu: uruchom `calibrate` ponownie na dev; "
                         "wyniki na zbiorach test z poprzedniej wersji nie są już porównywalne (--force pomija to zabezpieczenie)")
    return cfg, fr


def run(name: str, final: bool, force: bool) -> None:
    cfg, fr = load_frozen(name, force)
    print(f"[{name}] konfiguracja {fr['fingerprint']} ({fr['at']}), progi {cfg.thresholds}, e_ref {cfg.e_ref}, korekta dla {cfg.adjust_levels}")
    hist = [json.loads(l) for l in HISTORY.open()] if HISTORY.exists() else []
    seen = sum(1 for h in hist if h["fingerprint"] == fr["fingerprint"])
    report = {}
    for ds in datasets(final, fr.get("family", 1)):
        res = run_dataset(cfg, ds)
        report[ds.name] = {"role": ds.role, "results": res}
        print(fmt(res, ds))
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a") as f:
        f.write(json.dumps({"at": time.strftime("%F %T"), "fingerprint": fr["fingerprint"], "name": name, "final": final}) + "\n")
    print(f"\nuwaga: to {seen + 1}. przebieg na zbiorach test dla konfiguracji {fr['fingerprint']}" + ("; final odkryty" if final else ""))
    (ART / f"report_{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float))


def compare(force: bool, names: tuple = ("adj", "lex"), family: int = 1, role: str = "test") -> None:
    """Zestawienie dwóch zamrożonych konfiguracji na zbiorach TEST; progi każdej dobrane na tej samej puli dev."""
    cfgs = {n: load_frozen(n, force)[0] for n in names}
    n1, n2 = names
    keys = ("AUC", "ARI", "B3_F", "top1", "błędnie_połączone")
    print(f"kolumny: {n1} / {n2}")
    print(f"{'zbiór':<10}{'poziom':<10}{'scenariusz':<14}" + "".join(f"{k:>22}" for k in keys))
    sums = {n: {lv: {k: [] for k in keys} for lv in LEVELS} for n in cfgs}
    for ds in (d for d in datasets(False, family) if d.role == role):
        res = {n: run_dataset(c, ds) for n, c in cfgs.items()}
        for lv in LEVELS:
            for sc in res[n1]:
                row = "".join(f"{res[n1][sc][lv][k]:>10.3f}/{res[n2][sc][lv][k]:<10.3f}" for k in keys)
                print(f"{ds.name:<10}{lv:<10}{sc:<14}{row}")
                for n in cfgs:
                    for k in keys:
                        sums[n][lv][k].append((sc, res[n][sc][lv][k]))
    print(f"\nŚREDNIA po zbiorach test ({n1} / {n2})")
    for lv in LEVELS:
        for sc in ("baza", "bez_HAR", "bez_HTML", "duplikaty+20%"):
            row = "".join(f"{np.mean([v for s_, v in sums[n1][lv][k] if s_ == sc]):>10.3f}/"
                          f"{np.mean([v for s_, v in sums[n2][lv][k] if s_ == sc]):<10.3f}" for k in keys)
            print(f"{'średnia':<10}{lv:<10}{sc:<14}{row}")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a") as f:
        f.write(json.dumps({"at": time.strftime("%F %T"), "fingerprint": "compare:" + "+".join(names), "name": "compare", "final": False}) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["calibrate", "run", "compare"])
    ap.add_argument("--name", default="adj", help="nazwa pliku frozen_<name>.json; base/adj/lex mają dawne znaczenie, gdy nie podano flag")
    ap.add_argument("--names", nargs=2, default=["adj", "lex"], help="compare: dwie konfiguracje do porównania")
    ap.add_argument("--family", type=int, default=1, choices=[1, 2], help="1 = syntetyka v1, 2 = syntetyka v2 (szum jak w prawdziwym HAR)")
    ap.add_argument("--role", default="test", choices=["dev", "test"], help="compare: na którym zbiorze porównywać")
    ap.add_argument("--adjust", action="store_true", help="korekta o dostępność dowodu dla poziomu kampanii")
    ap.add_argument("--lexical", action="store_true", help="kanał leksykalny text_lex")
    ap.add_argument("--trace", default="jaccard", choices=["jaccard", "contain", "overlap"])
    ap.add_argument("--combine", default="mean", choices=["mean", "noisy_or"])
    ap.add_argument("--trace-operator", default=None, choices=["jaccard", "contain", "overlap"], help="miara śladów tylko dla poziomu operatora")
    ap.add_argument("--hub-frac", type=float, default=None, help="limit częstości śladów: ułamek galerii")
    ap.add_argument("--hub-abs", type=int, default=None, help="limit częstości śladów: liczba materiałów")
    ap.add_argument("--embed-fix", default="none", choices=["none", "center", "abtt1"], help="korekta PCA embeddingów tekstu")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "calibrate":
        legacy = {"base": ([], False), "adj": (["campaign"], False), "lex": (["campaign"], True)}
        explicit = a.adjust or a.lexical or a.trace != "jaccard" or a.combine != "mean" or a.family != 1 or a.embed_fix != "none" or a.trace_operator or a.hub_frac or a.hub_abs
        adj, lex = legacy[a.name] if (a.name in legacy and not explicit) else (["campaign"] if a.adjust else [], a.lexical)
        calibrate(a.name, adj, lex, a.family, a.trace, a.combine, a.embed_fix, a.trace_operator, a.hub_frac, a.hub_abs)
    elif a.cmd == "run":
        run(a.name, a.final, a.force)
    else:
        compare(a.force, tuple(a.names), a.family, a.role)


if __name__ == "__main__":
    main()
