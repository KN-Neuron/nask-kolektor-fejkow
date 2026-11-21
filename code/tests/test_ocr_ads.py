"""Odczyt reklamodawcy i treści kreacji ze zrzutu (wyniki OCR zapisane jako tekst, bez plików)."""
from fejki.demo.material import advertisers, clean_ocr


def test_advertiser_before_sponsored_with_icon_noise():
    assert advertisers("@ Sharon Coleman eee Sponsorowane Dowiedz się więcej") == ["Sharon Coleman"]
    assert advertisers("& EasyJoy Sponsorowane INCYDENT W CENTRUM") == ["EasyJoy"]


def test_advertiser_after_sponsored_on_result_card():
    assert advertisers("Dziedzictwo gwiazd Sponsorowane - Glowpixel") == ["Glowpixel"]
    assert advertisers("Tytuł reklamy Sponsorowane · Glowpixel") == ["Glowpixel"]


def test_no_advertiser_without_marker():
    assert advertisers("Zwykły tekst bez znacznika") == []


def test_clean_ocr_drops_platform_ui():
    t = clean_ocr("Formal Favorable Sponsorowane Dowiedz się więcej Wydarzenie, które wstrząsnęło Polską")
    assert "Sponsorowane" not in t and "Dowiedz" not in t
    assert "wstrząsnęło" in t
