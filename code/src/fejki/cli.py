"""CLI: one command per phase."""
from __future__ import annotations

import os
from datetime import UTC

import typer

from .config import load_config, path, pick_device

app = typer.Typer(help="Kolekcjoner Fejków: wykrywanie kampanii reklam oszukańczych", no_args_is_help=True)
ingest_app = typer.Typer(help="Pobieranie danych")
eval_app = typer.Typer(help="Eksperymenty")
graph_app = typer.Typer(help="Graf kampanii")
app.add_typer(ingest_app, name="ingest")
app.add_typer(eval_app, name="eval")
infra_app = typer.Typer(help="Kanał infrastruktury (bierne dane o domenach)")
app.add_typer(graph_app, name="graph")
app.add_typer(infra_app, name="infra")

CFG = typer.Option("config/default.yaml", "--config")


def _con(cfg):
    from .db import connect

    return connect(path(cfg["db_path"]))


@ingest_app.command("jsonl")
def ingest_jsonl(file: str, config: str = CFG):
    from .db import upsert_ads
    from .ingest.jsonl import read_jsonl
    from .process.pipeline import enrich

    cfg = load_config(config)
    con = _con(cfg)
    n = upsert_ads(con, [enrich(a, cfg) for a in read_jsonl(file)])
    typer.echo(f"ingested {n} ads")


@ingest_app.command("meta")
def ingest_meta(countries: str = "PL", days: int = 30, queries: str = "config/queries.txt", config: str = CFG):
    from datetime import datetime

    from .db import upsert_ads
    from .ingest.meta_api import fetch, to_ad
    from .process.pipeline import enrich

    cfg = load_config(config)
    con = _con(cfg)
    now = datetime.now(UTC)
    for q in [l.strip() for l in open(queries) if l.strip()]:
        recs = fetch(q, tuple(countries.split(",")), days, cfg=cfg)
        typer.echo(f"{q}: {upsert_ads(con, [enrich(to_ad(r, now), cfg) for r in recs])} ads")


@ingest_app.command("csv")
def ingest_csv(file: str, source: str = "meta", config: str = CFG):
    """Ad Library CSV export (columns matched loosely)."""
    from .db import upsert_ads
    from .ingest.csv_export import read_csv
    from .process.pipeline import enrich

    cfg = load_config(config)
    n = upsert_ads(_con(cfg), [enrich(a, cfg) for a in read_csv(file, source)])
    typer.echo(f"ingested {n} ads")


@ingest_app.command("google")
def ingest_google(region: str = "PL", days: int = 30, limit: int = 5000, config: str = CFG):
    """Google Ads Transparency Center via BigQuery (needs GCP credentials)."""
    from datetime import datetime

    from .db import upsert_ads
    from .ingest.bigquery_google import fetch, row_to_ad
    from .process.pipeline import enrich

    cfg = load_config(config)
    now = datetime.now(UTC)
    rows = fetch(region, days, limit)
    n = upsert_ads(_con(cfg), [enrich(row_to_ad(r, now), cfg) for r in rows])
    typer.echo(f"ingested {n} ads (text is mostly empty for Google rows)")


@ingest_app.command("cert")
def ingest_cert(file: str = typer.Option("", help="local JSON instead of download"), config: str = CFG):
    from .ingest.cert import fetch_cert, load_cert_file, store_cert

    cfg = load_config(config)
    entries = load_cert_file(file) if file else fetch_cert()
    store_cert(_con(cfg), entries)
    typer.echo(f"stored {len(entries)} cert entries")


@app.command()
def synth(n_campaigns: int = 20, seed: int = 1, out: str = "data/fixtures", generator: str = typer.Option("rule", help="rule | llm (LLM_PROVIDER: ollama, deepseek, kimi, openai_compat, anthropic)"), config: str = CFG):
    from .synth.campaigns import write_fixtures

    s = load_config(config)["synth"]
    r = write_fixtures(out, seed, n_campaigns=n_campaigns, dev_fraction=s["dev_fraction"], variants=tuple(s["variants_per_campaign"]),
                       n_background=s["n_background"], n_controls=s["n_controls"], mu=s["cert_delay_lognormal"]["mu"], sigma=s["cert_delay_lognormal"]["sigma"], generator=generator)
    typer.echo(f"{r} (SYNTHETIC research data: fictional people, brands and reserved domains)")


