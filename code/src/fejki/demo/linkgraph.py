"""Czytelny graf powiązań: materiał → konkretny wspólny ślad → materiał, każda sieć w ramce, kampanie w ramkach wewnątrz.

Zamiast linii „0.88” między kulkami rysujemy to, CO łączy materiały (piksel, domenę, ścieżkę zestawu, te same obrazy, tekst),
i to samo opisujemy zdaniami. Słabe przesłanki (tematyka, osoba w wielu materiałach, konflikty) pomijamy, bo niczego nie dowodzą;
zostają w tabeli przesłanek pod rysunkiem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from fejki.demo.similar import Campaign, Pair

MIN_WEIGHT = 0.3  # poniżej tego przesłanka jest tłem (np. wspólna tematyka), nie dowodem

# kod przesłanki → (krótka nazwa, rodzaj): rodzaj „treść” = ten sam przekaz, „infra” = ten sam operator / zaplecze
KIND: dict[str, tuple[str, str]] = {
    "same_landing": ("ta sama domena", "infra"),
    "shared_ad_id": ("ta sama reklama Meta", "infra"),
    "shared_pixel": ("ten sam piksel Meta", "infra"),
    "shared_tracker": ("ten sam identyfikator śledzenia", "infra"),
    "shared_account": ("ten sam oznacznik konta", "infra"),
    "shared_contact": ("ten sam kontakt", "infra"),
    "shared_advertiser": ("ten sam reklamodawca", "infra"),
    "same_scheme": ("ten sam schemat parametrów adresu", "infra"),
    "same_path_template": ("ta sama ścieżka zestawu", "infra"),
    "shared_prefix": ("ten sam katalog zestawu", "infra"),
    "shared_host": ("ta sama nietypowa usługa", "infra"),
    "shared_redirect": ("to samo przekierowanie", "infra"),
    "infra": ("wspólna infrastruktura", "infra"),
    "dom": ("ta sama struktura strony", "infra"),
    "text": ("ten sam tekst", "treść"),
    "semantic": ("ten sam sens tekstu", "treść"),
    "visual": ("podobny wygląd", "treść"),
    "same_logo": ("ta sama podrobiona marka", "treść"),
    "same_title": ("ten sam tytuł", "treść"),
    "person": ("ta sama osoba", "treść"),
    "same_product": ("ten sam produkt", "treść"),
    "img_shot": ("podobny zrzut", "treść"),
    "img_asset": ("te same obrazy", "treść"),
}
STYLE = {"infra": ("#dbeafe", "#1d4ed8"), "treść": ("#fee2e2", "#b91c1c")}
NET_FILL = ["#f8fafc", "#fffbeb", "#f0fdf4", "#faf5ff", "#fdf2f8", "#ecfeff"]


@dataclass
class Trace:
    code: str
    value: str
    members: set[str] = field(default_factory=set)
    weight: float = 0.0

    @property
    def name(self) -> str:
        return KIND.get(self.code, (self.code, "infra"))[0]

    @property
    def kind(self) -> str:
        return KIND.get(self.code, (self.code, "infra"))[1]


def _value(code: str, reason: str) -> str:
    """Sama wartość śladu z opisu przesłanki, krótko (to, co ma się zmieścić w owalu)."""
    if code == "same_scheme":
        m = re.search(r"długości: ([^)]*)\)", reason)
        return (m.group(1) if m else reason)[:60]
    if code == "text":
        m = re.search(r"podobieństwo ([0-9.]+)\); wspólne: (.*)", reason)
        return f"zgodność {float(m.group(1)):.0%}" if m else reason[:50]
    if code == "img_asset":
        m = re.search(r"\((\d+), np\. ([^)]*)\)", reason)
        return f"{m.group(1)} plików, np. {m.group(2)[:30]}" if m else reason[:50]
    if code == "shared_pixel":
        return reason.split(": ", 1)[-1].split(" ")[0]
    if code == "person":
        return reason.split(": ", 1)[-1].split(" (")[0]
    v = reason.split(": ", 1)[-1] if ": " in reason else reason
    return v.strip("„”")  # pełna wartość jest kluczem śladu; skracamy dopiero przy rysowaniu (_short)


def _short(v: str, n: int = 42) -> str:
    """Skrót ze środka: zostaje początek i koniec (w ścieżkach zestawu oba coś mówią)."""
    if len(v) <= n:
        return v
    return v[: n - 13] + "…" + v[-12:] if v.startswith("/") else v[: n - 1].rstrip() + "…"


def traces(pairs: list[Pair], min_weight: float = MIN_WEIGHT) -> list[Trace]:
    """Wspólne ślady z przesłanek par; ten sam ślad w kilku parach = jeden węzeł łączący wszystkie te materiały."""
    out: dict[tuple[str, str], Trace] = {}
    for p in pairs:
        for e in p.evidence:
            if e.weight < min_weight or e.code in ("topic", "conflict"):
                continue
            v = _value(e.code, e.reason)
            key = (e.code, v) if e.code not in ("text", "img_asset", "img_shot", "semantic", "visual", "dom") else (e.code, f"{p.a}~{p.b}")
            t = out.setdefault(key, Trace(e.code, v))
            t.members |= {p.a, p.b}
            t.weight = max(t.weight, e.weight)
    return sorted(out.values(), key=lambda t: (-len(t.members), -t.weight))


def _bundle(ts: list[Trace]) -> list[tuple[str, str, list[str], set[str], float]]:
    """Ślady tego samego rodzaju łączące te same materiały → jeden owal („2 × ta sama ścieżka zestawu”)."""
    b: dict[tuple[str, frozenset], list[Trace]] = {}
    for t in ts:
        b.setdefault((t.code, frozenset(t.members)), []).append(t)
    rows = [(g[0].name, g[0].kind, [t.value for t in g], set(ms), max(t.weight for t in g)) for (_, ms), g in b.items()]
    return sorted(rows, key=lambda r: (-len(r[3]), -r[4]))


def _code(v: str) -> str:
    return "`" + _short(v, 60).replace("`", "'") + "`"


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:]


def _esc(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def summary(net: Campaign, camps: list[Campaign], ts: list[Trace], label: dict[str, str]) -> list[str]:
    """Zdania: co łączy materiały wewnątrz każdej kampanii i co skleja kampanie w sieć."""
    mem = set(net.members)
    cs = [c for c in camps if set(c.members) <= mem]
    camp_of = {m: c.id for c in cs for m in c.members}
    lines = []
    for c in cs:
        if len(c.members) < 2:
            continue
        inside = [t for t in ts if t.members <= set(c.members)]
        what = "; ".join(f"{_lc(n)} ({', '.join(_code(x) for x in v[:2])})" for n, _, v, _, _ in _bundle(inside)[:4])
        lines.append(f"**{', '.join(c.members)}** to jedna kampania (ten sam przekaz): {what or 'podobna treść'}.")
    cross = [t for t in ts if t.members <= mem and len({camp_of.get(m, m) for m in t.members}) > 1]
    for n, _, vals, ms, _ in _bundle(cross)[:5]:
        lines.append(f"**{', '.join(sorted(ms))}** łączy {_lc(n)}: {', '.join(_code(x) for x in vals[:2])}.")
    if not lines:
        lines.append("Powiązanie wynika z podobieństwa treści (szczegóły w tabeli).")
    return lines


def _html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def boxes(ts: list[Trace]) -> list[tuple[set[str], list[Trace]]]:
    """Jedna ramka na zestaw materiałów: wszystkie ślady, które łączą dokładnie te materiały."""
    b: dict[frozenset, list[Trace]] = {}
    for t in ts:
        b.setdefault(frozenset(t.members), []).append(t)
    return sorted(((set(ms), sorted(g, key=lambda t: -t.weight)) for ms, g in b.items()), key=lambda r: (-len(r[0]), -r[1][0].weight))


def _box_label(g: list[Trace], max_lines: int = 5) -> str:
    rows = []
    for name, kind, vals, _, _ in _bundle(g)[:max_lines]:
        ink = STYLE[kind][1]
        head = f"{len(vals)} × {_lc(name)}" if len(vals) > 1 else _lc(name)
        rows.append(f'<tr><td align="left"><font color="{ink}">● </font>{_html(head)}: '
                    f'<font color="#475569">{_html(_short(vals[0], 40))}</font></td></tr>')
    more = len(_bundle(g)) - max_lines
    if more > 0:
        rows.append(f'<tr><td align="left"><font color="#64748b">(+{more} w tabeli)</font></td></tr>')
    return '<<table border="0" cellspacing="0" cellpadding="2">' + "".join(rows) + "</table>>"


def dot(materials: list[str], nets: list[Campaign], camps: list[Campaign], pairs: list[Pair], label: dict[str, str],
        highlight: str | None = None) -> str:
    """DOT: sieci (ramki) z kampaniami (przerywane ramki wewnątrz), materiały jako karteczki, a obok nich ramki
    „co łączy te materiały” (jedna na zestaw materiałów). Ramka przekazu (czerwona) siedzi w kampanii, ramki zaplecza
    (niebieskie, łączące kampanie) w sieci. Materiały bez powiązań nie są rysowane (lista obok), bo tylko zaśmiecałyby obraz.
    """
    shown = set(materials)
    ts = [t for t in traces(pairs) if t.members <= shown]
    linked = set().union(*(t.members for t in ts)) if ts else set()
    lines = ['graph G {', 'rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.7; newrank=true;',
             'node [fontname="Helvetica", fontsize=11]; edge [color="#64748b"];']
    for k, net in enumerate(n for n in nets if set(n.members) & linked):
        mem = set(net.members) & shown
        lines.append(f'subgraph cluster_{k} {{ label="sieć {_esc(net.id)} · {len(mem)} materiałów"; labeljust=l; fontsize=12; '
                     f'style="rounded,filled"; fillcolor="{NET_FILL[k % len(NET_FILL)]}"; color="#cbd5e1";')
        bx = boxes([t for t in ts if t.members <= mem])
        placed: set[int] = set()
        for j, c in enumerate(c for c in camps if set(c.members) <= mem):
            many = len(c.members) > 1
            if many:
                lines.append(f'subgraph cluster_{k}_{j} {{ label="kampania {_esc(c.id)}: ten sam przekaz"; labeljust=l; fontsize=10; '
                             'style="rounded,dashed"; color="#ef4444";')
            for m in c.members:
                hl = ', penwidth=3, color="#111827"' if m == highlight else ""
                lines.append(f'"m:{_esc(m)}" [label="{_esc(m)}\\n{_esc(label.get(m, ""))}", shape=note, style=filled, '
                             f'fillcolor="white"{hl}];')
            if many:
                for i, (ms, g) in enumerate(bx):
                    if ms <= set(c.members):
                        lines.append(f'"b{k}_{i}" [label={_box_label(g)}, shape=box, style="rounded,filled", fillcolor="#fff1f2", '
                                     'color="#fca5a5", fontsize=10];')
                        placed.add(i)
                lines.append("}")
        for i, (ms, g) in enumerate(bx):
            if i not in placed:
                lines.append(f'"b{k}_{i}" [label={_box_label(g)}, shape=box, style="rounded,filled", fillcolor="#eff6ff", '
                             'color="#93c5fd", fontsize=10];')
            for m in sorted(ms):
                lines.append(f'"m:{_esc(m)}" -- "b{k}_{i}" [penwidth={1 + 2 * g[0].weight:.1f}];')
        lines.append("}")
    lines.append("}")
    return "\n".join(lines)


def lonely(materials: list[str], pairs: list[Pair]) -> list[str]:
    ts = traces(pairs)
    linked = set().union(*(t.members for t in ts)) if ts else set()
    return [m for m in materials if m not in linked]
