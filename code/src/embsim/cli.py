from __future__ import annotations

from pathlib import Path

import numpy as np
import typer

from .embed import DEFAULT_MODEL, DEFAULT_PROMPT, Embedder
from .material import load_case, load_cases
from .similarity import CHANNELS, case_vectors, clusters, sim_matrix

app = typer.Typer(help="Kolekcjoner Fejków v2: embeddingi multimodalne + podobieństwo", no_args_is_help=True)
MODEL = typer.Option(DEFAULT_MODEL, "--model")
PROMPT = typer.Option(DEFAULT_PROMPT, "--prompt")


def _table(ids: list[str], S: np.ndarray) -> str:
    w = max(max(len(i) for i in ids), 4) + 2
    rows = ["".join([" " * w] + [f"{i:>{w}}" for i in ids])]
    for i, r in zip(ids, S):
        rows.append(f"{i:<{w}}" + "".join(f"{'-':>{w}}" if np.isnan(x) else f"{x:>{w}.2f}" for x in r))
    return "\n".join(rows)


@app.command()
def matrix(root: Path, channel: str = "both", threshold: float = 0.8, model: str = MODEL, prompt: str = PROMPT):
    """Macierz podobieństw wszystkich przypadków z folderu `root` i grupy powyżej progu."""
    assert channel in CHANNELS, f"kanał: {CHANNELS}"
    emb = Embedder(model, prompt)
    cases = load_cases(root)
    vecs = [case_vectors(emb, m)[channel] for m in cases]
    ids = [m.id for m in cases]
    S = sim_matrix(vecs)
    typer.echo(_table(ids, S))
    typer.echo(f"\ngrupy przy progu {threshold}:")
    for g in clusters(np.nan_to_num(S, nan=-1), threshold):
        typer.echo("  " + ", ".join(ids[i] for i in g))


@app.command()
def similar(case: Path, root: Path, channel: str = "both", top: int = 5, model: str = MODEL, prompt: str = PROMPT):
    """Najbliższe przypadki z `root` dla nowego materiału `case`."""
    emb = Embedder(model, prompt)
    q = case_vectors(emb, load_case(case))[channel]
    rows = [(m.id, case_vectors(emb, m)[channel]) for m in load_cases(root) if m.id != case.name]
    scored = sorted(((float(q @ v), i) for i, v in rows if v is not None and q is not None), reverse=True)
    for s, i in scored[:top]:
        typer.echo(f"{s:.3f}  {i}")


if __name__ == "__main__":
    app()