@app.command()
def embed(model: str = "", split: str = "all", config: str = CFG):
    from .embed.encoder import embed_texts
    from .eval.experiments import load_ads

    cfg = load_config(config, {"encoder.name": model} if model else None)
    ads = load_ads(cfg)
    e = embed_texts([a.text_norm for a in ads], cfg)
    typer.echo(f"embedded {e.shape} on {pick_device(cfg['device'])}")


@app.command()
def erase(by: str = "topic", seed: int = 1, config: str = CFG):
    from .eval.experiments import build_ctx

    ctx = build_ctx(load_config(config), seed)
    typer.echo(f"removed rank per channel: {ctx.ranks}")


@app.command()
def cluster(method: str = "agglo", channel: str = "E1_leace_topic", seed: int = 1, config: str = CFG):
    from .eval.experiments import build_ctx, cluster_channel, eval_labels, pool

    ctx = build_ctx(load_config(config), seed)
    dev, test = pool(ctx, "dev"), pool(ctx, "test")
    lab, par = cluster_channel(ctx, channel, method, dev, test)
    r = eval_labels(ctx, test, lab, 200)
    typer.echo(f"{channel}/{method} {par}: P={r['P']:.3f} R={r['R']:.3f} F1={r['F1']:.3f} recall_cross_topic={r['recall_x']:.3f}")


@graph_app.command("build")
def graph_build(seed: int = 1, config: str = CFG):
    from .eval.experiments import build_ctx
    from .eval.report import e6

    ctx = build_ctx(load_config(config), seed)
    e6(ctx)  # builds cards and graph as part of the operational pipeline
    typer.echo("graph and cards written to artifacts/")


@eval_app.command("all")
def eval_all(seed: int = 1, fixtures: str = "data/fixtures", config: str = CFG):
    from .eval.experiments import run_all
    from .eval.report import write_report

    cfg = load_config(config, {"seed": seed})
    out = run_all(cfg, seed, fixtures)
    write_report(out)
    typer.echo(out["verdict"])
    typer.echo("artifacts/tables/REPORT.md")


@eval_app.command("one")
def eval_one(exp: str, seed: int = 1, config: str = CFG):
    from .eval import experiments as ex
    from .eval import report as rp

    ctx = ex.build_ctx(load_config(config, {"seed": seed}), seed)
    fn = {"E1": ex.e1, "E2": ex.e2, "E3": ex.e3, "E4": ex.e4, "E5": ex.e5, "E6": rp.e6, "E7": rp.e7}[exp.upper()]
    typer.echo(fn(ctx).round(3).to_string(index=False))


@app.command()
def replay(start: str = "", end: str = "", seed: int = 1, config: str = CFG):
    from .eval.experiments import build_ctx
    from .eval.report import e6

    ctx = build_ctx(load_config(config), seed)
    typer.echo(e6(ctx).T.to_string())


@app.command()
def comments(seed: int = 1, config: str = CFG):
    from .synth.comments import run_comment_demo

    typer.echo(run_comment_demo(load_config(config), seed).round(3).to_string(index=False))


@app.command("app")
def run_app():
    import subprocess
    import sys

    from .config import ROOT

    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "src/fejki/app/streamlit_app.py")])


if __name__ == "__main__":
    app()


demo_app = typer.Typer(help="Demonstrator: analiza materiałów i łączenie w kampanie")
app.add_typer(demo_app, name="demo")
DEFAULT_DATA = os.environ.get("FEJKI_DATA", "../data/dane/do_udostępnienia")


