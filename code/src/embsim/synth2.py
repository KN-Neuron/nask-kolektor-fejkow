"""Syntetyka v2: ten sam model co fejki.demo.synth_cases (operator -> kampanie -> warianty), ale z szumem jak w PRAWDZIWYM HAR.

Dlaczego: v1 miała 3 adresy w HAR, które zawsze się zgadzały, więc cechy infrastruktury wyglądały czyściej niż w rzeczywistości.
Przypadki NASK-10 mają 5–15 prefiksów zasobów, do 11 nazw parametrów i do 10 hostów na przypadek, a część z nich to wszechobecne
trackery (Facebook, Google, CDN). Tu każdy zrzut ma:
  * wszechobecne zasoby (trackery, CDN) w losowym podzbiorze, wspólne dla WSZYSTKICH operatorów (nie niosą informacji);
  * zasoby zestawu operatora w losowym podzbiorze (zrzuty tej samej kampanii nie są identyczne);
  * łańcuch przekierowań przez jednego z 2–3 brokerów operatora;
  * parametry adresu: rdzeń operatora + losowe dodatkowe i śmieciowe nazwy;
  * jednorazowe zasoby zewnętrzne (szum rozdymający sumę zbiorów), lustrzane domeny lądowania w obrębie kampanii;
  * z prawdopodobieństwem `missing_rate` brak HTML albo HAR.
Prawda ma dwa poziomy: kampania (operator + przekaz) i operator. Negatywy to „legalne” strony z tymi samymi osobami i wszechobecnymi
trackerami. Ograniczenie: to wciąż generator pisany przez nas pod nasze cechy; ma ZMNIEJSZYĆ rozjazd względem prawdziwych danych,
nie go wyeliminować.
"""
from __future__ import annotations

import json
import random
import string
from pathlib import Path

from fejki.demo.synth_cases import LEGIT, NARRATIVES, PERSONS, SYN, _domain, _har, _page, _rid

EXTRA_NARRATIVES = {
    "lotto": "{p} wygrał w loterii i ujawnia: wystarczy {amt} zł, by dołączyć do zamkniętej grupy. Pozostało {n} wolnych miejsc, "
             "zarejestruj się dziś i odbierz bonus.",
    "bank": "Alarm w bankach: {p} ostrzega przed utratą oszczędności. Przenieś {amt} zł na bezpieczne konto w programie ochronnym, "
            "oferta ważna tylko dla pierwszych {n} osób.",
    "zdrowie": "Lekarze w szoku: {p} poleca naturalny preparat, który działa w {n} dni. Zamów teraz, płacisz tylko {amt} zł za przesyłkę.",
    "praca": "{p} szuka współpracowników do pracy zdalnej: {amt} zł dziennie bez doświadczenia. Zostało {n} stanowisk, aplikuj od razu.",
    "kredyt": "Pożyczka bez BIK od ręki dzięki {p}: kwota do {amt} zł, decyzja w kilka minut. Dostępne tylko dla {n} pierwszych wniosków.",
}
ALL_NARR = {**NARRATIVES, **EXTRA_NARRATIVES}
UBIQ_HOSTS = ["facebook.net", "facebook.com", "googletagmanager.com", "google-analytics.com", "jsdelivr.net", "gstatic.com",
              "cloudflare.com", "fonts.googleapis.com"]
UBIQ_DIRS = ["/signals/config", "/en_US", "/npm/jquery@3.6.0", "/gtag/js", "/css/fonts", "/tr/events"]
PARAM_POOL = ["utm_id", "utm_medium", "utm_source", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid", "cid", "sid", "ref",
              "clickid", "subid", "adset", "placement", "device", "geo", "lang", "ts", "v", "pmd", "ex", "dl", "rl", "id"]
FILES = ["app.js", "main.js", "style.css", "sdk.js", "config.json", "bundle.js", "logo.png", "events.js"]


def _kit_dir(rnd, n_seg=2):
    return "/" + "/".join("".join(rnd.choices(string.ascii_lowercase, k=rnd.randint(3, 6))) for _ in range(n_seg))


