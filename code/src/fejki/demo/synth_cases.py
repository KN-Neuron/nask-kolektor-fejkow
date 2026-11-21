"""Generator SYNTETYCZNYCH przypadków w formacie organizatora (folder: zapis strony HTML + log HAR) z znaną prawdą.

Model: **operator** (zestaw stron, schemat parametrów TDS, piksel, styl domen, pula reklamodawców) prowadzi **kampanie** (narracja + osoba +
produkt); każda kampania ma kilka **wariantów** (inna domena, parafraza, losowe braki). Prawda: kampania i operator (sieć).
Trudne przypadki: (1) dwóch operatorów dzieli ten sam zestaw stron, ale nie piksel ani TDS; (2) ta sama narracja u różnych operatorów;
(3) negatywy: „legalne” strony z tymi samymi osobami i tematami.

Bezpieczeństwo: domeny wyłącznie `.example` i `.test`, brak działających linków, numerów ani prawdziwych identyfikatorów; osoby tylko
w tekście. Ograniczenie: syntetyka sprawdza, czy metoda odzyskuje to, co sami podłożyliśmy, nie czy prawdziwe kampanie tak wyglądają
(wyniki raportujemy osobno od danych prawdziwych).
"""
from __future__ import annotations

import json
import random
import string
from pathlib import Path

PERSONS = ["Rafał Brzoska", "Monika Olejnik", "Adam Glapiński", "Krzysztof Stanowski", "Donald Tusk", "Dominika Kulczyk"]
NARRATIVES = {
    "zamach": "{p} postrzelony. Nagranie z miejsca zdarzenia usunięto po kilku minutach. Dziennikarze ujawniają, że {p} znał platformę, "
              "dzięki której zwykli Polacy zarabiają. Wpłać {amt} zł i obserwuj zysk już dziś. Zostało tylko {n} miejsc.",
    "aresztowanie": "Wyprowadzono go w kajdankach po programie na żywo. {p} zdradził w studiu, jak zarabiać pasywnie. Banki nie chcą, "
                    "żebyś to wiedział. Zacznij od {amt} zł, automatyczny algorytm robi resztę. Zostało tylko {n} kont.",
    "wywiad": "Szokujący wywiad: {p} ujawnia sekret bogactwa. Platforma inwestycyjna z AI daje {amt} zł dziennie bez doświadczenia. "
              "Oferta kończy się dziś, zostało {n} miejsc. Zarejestruj się i odbierz bonus.",
}
LEGIT = ["{p} otworzył nową fabrykę w Polsce. Wydarzenie relacjonowały lokalne media, a prezes podziękował pracownikom za rok pracy.",
         "Rozmowa z {p} o historii sztuki i wystawach w Warszawie. Wywiad ukazał się w weekendowym dodatku."]
SYN = [("zarabiać", "dorabiać"), ("platforma", "serwis"), ("sekret", "tajemnicę"), ("Wpłać", "Przelej"), ("Zacznij", "Rozpocznij")]


def _rid(rnd, n):
    return "".join(rnd.choices(string.ascii_letters + string.digits, k=n))


def _domain(rnd, style):
    w = "".join(rnd.choices(string.ascii_lowercase, k=rnd.randint(6, 9)))
    return f"{w}.{style}"


def _page(title, body, saved_from, pixel):
    fbq = f"<script>fbq('init', '{pixel}');</script>" if pixel else ""
    nodes = "".join(f"<div class='blk{k % 9} sect'><p>x{k}</p></div>" for k in range(30))  # strona o dostatecznej strukturze
    return (f"<!-- saved from url=({len(saved_from):04d}){saved_from} -->\n<html><head><title>{title}</title>{fbq}</head>"
            f"<body><div class='hero art'><h1>{title}</h1><p>{body}</p></div>{nodes}</body></html>")


def _har(urls):
    return json.dumps({"log": {"entries": [{"startedDateTime": "2026-11-01T10:00:00Z", "request": {"url": u},
                                            "response": {"status": 200, "content": {"mimeType": "text/html"}}} for u in urls]}})