@demo_app.command("build")
def demo_build(data: str = typer.Argument(DEFAULT_DATA, help="folder z podfolderami-przypadkami"), no_ocr: bool = False,
               infra: bool = typer.Option(False, help="zbierz też bierne dane infrastruktury (DNS, RDAP, crt.sh); wymaga sieci")):
    """Buduje indeks materiałów ze zbioru przypadków (artifacts/demo/index.json)."""
    from pathlib import Path

    from .demo import store

    idx = store.build(Path(data), ocr=not no_ocr, progress=lambda k, n, d: typer.echo(f"[{k + 1}/{n}] {d}"))
    if infra:
        for e in store.collect_infra(idx):
            typer.echo(f"infra: {e}")
    typer.echo(f"zapisano {store.save(idx)} ({len(idx.materials)} materiałów)")


@demo_app.command("eval")
def demo_eval(thr: float = 0.7, data: str = DEFAULT_DATA, partial: bool = True):
    """Testy zachowania: pomiń-jeden i odporność na niepełne wejście."""
    from pathlib import Path

    import pandas as pd

    from .demo import store
    from .demo.evaluate import leave_one_out, partial_inputs

    idx = store.load()
    if not idx:
        raise typer.Exit("brak indeksu: uruchom `fejki demo build`")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 100)
    loo = leave_one_out(idx.materials, thr)
    typer.echo(loo.to_string(index=False))
    typer.echo(f"\nspójność kampanii {loo['kampania OK'].mean():.0%}, sieci {loo['sieć OK'].mean():.0%}")
    out = path("artifacts/demo"); out.mkdir(parents=True, exist_ok=True)
    loo.to_csv(out / "eval_leave_one_out.csv", index=False)
    if partial:
        pi = partial_inputs(store.case_dirs(Path(data)), idx.materials, thr)
        typer.echo("\n" + pi.to_string(index=False))
        pi.to_csv(out / "eval_partial_inputs.csv", index=False)


urlscan_app = typer.Typer(help="urlscan.io: gotowe publiczne skany jako zbiór treningowy/testowy (nie zlecamy nowych skanów)")
app.add_typer(urlscan_app, name="urlscan")
URLSCAN_DIR = os.environ.get("FEJKI_URLSCAN", "../data/urlscan")


def _load_env():
    """Wczytuje code/.env (np. URLSCAN_API_KEY), bez czytania konfiguracji YAML."""
    from dotenv import load_dotenv

    from .config import ROOT

    load_dotenv(ROOT / ".env")


@urlscan_app.command("search")
def urlscan_search(query: str, size: int = 10):
    """Podgląd wyników zapytania (bez zapisu)."""
    from .sources.urlscan import Client

    _load_env()
    j = Client().search(query, size=size)
    typer.echo(f"wszystkich: {j.get('total')}")
    for r in j.get("results", []):
        p = r.get("page", {})
        typer.echo(f"{r['task']['time'][:10]}  {p.get('domain', '')[:40]:40s} wiek dom.: {p.get('domainAgeDays', '?'):>4}  {(p.get('title') or '')[:70]}")


@urlscan_app.command("collect")
def urlscan_collect(pivots: str = "config/urlscan_pivots.yaml", out: str = URLSCAN_DIR, max_per_domain: int = 2,
                    no_screenshots: bool = False):
    """Zbiera skany dla pivotów z pliku YAML; każdy skan = folder przypadku, etykiety w labels.csv."""
    from pathlib import Path

    from .sources.urlscan import Client, collect, load_pivots

    _load_env()
    c = Client()
    typer.echo("tryb: " + ("z kluczem API (pełne wyniki i DOM)" if c.api_key else "bez klucza (metadane i zrzuty)"))
    rows = collect(c, load_pivots(Path(pivots)), Path(out), max_per_domain, not no_screenshots, log=typer.echo)
    typer.echo(f"razem przypadków: {len(rows)} → {out}")