def generate(out: Path, n_operators: int = 6, campaigns_per_op: int = 2, variants: int = 3, seed: int = 1, missing_rate: float = 0.25,
             noise: float = 1.0) -> dict:
    """Zapisuje `out/<id>/{strona.html, <domena>.har}` i `out/prawda.json`; zwraca prawdę {id: {kampania, operator, rodzaj}}."""
    rnd = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    ops = []
    for k in range(n_operators):
        ops.append({"id": f"O{k + 1}", "kits": [_kit_dir(rnd) for _ in range(rnd.randint(3, 6))],
                    "brokers": [f"{_rid(rnd, 6).lower()}.{rnd.choice(['xyz', 'top', 'site'])}" for _ in range(rnd.randint(2, 3))],
                    "core": rnd.sample(PARAM_POOL, rnd.randint(2, 4)), "extras": rnd.sample(PARAM_POOL, rnd.randint(3, 7)),
                    "pixel": "".join(rnd.choices(string.digits, k=16)) if rnd.random() < 0.35 else None,
                    "style": rnd.choice(["example", "test"]), "third": [f"{_rid(rnd, 7).lower()}.{rnd.choice(['io', 'net'])}"
                                                                         for _ in range(rnd.randint(1, 2))]})
    # dwa operatory dzielą część zasobów (trudny przypadek: wspólny zestaw, ale inny schemat adresu i brokerzy)
    if len(ops) >= 2:
        ops[1]["kits"][:2] = ops[0]["kits"][:2]
    names = list(ALL_NARR)
    truth: dict[str, dict] = {}
    n = 0
    for oi, op in enumerate(ops):
        for ci in range(campaigns_per_op):
            narr = rnd.choice(names)                       # przekaz losowy: część kampanii różnych operatorów współdzieli narrację
            person, product = rnd.choice(PERSONS), rnd.choice(["Metabo RX", "Uromexil", "CryptoX", "BonusPlus"])
            cid = f"{op['id']}-K{ci + 1}"
            base = ALL_NARR[narr].format(p=person, amt=rnd.choice([250, 500, 1000]), n=rnd.randint(3, 20))
            mirrors = [_domain(rnd, op["style"]) for _ in range(rnd.randint(1, 2))]
            for v in range(variants):
                n += 1
                mid = f"s{n:03d}"
                text = base
                for a, b in rnd.sample(SYN, k=rnd.randint(0, 2)):
                    text = text.replace(a, b)
                dom = rnd.choice(mirrors) if rnd.random() < 0.5 else _domain(rnd, op["style"])
                q = [(k, _rid(rnd, 10)) for k in op["core"]]
                q += [(k, _rid(rnd, 8)) for k in op["extras"] if rnd.random() < 0.6]
                q += [(k, _rid(rnd, 6)) for k in rnd.sample(PARAM_POOL, rnd.randint(0, int(3 * noise)))]
                landing = f"https://{dom}/?" + "&".join(f"{k}={val}" for k, val in q)
                urls = [landing]
                for kd in op["kits"]:                      # zasoby zestawu operatora: losowy podzbiór
                    if rnd.random() < 0.75:
                        urls += [f"https://{dom}{kd}/{rnd.choice(FILES)}" for _ in range(rnd.randint(1, 2))]
                for h in UBIQ_HOSTS:                       # wszechobecne trackery i CDN
                    if rnd.random() < 0.8:
                        urls.append(f"https://{h}{rnd.choice(UBIQ_DIRS)}/{rnd.choice(FILES)}")
                for _ in range(rnd.randint(1, 3)):         # łańcuch przez brokera
                    urls.append(f"https://{rnd.choice(op['brokers'])}/go?" + "&".join(f"{k}={_rid(rnd, 6)}" for k in rnd.sample(op["core"], 1)))
                urls += [f"https://{rnd.choice(op['third'])}/api/v1/{rnd.choice(FILES)}" for _ in range(rnd.randint(0, 2))]
                urls += [f"https://{_rid(rnd, 7).lower()}.{rnd.choice(['com', 'net'])}/{rnd.choice(UBIQ_DIRS)[1:]}/{rnd.choice(FILES)}"
                         for _ in range(rnd.randint(2, int(2 + 8 * noise)))]          # jednorazowy szum zewnętrzny
                d = out / mid
                d.mkdir(exist_ok=True)
                title = f"Szokujące: {person} i {product}"
                miss = rnd.random() < missing_rate
                drop_html = miss and rnd.random() < 0.5
                if not drop_html:
                    pixel = op["pixel"] if (op["pixel"] and rnd.random() < 0.6) else None
                    (d / "strona.html").write_text(_page(title, text, landing, pixel), encoding="utf-8")
                if not miss or drop_html:
                    (d / f"{dom}.har").write_text(_har(urls), encoding="utf-8")
                if not list(d.iterdir()):
                    (d / "strona.html").write_text(_page(title, text, landing, None), encoding="utf-8")
                truth[mid] = {"kampania": cid, "operator": op["id"], "rodzaj": "oszustwo"}
    for k in range(max(3, n_operators)):                   # negatywy: legalne strony z tymi samymi osobami i trackerami
        n += 1
        mid = f"s{n:03d}"
        person = PERSONS[k % len(PERSONS)]
        d = out / mid
        d.mkdir(exist_ok=True)
        dom = _domain(rnd, "example")
        url = f"https://{dom}/artykul/{k}"
        urls = [url, f"https://{dom}/static/site.css"] + [f"https://{h}{rnd.choice(UBIQ_DIRS)}/{rnd.choice(FILES)}"
                                                          for h in UBIQ_HOSTS if rnd.random() < 0.7]
        (d / "strona.html").write_text(_page(f"Wiadomości: {person}", rnd.choice(LEGIT).format(p=person), url, None), encoding="utf-8")
        (d / f"{dom}.har").write_text(_har(urls), encoding="utf-8")
        truth[mid] = {"kampania": f"neg:{mid}", "operator": f"neg:{mid}", "rodzaj": "negatyw"}
    (out / "prawda.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    return truth
