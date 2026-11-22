"""Wznawianie importu: czytanie przyrostowe pliku JSONL, stan przetwarzania i bezpieczny zapis galerii.

Problemy, które to rozwiązuje (scraper dopisuje do pliku, a nasz proces może się przerwać w dowolnym miejscu):

  * plik czytamy od ZAPAMIĘTANEGO BAJTU, nie od początku; przesunięcie rośnie tylko o w pełni przeczytane linie;
  * niedokończona ostatnia linia (writer jeszcze pisze) nie jest przetwarzana, dopóki się nie dokończy;
  * stan zapisujemy atomowo (plik tymczasowy + zamiana), po każdej paczce;
  * jeśli plik został podmieniony albo skrócony (inny początek, mniejszy rozmiar), zaczynamy od zera; duplikatów nie będzie, bo
    rejestr przetworzonych (decyzje w grafie, `decision.decided`) pomija to, co już rozstrzygnięto;
  * zła linia (nie JSON) nie blokuje reszty: trafia do `watch_errors.jsonl`;
  * galeria (JSONL) dostaje wiersz jednym zapisem z `fsync`, a przed otwarciem odcinamy niedokończoną końcówkę po awarii.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

HEAD_BYTES = 256


def _head(path: Path) -> str:
    """Skrót pierwszej linii (do HEAD_BYTES): stabilny, gdy plik tylko rośnie; zmienia się, gdy plik podmieniono."""
    with path.open("rb") as f:
        first = f.read(HEAD_BYTES).split(b"\n", 1)[0]
    return hashlib.sha1(first).hexdigest()


def load_state(state_path: Path, path: Path) -> dict:
    """Stan dla pliku: {'offset': bajt, 'head': skrót początku}. Plik podmieniony lub skrócony => od zera."""
    st = {}
    if state_path.exists():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8")).get(str(path), {})
        except ValueError:
            st = {}
    if not isinstance(st, dict):          # stary format: sama liczba linii; nie da się z niej odtworzyć bajtu
        st = {}
    size = path.stat().st_size if path.exists() else 0
    if st.get("offset", 0) > size or (st.get("offset", 0) and st.get("head") != _head(path)):
        return {"offset": 0, "head": _head(path) if size else None, "reset": True}
    return {"offset": st.get("offset", 0), "head": st.get("head") or (_head(path) if size else None)}


def save_state(state_path: Path, path: Path, offset: int, head: str | None) -> None:
    """Atomowy zapis: plik tymczasowy, `fsync`, zamiana. Awaria w trakcie zostawia poprzedni, poprawny stan."""
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    state[str(path)] = {"offset": offset, "head": head}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(state))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, state_path)


def read_new(path: Path, offset: int, limit: int | None = None) -> tuple[list[tuple[int, str]], int]:
    """Nowe, kompletne linie od `offset`: lista (bajt po linii, tekst) i przesunięcie po ostatniej przeczytanej.

    Końcówka bez znaku nowej linii jest brana tylko wtedy, gdy jest poprawnym JSON-em (writer nie dopisał `\\n`); inaczej czeka."""
    out: list[tuple[int, str]] = []
    pos = offset
    with path.open("rb") as f:
        f.seek(offset)
        while limit is None or len(out) < limit:
            raw = f.readline()
            if not raw:
                break
            end = pos + len(raw)
            if not raw.endswith(b"\n"):
                try:
                    json.loads(raw)
                except ValueError:
                    break                      # niedokończona linia: zostaje na następny przebieg
            pos = end
            if raw.strip():
                out.append((pos, raw.decode("utf-8", errors="replace")))
    return out, pos


def log_error(path: Path, line: str, why: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"linia": line[:500], "powód": why}, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------------------------------------------------
# galeria (JSONL)


def repair_gallery(path: Path) -> int:
    """Odcina z końca pliku galerii wiersz niedokończony po awarii (brak `\\n` albo niepoprawny JSON). Zwraca liczbę uciętych bajtów."""
    if not path.exists() or path.stat().st_size == 0:
        return 0
    data = path.read_bytes()
    keep = len(data)
    if not data.endswith(b"\n"):
        keep = data.rfind(b"\n") + 1
    else:
        last = data[:-1].rfind(b"\n") + 1
        try:
            json.loads(data[last:])
        except ValueError:
            keep = last
    if keep != len(data):
        with path.open("r+b") as f:
            f.truncate(keep)
    return len(data) - keep


def append_line(path: Path, obj: dict) -> None:
    """Dopisuje jeden wiersz JSONL jednym zapisem, z `fsync` (kompletny wiersz albo nic widocznego po repair_gallery)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
