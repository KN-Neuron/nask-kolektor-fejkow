"""Interpretacja wyniku dla analityka: werdykt po ludzku, jakie dane wejściowe były, czego zabrakło i co z tym zrobić.

Cel: wynik „nowy wzorzec, 0,00” nie może zostać bez wyjaśnienia. Analityk ma wiedzieć, czy to znaczy „naprawdę nic wspólnego”,
czy „za mało danych, żeby cokolwiek stwierdzić” (to są dwie różne sytuacje).
"""
from __future__ import annotations

from .material import Material
from .similar import MatchResult

CHANNELS = [
    ("domena docelowa", lambda m: bool(m.landing_domains)),
    ("schemat adresu (system kierowania ruchu)", lambda m: bool(m.url_schemes)),
    ("identyfikatory reklam i pikseli", lambda m: bool(m.ad_ids or m.pixel_ids or m.tracker_ids)),
    ("tekst strony lub reklamy", lambda m: len(m.text) > 200),
    ("obraz (zrzut, kreacja)", lambda m: any(i.role in ("zrzut", "kreacja", "klatka") for i in m.images)),
    ("struktura strony i zasoby (HTML)", lambda m: m.pages > 0),
    ("przekierowania i usługi zewnętrzne (HAR)", lambda m: bool(m.redirects or m.third_party_hosts or m.path_prefixes)),
]


def input_profile(m: Material) -> tuple[list[str], list[str]]:
    have = [n for n, f in CHANNELS if f(m)]
    lack = [n for n, f in CHANNELS if not f(m)]
    return have, lack


def advice(m: Material, lack: list[str]) -> list[str]:
    out = []
    if m.source == "url" or (not m.pages and not m.images and not m.text.strip()):
        out.append("Podano tylko adres: analiza opiera się na kształcie adresu i domenie. Dodaj zapis strony (HTML) albo log HAR, "
                   "żeby porównać treść, szablon, przekierowania i usługi zewnętrzne.")
    if "obraz (zrzut, kreacja)" in lack and m.source != "url":
        out.append("Brak obrazu: dodaj zrzut reklamy, żeby odczytać reklamodawcę, tekst kreacji i porównać wygląd.")
    if "tekst strony lub reklamy" in lack and m.source != "url":
        out.append("Mało tekstu: dołóż treść reklamy lub stronę, bo tekst jest najsilniejszym kanałem przy braku wspólnych identyfikatorów.")
    return out


def verdict(r: MatchResult, m: Material, n_ref: int, n_urlscan: int) -> dict:
    """Jedno zdanie werdyktu, poziom pewności i znaczenie wyniku."""
    have, lack = input_profile(m)
    ref = f"zbiór referencyjny: {n_ref} materiałów" + (f" (w tym {n_urlscan} skanów urlscan)" if n_urlscan else "")
    d = r.decision
    if d.startswith("przypisano"):
        level, mean = "success", "Materiał ma ten sam przekaz co znana kampania (duplikat lub wariant). To powiązanie jest dobrze uzasadnione."
    elif d.startswith("nowy przekaz, ale ta sama infrastruktura"):
        level, mean = "success", ("Treść jest inna niż w znanych kampaniach, ale infrastruktura i śledzenie wskazują tego samego operatora: "
                                  "to prawdopodobnie kolejna kampania tej samej sieci.")
    elif d.startswith("możliwe powiązanie"):
        level, mean = "warning", "Są słabe wspólne ślady. To trop do sprawdzenia przez analityka, nie ustalone powiązanie."
    else:
        if len(have) <= 2:
            level = "warning"
            mean = ("Nie da się tego rozstrzygnąć: wejście zawiera zbyt mało danych (zob. poniżej), więc brak powiązania nie znaczy, "
                    "że materiał jest nowy. Uzupełnij dane i spróbuj ponownie.")
        else:
            level = "info"
            mean = (f"Przy dostępnych danych nie znaleziono wspólnych śladów z żadną znaną kampanią ({ref}). "
                    "To może być nowa kampania albo kampania, której nie ma w zbiorze referencyjnym.")
    return {"decision": d, "level": level, "meaning": mean, "have": have, "lack": lack, "advice": advice(m, lack), "ref": ref}
