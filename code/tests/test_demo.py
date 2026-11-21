"""Testy demonstratora na sztucznych plikach (dane organizatora nie mogą trafić do repozytorium)."""
from __future__ import annotations

import json

from PIL import Image, ImageDraw

from fejki.demo.cards import build_cards, card_markdown, domains_csv
from fejki.demo.material import (
    advertisers,
    build_material,
    date_from_name,
    find_persons,
    hamming,
    load_persons,
    material_from_inputs,
    phash,
    url_features,
)
from fejki.demo.similar import all_pairs, campaigns, match

PIXEL = "1234567890123456"
TDS = "utm_id=AbCdEfGhIjKlMnOpQrSt&utm_medium=Ab12Cd34Ef&utm_campaign=Gh56Ij78Kl&utm_content=Mn90Op12Qr&utm_visit=01a19999-1111-7222-8333-444455556666"


def _page(title: str, body: str, saved_from: str, pixel: str | None = None) -> str:
    fbq = f"<script>fbq('init', '{pixel}');</script>" if pixel else ""
    return (f"<!-- saved from url=(0077){saved_from} -->\n<html><head><title>{title}</title>{fbq}</head>"
            f"<body><div class='hero art'><h1>{title}</h1><p>{body}</p></div></body></html>")


def _har(urls: list[str], when: str = "2026-10-09T06:25:24.976Z") -> str:
    return json.dumps({"log": {"entries": [{"startedDateTime": when, "request": {"url": u},
                                            "response": {"status": 200, "content": {"mimeType": "text/html"}}} for u in urls]}})


def _case(tmp, name, title, body, domain, pixel=None, query=TDS, kit="/_kit/production/landing"):
    d = tmp / name
    d.mkdir()
    url = f"https://{domain}/?{query}"
    (d / f"{title[:20]}.html").write_text(_page(title, body, url, pixel), encoding="utf-8")
    (d / f"{domain}.har").write_text(_har([url, f"https://{domain}{kit}/app.js"]), encoding="utf-8")
    return build_material(name, name, "folder", files=[p for p in d.rglob("*") if p.is_file()], ocr=False, base=d)


STORY = ("Zamach na znanego przedsiębiorcę. Rafał Brzoska ujawnia platformę, dzięki której zwykli ludzie zarabiają. "
         "Wpłać 1000 złotych i obserwuj zysk na platformie inwestycyjnej. Komentarze czytelników potwierdzają wypłaty. ")


def test_url_features_scheme_ids_and_prefix():
    f = url_features(f"https://shop.example.com/_kit/production/landing/x.css?{TDS}&ad_id=120250558396250564&pxl={PIXEL}&acc=hk77_tv6")
    assert f["domain"] == "example.com"
    assert "utm_visit:uuid" in f["scheme"] and "utm_id:rnd20" in f["scheme"]
    assert f["ad_ids"] == ["120250558396250564"] and f["pixel_ids"] == [PIXEL] and f["accounts"] == ["hk77"]
    assert f["prefix"] == "/_kit/production/landing"
    assert url_features("https://www.facebook.com/ads/library/?id=1982065065827084")["ad_ids"] == ["1982065065827084"]


def test_persons_inflection_and_no_surname_confusion():
    persons = load_persons()
    found = find_persons("Zamach na Rafała Brzoskę. Mateusza Morawieckiego zaproszono do studia.", persons)
    assert "Rafał Brzoska" in found and "Mateusz Morawiecki" in found
    # pospolite nazwisko bez imienia nie jest dopasowaniem; forma żeńska nie łapie męskiej
    assert "Robert Lewandowski" not in find_persons("Tomasz Lewandowski, prezes funduszu", persons)
    assert "Robert Lewandowski" not in find_persons("Anna Lewandowska poleca", persons)


def test_advertiser_from_ocr():
    assert advertisers("Formal Favorable Sponsorowane @ NA ZYWO") == ["Formal Favorable"]
    assert advertisers("V Sustain Studio Sponsorowane x Sustain Studio Sponsorowane") == ["Sustain Studio"]


def test_phash_identical_and_different():
    a = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(a).rectangle([20, 20, 120, 160], fill="black")
    b = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(b).ellipse([60, 10, 190, 120], fill="black")
    assert hamming(phash(a), phash(a.resize((400, 400)))) <= 4
    assert hamming(phash(a), phash(b)) > 10


def test_material_from_folder_extracts_features(tmp_path):
    m = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    assert m.landing_domains == ["alpha-news.live"]
    assert PIXEL in m.pixel_ids
    assert "Rafał Brzoska" in m.persons
    assert m.url_schemes and "/_kit/production/landing" in m.path_prefixes
    assert "brak zrzutu ekranu / nagrania" in m.missing