def generate(out: Path, n_operators: int = 6, campaigns_per_op: int = 2, variants: int = 3, seed: int = 1,
             missing_rate: float = 0.25) -> dict:
    """Zapisuje przypadki do `out/<id>/` i etykiety do `out/prawda.json`; zwraca prawdę {materiał: {kampania, operator, rodzaj}}."""
    rnd = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    truth: dict[str, dict] = {}
    shared_kit = f"/kit{_rid(rnd, 4).lower()}/landing"
    ops = []
    for k in range(n_operators):
        ops.append({"id": f"O{k + 1}", "kit": shared_kit if k < 2 else f"/k{_rid(rnd, 5).lower()}/lp",  # O1 i O2 dzielą zestaw
                    "pixel": "".join(rnd.choices(string.digits, k=16)), "tds_len": (rnd.choice([12, 16, 20]), rnd.choice([8, 10])),
                    "style": rnd.choice(["example", "test"]), "advs": [f"Konto {_rid(rnd, 5)}" for _ in range(3)]})
    ops[1]["tds_len"] = (ops[0]["tds_len"][0] + 2, ops[0]["tds_len"][1] + 1)  # inny schemat TDS mimo wspólnego zestawu
    n = 0
    names = list(NARRATIVES)
    for oi, op in enumerate(ops):
        for ci in range(campaigns_per_op):
            narr = names[(oi + ci) % len(names)] if oi < 3 else names[ci % len(names)]  # ta sama narracja u kilku operatorów
            person = PERSONS[(oi * 2 + ci) % len(PERSONS)]
            cid = f"{op['id']}-K{ci + 1}"
            base = NARRATIVES[narr].format(p=person, amt=rnd.choice([250, 500, 1000]), n=rnd.randint(3, 20))
            for v in range(variants):
                n += 1
                mid = f"s{n:03d}"
                text = base
                for a, b in rnd.sample(SYN, k=rnd.randint(0, 2)):
                    text = text.replace(a, b)
                dom = _domain(rnd, op["style"])
                q = f"utm_id={_rid(rnd, op['tds_len'][0])}&utm_medium={_rid(rnd, op['tds_len'][1])}&utm_visit={_rid(rnd, 8)}-1111-7222-8333-444455556666"
                url = f"https://{dom}/?{q}"
                d = out / mid
                d.mkdir(exist_ok=True)
                title = f"Szokujące: {person} i platforma {narr}"
                miss = rnd.random() < missing_rate
                pixel = op["pixel"] if rnd.random() > 0.3 else None
                if not miss or rnd.random() < 0.5:
                    (d / "strona.html").write_text(_page(title, text, url, pixel), encoding="utf-8")
                if not miss or rnd.random() < 0.5:
                    (d / f"{dom}.har").write_text(_har([url, f"https://{dom}{op['kit']}/app.js", f"https://{dom}{op['kit']}/style.css"]), encoding="utf-8")
                if not list(d.iterdir()):
                    (d / "strona.html").write_text(_page(title, text, url, None), encoding="utf-8")
                truth[mid] = {"kampania": cid, "operator": op["id"], "rodzaj": "oszustwo"}
    for k in range(max(3, n_operators)):  # negatywy: legalne strony z tymi samymi osobami
        n += 1
        mid = f"s{n:03d}"
        person = PERSONS[k % len(PERSONS)]
        d = out / mid
        d.mkdir(exist_ok=True)
        dom = _domain(rnd, "example")
        url = f"https://{dom}/artykul/{k}"
        (d / "strona.html").write_text(_page(f"Wiadomości: {person}", rnd.choice(LEGIT).format(p=person), url, None), encoding="utf-8")
        (d / f"{dom}.har").write_text(_har([url, f"https://{dom}/static/site.css"]), encoding="utf-8")
        truth[mid] = {"kampania": f"neg:{mid}", "operator": f"neg:{mid}", "rodzaj": "negatyw"}
    (out / "prawda.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    return truth