@urlscan_app.command("eval")
def urlscan_eval(data: str = URLSCAN_DIR, thr: float = 0.7, no_ocr: bool = False):
    """Buduje osobny indeks ze skanów urlscan i ocenia grupowanie względem etykiet z pivotów."""
    import csv
    from pathlib import Path

    from .demo import store
    from .demo.evaluate import against_labels

    labels = {r["case_id"]: r for r in csv.DictReader((Path(data) / "labels.csv").open(encoding="utf-8"))}
    idx = store.build(Path(data), ocr=not no_ocr, progress=lambda k, n, d: typer.echo(f"[{k + 1}/{n}] {d}") if k % 25 == 0 else None)
    store.save(idx, path("artifacts/demo/urlscan_index.json"))
    res = against_labels(idx.materials, labels, thr)
    for level, r in res.items():
        typer.echo(f"{level}: B-cubed P {r['precision']} R {r['recall']} F1 {r['f1']} (n={r['n']}); "
                   f"negatywy doklejone do oszustw: {r['negatywy_doklejone_do_oszustw']}")


@demo_app.command("cards")
def demo_cards(thr: float = 0.7):
    """Karty kampanii (Markdown) i lista domen do weryfikacji (CSV) w artifacts/demo/cards/."""
    from .demo import store
    from .demo.cards import build_cards, card_markdown, domains_csv
    from .demo.similar import all_pairs, campaigns

    idx = store.load()
    if not idx:
        raise typer.Exit("brak indeksu: uruchom `fejki demo build`")
    infra = store.infra_records(idx) if idx.infra else None
    pairs = all_pairs(idx.materials, infra)
    cards = build_cards(idx.materials, pairs, campaigns(idx.materials, pairs, thr, "kampania"),
                        campaigns(idx.materials, pairs, thr, "sieć"), thr, infra)
    out = path("artifacts/demo/cards"); out.mkdir(parents=True, exist_ok=True)
    for c in cards:
        (out / f"{c.id}.md").write_text(card_markdown(c), encoding="utf-8")
    (out / "domeny_do_weryfikacji.csv").write_text(domains_csv(cards), encoding="utf-8")
    for c in cards:
        typer.echo(f"{c.id} [{', '.join(c.members)}] okno {c.window_start or '—'} → {c.window_end or '—'}; "
                   f"domen do weryfikacji: {len(c.domains_to_verify)}")
    typer.echo(f"zapisano {out}")


@demo_app.command("app")
def demo_run(port: int = 8501):
    """Uruchamia demonstrator w przeglądarce."""
    import subprocess
    import sys

    from .config import ROOT

    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "src/fejki/app/demo_app.py"), "--server.port", str(port)])


@infra_app.command("collect")
def infra_collect(file: str = typer.Argument(..., help="plik tekstowy z adresami URL"), refresh: bool = False, no_ct: bool = False):
    """Zbiera cechy domen biernie (DNS, ASN, RDAP, CT). Nie łączy się ze stronami oszustów."""
    from .infra.collect import collect_cached, load_links

    for dom, urls in load_links(open(file).read()).items():
        r = collect_cached(dom, urls, refresh=refresh, use_ct=not no_ct)
        typer.echo(f"{dom}: IP {','.join(r.a) or '-'} | NS {','.join(r.ns) or '-'} | rejestrator {r.rdap.registrar} | utw. {r.rdap.created} | bledy {r.errors or '-'}")


@infra_app.command("link")
def infra_link(file: str = typer.Argument(..., help="ten sam plik z URL-ami"), min_score: float = 0.5, config: str = CFG):
    """Łączy domeny regułami dowodowymi i wypisuje uzasadnienie każdej krawędzi."""
    import json

    from .infra.collect import collect_cached, load_links
    from .infra.link import graph_edges
    from .infra.link import link as do_link

    cfg = load_config(config)
    recs = [collect_cached(d, u) for d, u in load_links(open(file).read()).items()]
    links = do_link(recs, cfg.get("infra"), min_score)
    for li in links:
        typer.echo(f"{li.src} <-> {li.dst}  wynik {li.score}")
        for e in li.evidence:
            typer.echo(f"    [{e.weight:.2f}] {e.reason}")
    if not links:
        typer.echo("brak krawędzi powyżej progu")
    out = path("artifacts/infra"); out.mkdir(parents=True, exist_ok=True)
    (out / "links.json").write_text(json.dumps({"links": [li.model_dump() for li in links], "graph_edges": graph_edges(links)}, indent=1, ensure_ascii=False))
    typer.echo(f"zapisano {out / 'links.json'}")