def test_pairs_campaigns_networks_and_matching(tmp_path):
    a = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    b = _case(tmp_path, "2", "Wiem, kto strzelał: zamach", STORY, "beta-news.live", pixel=PIXEL)  # duplikat na innej domenie
    c = _case(tmp_path, "3", "Kardiolog ostrzega", "Nowy suplement obniża ciśnienie w 7 dni. Zamów kapsułki dziś.",
              "gamma-health.top")  # inny przekaz, ten sam zestaw TDS
    d = _case(tmp_path, "4", "Sweet Bonus Casino", "Odbierz bonus 5000 zł w kasynie.", "casino-x.xyz",
              query="utm_source=fb&utm_campaign=promo", kit="/casino/static")  # nic wspólnego
    mats = [a, b, c, d]
    pairs = all_pairs(mats)
    ab = next(p for p in pairs if {p.a, p.b} == {"1", "2"})
    assert ab.score >= 0.9 and ab.relation == "duplikat"
    assert any("piksel" in e.reason for e in ab.evidence)
    camps = campaigns(mats, pairs, 0.7, "kampania")
    nets = campaigns(mats, pairs, 0.7, "sieć")
    assert sorted(next(x.members for x in camps if "1" in x.members)) == ["1", "2"]
    assert "3" in next(x.members for x in nets if "1" in x.members)  # ta sama sieć przez wspólny zestaw strony
    assert next(x.members for x in nets if "4" in x.members) == ["4"]  # obcy materiał nie jest doklejany
    # nowy materiał: wariant znanej kampanii
    e = material_from_inputs("nowy", url=f"https://delta-news.live/?{TDS}", text=STORY)
    r = match(e, mats, camps, nets)
    assert r.best_campaign is not None and r.best_score >= 0.7
    # nowy materiał bez wspólnych śladów
    f = material_from_inputs("obcy", text="Przepis na sernik z rodzynkami i wanilią.")
    assert match(f, mats, camps, nets).decision.startswith("nowy wzorzec")


def test_incomplete_input_does_not_crash(tmp_path):
    p = tmp_path / "broken.har"
    p.write_text("{not json", encoding="utf-8")
    m = material_from_inputs("x", files=[p])
    assert any("HAR nieczytelny" in n for n in m.notes)
    assert "brak zapisanej strony (HTML)" in m.missing


def test_date_from_name_converts_local_time_and_skips_ambiguous():
    assert date_from_name("Zrzut ekranu 2026-10-09 082411.png") == "2026-10-09T06:24:11"  # CEST (UTC+2) → UTC
    assert date_from_name("Zrzut ekranu 2026-11-21 120000.png") == "2026-11-21T11:00:00"  # CET (UTC+1) → UTC
    assert date_from_name("Nagranie 2026-10-27.mp4") == "2026-10-27"
    assert date_from_name("ScreenRecording_08-12-2026 08-38-33_1.MP4") is None  # dzień czy miesiąc? nie zgadujemy


def test_campaign_card_window_and_domains_to_verify(tmp_path):
    a = _case(tmp_path, "1", "Wiem, kto strzelał: zamach", STORY, "alpha-news.live", pixel=PIXEL)
    b = _case(tmp_path, "2", "Wiem, kto strzelał: zamach", STORY, "beta-news.live", pixel=PIXEL)
    c = _case(tmp_path, "3", "Kardiolog ostrzega", "Nowy suplement obniża ciśnienie w 7 dni. Zamów kapsułki dziś.",
              "gamma-health.top")
    (tmp_path / "2" / "beta-news.live.har").write_text(
        _har(["https://beta-news.live/?" + TDS, "https://beta-news.live/_kit/production/landing/app.js"], "2026-10-11T10:00:00Z"),
        encoding="utf-8")
    from fejki.demo.material import material_from_folder

    b = material_from_folder(tmp_path / "2", ocr=False)
    mats = [a, b, c]
    pairs = all_pairs(mats)
    cards = build_cards(mats, pairs, campaigns(mats, pairs, 0.7, "kampania"), campaigns(mats, pairs, 0.7, "sieć"))
    k = next(x for x in cards if "1" in x.members)
    assert k.members == ["1", "2"] and k.network
    assert k.window_start.startswith("2026-10-09") and k.window_end.startswith("2026-10-11") and k.window_days == 2.1
    prio = {d.domain: d.priority for d in k.domains_to_verify}
    assert prio["alpha-news.live"] == "wysoki" and prio["beta-news.live"] == "wysoki"
    assert prio["gamma-health.top"] == "średni"  # domena innej kampanii tej samej sieci
    md = card_markdown(k)
    assert "Domeny do weryfikacji" in md and "alpha-news.live" in md and "nie czas emisji" in md
    assert domains_csv(cards).splitlines()[0].startswith("kampania,siec,domena,priorytet")
