"""Schemat perswazji: jawne „ruchy” w tekście reklamy i strony (wyjaśnialne „DNA” kampanii).

Hipoteza projektu: oszuści zmieniają temat (znana osoba, produkt), ale powtarzają ten sam schemat perswazji. Ruchy wykrywamy
słownikami (polskie znaki ujednolicone, bo OCR je gubi). Wynik: liczba wystąpień na 1000 słów, a do porównań udział ruchu.
To warstwa wyjaśniająca; podobieństwo schematu ponad tematami liczy `template.py` (embeddingi + LEACE).
"""
from __future__ import annotations

import re

import numpy as np

_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")

MOVES: dict[str, tuple[str, list[str]]] = {
    "szokujacy_news": ("szokujący news / sensacja", [
        "szok", "skandal", "pilne", "breaking", "wstrzas", "zamach", "kajdank", "aresztow", "usunieto", "ocenzur",
        "na zywo", "transmisj", "postrzel", "napasc", "atak na"]),
    "tajemnica": ("tajemnica / spisek", [
        "sekret", "tajemnic", "ukrywa", "nie chca", "nie chcieli", "zakazan", "ujawni", "prawd", "elity", "zablokowac",
        "banki nie", "zatai"]),
    "autorytet": ("autorytet / ekspert", [
        "dr ", "dr n. med", "profesor", "prof.", "naukow", "lekarz", "ekspert", "badani", "certyfik", "udowodnion",
        "specjalist", "minister", "prezes"]),
    "presja_czasu": ("presja czasu / niedobór", [
        "zostalo tylko", "pozostalo tylko", "ostatni", "tylko dzis", "konczy sie", "promocja konczy", "pospiesz",
        "wkrotce", "limitowan", "ograniczon", "liczba miejsc", "nie czekaj", "zanim"]),
    "dowod_spoleczny": ("dowód społeczny / komentarze", [
        "lubie to", "odpowiedz", "komentarz", "opini", "recenzj", "tysiace", "polakow juz", "uzytkownik", "graczy",
        "pomoglo", "polecam", "dziekuje"]),
    "obietnica_zysku": ("obietnica zysku", [
        "zysk", "zarob", "dochod", "wyplat", "pasywn", "dziennie", "tygodniowo", "miesiecznie", "bogac", "milion",
        "bonus", "wygran", "zwrot"]),
    "niska_bariera": ("niska bariera / automat", [
        "zaledwie", "tylko 1", "minimaln", "wplac", "depozyt", "bez doswiadczenia", "automatycz", "algorytm",
        "sztuczn", " ai ", "bot", "kazdy moze", "bez wysilku"]),
    "formularz": ("formularz / kontakt z konsultantem", [
        "imie", "telefon", "e-mail", "email", "zarejestruj", "rejestracj", "zamow", "konsultant", "oddzwoni",
        "wypelnij", "formularz"]),
    "podrobiony_portal": ("podrobiony portal / marka", [
        "gazeta.pl", "tvn24", "onet", "wp.pl", "interia", "polsat", "forbes", "bbc", "app store", "google play",
        "rmf", "business insider"]),
    "cena_rabat": ("cena / rabat", [
        "%", "znizk", "rabat", "zamiast", " pln", " zl", "cena", "darmow", "gratis"]),
}


def fold(text: str) -> str:
    return text.translate(_PL).lower()


def moves(text: str) -> dict[str, float]:
    """Liczba wystąpień ruchu na 1000 słów (0, gdy brak tekstu)."""
    t = " " + re.sub(r"https?://\S+", " ", fold(text)) + " "
    n_words = max(1, len(t.split()))
    return {k: round(1000 * sum(t.count(p) for p in pats) / n_words, 2) for k, (_, pats) in MOVES.items()}


def dna(text: str) -> np.ndarray:
    """Profil ruchów jako wektor udziałów (suma 1), w kolejności `MOVES`."""
    v = np.array(list(moves(text).values()), dtype=float)
    s = v.sum()
    return v / s if s > 0 else v


def shared_moves(a: dict[str, float], b: dict[str, float], min_rate: float = 1.0) -> list[str]:
    """Ruchy wyraźnie obecne w obu materiałach (≥ min_rate na 1000 słów), etykietami dla analityka."""
    return [MOVES[k][0] for k in MOVES if a.get(k, 0) >= min_rate and b.get(k, 0) >= min_rate]


def label(key: str) -> str:
    return MOVES[key][0]
