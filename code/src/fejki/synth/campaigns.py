"""Synthetic generator: background ads, injected campaigns, controls C1, decoys, simulated CERT list.

Rule backend: persuasion templates are sentence frames with slots, shared across topics (the 'template'
signal), while topic words vary. All people, brands and domains are fictional.
"""
from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from ..schema import Ad, CampaignSpec

TOPICS = ["invest_crypto", "health", "institution", "ecommerce", "lottery", "remote_work", "loans", "other"]

TOPIC_POOL = {
    "invest_crypto": dict(
        obj=["platforma inwestycyjna do handlu bitcoin", "automatyczny robot tradingowy na kryptowalutach",
             "inwestycje w kryptowaluty i akcje", "system giełdowy oparty na sztucznej inteligencji"],
        gain=["stały pasywny dochód z inwestycji", "zyski z krypto każdego dnia", "wysokie odsetki od zainwestowanego kapitału"]),
    "health": dict(
        obj=["suplement diety na odchudzanie", "naturalna kuracja na bóle stawów", "preparat na ciśnienie i cholesterol",
             "krople wzmacniające wzrok"],
        gain=["lepsze zdrowie i samopoczucie", "szybką utratę wagi bez diety", "ulgę w bólu już po tygodniu"]),
    "institution": dict(
        obj=["weryfikacja konta bankowego", "zwrot nadpłaty podatku z urzędu skarbowego",
             "aktualizacja danych w serwisie bankowości internetowej", "odblokowanie karty płatniczej"],
        gain=["pełny dostęp do konta", "zwrot środków na rachunek", "ochronę przed zablokowaniem konta"]),
    "ecommerce": dict(
        obj=["wyprzedaż elektroniki i smartfonów", "tanie meble ogrodowe", "oryginalne buty sportowe", "robot sprzątający"],
        gain=["rabat do 70 procent na cały asortyment", "darmową dostawę do domu", "cenę niższą niż w sklepach"]),
    "lottery": dict(
        obj=["loteria z nagrodami dla klientów", "konkurs z nagrodą główną", "losowanie nowego smartfona", "ankieta z kartą podarunkową"],
        gain=["nagrodę główną o wartości kilku tysięcy złotych", "szansę na wygraną już dziś", "kartę podarunkową bez opłat"]),
    "remote_work": dict(
        obj=["praca zdalna z domu", "dorabianie online w wolnym czasie", "etat na odległość w międzynarodowej firmie",
             "zlecenia przez internet"],
        gain=["wypłatę co tydzień", "elastyczne godziny i dobre zarobki", "dodatkowe zarobki bez doświadczenia"]),
    "loans": dict(
        obj=["pożyczka bez zaświadczeń i BIK", "dotacja na rozwój małej firmy", "kredyt gotówkowy online",
             "szybka pożyczka ratalna"],
        gain=["pieniądze na koncie w 15 minut", "środki bez zbędnych formalności", "niskie raty i wysoką zdolność"]),
    "other": dict(
        obj=["kurs gotowania dla początkujących", "bilety na koncert w twoim mieście", "serwis rowerowy", "kurs języka angielskiego"],
        gain=["nowe umiejętności", "miły wieczór w dobrym towarzystwie", "profesjonalną obsługę"]),
}

# five persuasion templates: (move order, {move: [frame alt0, frame alt1]})
TEMPLATES: dict[str, tuple[list[str], dict[str, list[str]]]] = {
    "T1": (["authority", "scarcity", "social_proof", "urgency", "cta"], {
        "authority": ["{name} ujawnia sekret: {obj} to {gain}.", "Znana osoba, {name}, zdradza, jak {obj} daje {gain}."],
        "scarcity": ["Dostępne tylko dla pierwszych 100 osób, potem koniec.", "Liczba wolnych miejsc jest mocno ograniczona i szybko maleje."],
        "social_proof": ["Już ponad 12 000 Polaków skorzystało i dziękuje w komentarzach.", "Tysiące zadowolonych osób potwierdza, że to naprawdę działa."],
        "urgency": ["Zrób to dzisiaj, zanim oferta zniknie o północy.", "Nie zwlekaj, oferta wygasa jeszcze dziś."],
        "cta": ["Kliknij i sprawdź na {domain}.", "Wejdź na {domain} i zacznij od razu."]}),
    "T2": (["hook", "social_proof", "authority", "scarcity", "cta"], {
        "hook": ["Media milczą na ten temat: {obj} i {gain}!", "Tego nie pokażą w telewizji: {obj}, czyli {gain}."],
        "social_proof": ["Setki komentarzy pod filmem to potwierdzają.", "Zobacz opinie osób, które już spróbowały."],
        "authority": ["Eksperci związani z {name} nazywają to przełomem.", "{name} osobiście poleca to rozwiązanie."],
        "scarcity": ["Zostało zaledwie kilka wolnych kodów dostępu.", "Pula dostępnych kodów kończy się, a chętnych przybywa."],
        "cta": ["Odbierz dostęp: {domain}", "Zarezerwuj swoje miejsce na {domain}"]}),
    "T3": (["story", "authority", "social_proof", "urgency", "cta"], {
        "story": ["Byłem w szoku, gdy {name} pokazał mi, że {obj} daje {gain}.", "Nie wierzyłam własnym oczom, kiedy {name} wyjaśnił, jak {obj} zapewnia {gain}."],
        "authority": ["To jest legalne i sprawdzone przez prawników.", "Całość została potwierdzona przez niezależnych specjalistów."],
        "social_proof": ["Moi znajomi też już z tego korzystają.", "Sąsiedzi i rodzina zaczęli tak samo."],
        "urgency": ["Promocja kończy się za kilka godzin.", "Termin mija dziś wieczorem."],
        "cta": ["Szczegóły znajdziesz tutaj: {domain}", "Zobacz jak to zrobić: {domain}"]}),
    "T4": (["urgency", "authority", "scarcity", "social_proof", "cta"], {
        "urgency": ["PILNE! Ostatnie godziny: {obj}.", "Ostrzeżenie: czas na skorzystanie z oferty ({obj}) dobiega końca."],
        "authority": ["Oficjalny komunikat z udziałem {name}.", "Zgodnie ze stanowiskiem {name} sprawa jest pilna."],
        "scarcity": ["Tylko 50 wolnych miejsc w tej edycji.", "Edycja jest limitowana do kilkudziesięciu osób."],
        "social_proof": ["Zaufało nam już 30 000 klientów w całym kraju.", "Ponad trzydzieści tysięcy osób wybrało to rozwiązanie."],
        "cta": ["Aktywuj teraz: {domain}", "Przejdź do formularza: {domain}"]}),
    "T5": (["hook", "authority", "social_proof", "scarcity", "urgency", "cta"], {
        "hook": ["Czy wiesz, że {gain} to nie przypadek?", "Dlaczego nikt nie mówi o tym, że {gain} jest tak blisko?"],
        "authority": ["Prowadzący {name} wyjaśnia mechanizm krok po kroku.", "{name} pokazuje, jak działa {obj}."],
        "social_proof": ["Zobacz wpisy dziękczynne od uczestników.", "Uczestnicy dzielą się wynikami w komentarzach."],
        "scarcity": ["Rejestracja jest otwarta dla ograniczonej grupy.", "Zapisy obejmują tylko wąskie grono osób."],
        "urgency": ["Dziś ostatni dzień zapisów.", "Rejestracja zamyka się o północy."],
        "cta": ["Zapisz się na {domain}", "Dołącz teraz: {domain}"]}),
}

SYNONYMS = {"dzisiaj": "dziś", "szybko": "błyskawicznie", "tylko": "jedynie", "teraz": "natychmiast",
            "ponad": "więcej niż", "zadowolonych": "usatysfakcjonowanych", "sprawdź": "zobacz", "kliknij": "naciśnij",
            "oferta": "propozycja", "zacznij": "rozpocznij", "pierwszych": "najszybszych"}

BG_FRAMES = [
    "Sprawdź naszą ofertę: {obj}. Oferujemy {gain}.", "{brand} zaprasza: {obj}. Zyskaj {gain}.",
    "Nowość w {brand}! {obj} i {gain}.", "{obj}, czyli {gain}. Szczegóły w regulaminie.",
    "Poznaj {brand}: {obj}. Zapraszamy w godzinach otwarcia.", "Promocja w {brand} trwa do niedzieli, w ofercie: {obj}.",
    "Dołącz do klientów {brand} i zyskaj {gain}.", "{brand}: {obj} z gwarancją, a do tego {gain}.",
    "Obserwuj {brand} i bądź na bieżąco, mamy dla Ciebie {obj}.", "W {brand} znajdziesz {obj}. Zapytaj o {gain}.",
]
FREE_POOL = [
    "Tylko dziś {gain}!", "Nie przegap szansy na {obj}.", "Ludzie nie mogą uwierzyć, ile da się zyskać: {gain}.",
    "Sekretny sposób na {obj} ujawniony.", "Zapytaj eksperta o {obj}.", "Wynik, który zaskoczył wszystkich: {gain}.",
    "Jedno kliknięcie dzieli Cię od {gain}.", "Zobacz, co mówią o {obj} nasi klienci.", "Bezpłatna konsultacja w sprawie {obj}.",
    "Koniec z przepłacaniem, wybierz {obj}.", "To działa, a {gain} są na wyciągnięcie ręki.", "Przeczytaj, zanim zdecydujesz o {obj}.",
]
BRANDS = ["Nowak i Synowie", "Zielony Dom", "Mar-Tech", "Studio Lumen", "Kawiarnia Pod Dębem", "Sklep Kolorowy", "Fundusz Alfa",
          "Optyk Widok", "Księgarnia Strona", "Warsztat Rower+", "Szkoła Lingua", "Bank Przykładowy", "Apteka Zdrowa Fikcja",
          "Meble Kwadrat", "Pożyczki Wzorcowe", "Loteria Fikcja", "Salon Moda", "Biuro Rachunkowe Liczba"]
NAMES_FICT = ["Anna Testowska", "Jan Przykładowski", "Marek Fikcyjny", "Ewa Wymyślona", "Piotr Nieistniejący",
              "Karolina Syntetyczna", "Osoba Publiczna A", "Osoba Publiczna B"]
WORDS = ["szybki", "super", "mega", "złoty", "pewny", "nowy", "smart", "eko", "profit", "zysk", "start", "plus", "net", "max"]
UTC = UTC
EPOCH = datetime(2026, 9, 1, tzinfo=UTC)


def _fill(frame: str, d: dict) -> str:
    return frame.format(**d)


def _syn(text: str, rng: random.Random, p: float) -> str:
    out = []
    for w in text.split(" "):
        base = w.strip(".,!?:").lower()
        if base in SYNONYMS and rng.random() < p:
            out.append(w.lower().replace(base, SYNONYMS[base]))
        else:
            out.append(w)
    return " ".join(out)


def _rand_domain(rng: random.Random, tag: str = "") -> str:
    return f"{rng.choice(WORDS)}-{rng.choice(WORDS)}{rng.randint(1, 999)}{tag}.example"


def _times(n: int, profile: str, start: datetime, rng: random.Random) -> list[datetime]:
    if profile == "spike":
        offs = [rng.uniform(0, 2) for _ in range(n)]
    elif profile == "ramp":
        offs = [10 * rng.random() ** 0.5 for _ in range(n)]
    else:
        offs = [rng.choice([0, 6, 12]) + rng.uniform(0, 1.5) for _ in range(n)]
    return sorted(start + timedelta(days=o) for o in offs)


def make_campaign_ads(spec: CampaignSpec, rng: random.Random) -> list[Ad]:
    order, frames = TEMPLATES[spec.template_id]
    times = _times(spec.n_variants, spec.burst_profile, spec.start, rng)
    ads: list[Ad] = []
    for i, t in enumerate(times):
        topic = spec.topics[i % len(spec.topics)]
        pool = TOPIC_POOL[topic]
        name = spec.names[rng.randrange(len(spec.names))]
        dom_idx = min(int((t - spec.start).days // 3), len(spec.domains) - 1)
        slots = dict(name=name, obj=rng.choice(pool["obj"]), gain=rng.choice(pool["gain"]), domain=spec.domains[dom_idx])
        moves = list(order)
        if spec.paraphrase_level == 2 and rng.random() < 0.3:
            k = rng.randrange(len(moves) - 1)
            moves[k], moves[k + 1] = moves[k + 1], moves[k]
        parts = []
        for m in moves:
            alt = 0 if spec.paraphrase_level == 0 else (rng.randrange(2) if spec.paraphrase_level == 1 and rng.random() < 0.2 else
                                                         (rng.randrange(2) if spec.paraphrase_level == 2 else 0))
            parts.append(_fill(frames[m][alt], slots))
        text = " ".join(parts)
        if spec.paraphrase_level:
            text = _syn(text, rng, 0.4 if spec.paraphrase_level == 1 else 0.8)
        ads.append(Ad(
            ad_id=f"synthetic_campaign:{spec.campaign_id}-{i:04d}", source="synthetic_campaign", first_seen_at=t,
            delivery_start=t, page_id=rng.choice(spec.advertisers), page_name=None, body=text,
            link_caption=slots["domain"], lang="pl", truth_campaign=spec.campaign_id, truth_topic=topic,
            truth_template=spec.template_id, meta={"split": spec.split, "kind": "campaign"}))
    # cloaking decoys: other topics, no template, same infrastructure
    for j in range(spec.cloaking_decoys):
        topic = rng.choice([t for t in TOPICS if t not in spec.topics] or TOPICS)
        pool = TOPIC_POOL[topic]
        t = spec.start + timedelta(days=rng.uniform(0, 8))
        text = _fill(rng.choice(BG_FRAMES), dict(brand=rng.choice(BRANDS), obj=rng.choice(pool["obj"]), gain=rng.choice(pool["gain"])))
        ads.append(Ad(
            ad_id=f"synthetic_control:decoy-{spec.campaign_id}-{j:03d}", source="synthetic_control", first_seen_at=t,
            delivery_start=t, page_id=rng.choice(spec.advertisers), body=text, link_caption=rng.choice(spec.domains), lang="pl",
            truth_topic=topic, meta={"split": spec.split, "kind": "decoy", "decoy_of": spec.campaign_id}))
    return ads


def llm_rewrite(specs: list[CampaignSpec], camp: list[Ad], rng: random.Random, n_base: int = 2, n_para: int = 3) -> None:
    """Replace rule-based bodies by LLM text (C3: generator differs from the analysis encoder). Ground truth unchanged.

    Per (campaign, topic, name) we draw n_base originals, then n_para paraphrases of them at the campaign's level.
    """
    from .prompts import llm_generate, paraphrase_prompt, variant_prompt

    spec_by = {s.campaign_id: s for s in specs}
    pools: dict[tuple, list[str]] = {}
    for a in camp:
        if not a.truth_campaign:
            continue
        sp = spec_by[a.truth_campaign]
        name = a.named_entities[0] if a.named_entities else sp.names[0]
        key = (sp.campaign_id, a.truth_topic)
        if key not in pools:
            texts = [llm_generate(variant_prompt(sp.schema_moves, a.truth_topic, sp.names[0]), 0.9 + 0.05 * k) for k in range(n_base)]
            if sp.paraphrase_level:
                texts += [llm_generate(paraphrase_prompt(rng.choice(texts), sp.paraphrase_level), 1.0) for _ in range(n_para)]
            pools[key] = texts
        body = rng.choice(pools[key]).replace("{DOMAIN}", a.link_caption or "")
        if a.link_caption and a.link_caption not in body:
            body += f" {a.link_caption}"
        a.body = body
        a.meta["generator"] = "llm"


def make_specs(n: int, dev_fraction: float, variants: tuple[int, int], rng: random.Random) -> list[CampaignSpec]:
    specs = []
    tids = list(TEMPLATES)
    for c in range(n):
        tid = tids[c % len(tids)]
        n_topics = rng.choice([3, 4, 5, 6])
        topics = rng.sample(TOPICS[:-1] if rng.random() < 0.7 else TOPICS, n_topics)
        n_dom = rng.randint(3, 6)
        specs.append(CampaignSpec(
            campaign_id=f"C{c:02d}", template_id=tid, schema_moves=TEMPLATES[tid][0], topics=topics,
            names=rng.sample(NAMES_FICT, 3), n_variants=rng.randint(*variants), paraphrase_level=rng.choice([0, 1, 1, 2]),
            domains=[_rand_domain(rng) for _ in range(n_dom)], advertisers=[f"PX{rng.randint(10**5, 10**6)}" for _ in range(rng.randint(2, 5))],
            start=EPOCH + timedelta(days=rng.uniform(0, 60)), burst_profile=rng.choice(["spike", "ramp", "pulse"]),
            cloaking_decoys=rng.choice([0, 0, 5, 12])))
    order = list(range(n))
    rng.shuffle(order)
    n_dev = int(round(dev_fraction * n))
    for k, idx in enumerate(order):
        specs[idx].split = "dev" if k < n_dev else "test"
    return specs


def make_controls(n: int, rng: random.Random) -> list[Ad]:
    """C1: same generator family, each ad has its own random skeleton (no shared template)."""
    ads = []
    for i in range(n):
        topic = rng.choice(TOPICS[:-1])
        pool = TOPIC_POOL[topic]
        k = rng.randint(3, 5)
        text = " ".join(_fill(f, dict(obj=rng.choice(pool["obj"]), gain=rng.choice(pool["gain"]))) for f in rng.sample(FREE_POOL, k))
        t = EPOCH + timedelta(days=rng.uniform(0, 80))
        ads.append(Ad(ad_id=f"synthetic_control:c1-{i:04d}", source="synthetic_control", first_seen_at=t, delivery_start=t,
                      page_id=f"PY{rng.randint(10**5, 10**6)}", body=text, link_caption=_rand_domain(rng, "c"), lang="pl",
                      truth_topic=topic, meta={"split": rng.choice(["dev", "test"]), "kind": "c1"}))
    return ads


def make_background(n: int, rng: random.Random) -> list[Ad]:
    ads = []
    brand_dom = {b: f"{b.lower().replace(' ', '').replace('+', 'plus')}.example" for b in BRANDS}
    brand_pid = {b: f"PB{1000 + i}" for i, b in enumerate(BRANDS)}
    weights = [2, 2, 2, 3, 1, 1, 2, 3]
    for i in range(n):
        topic = rng.choices(TOPICS, weights)[0]
        pool = TOPIC_POOL[topic]
        brand = rng.choice(BRANDS)
        k = rng.choice([1, 2, 2, 3])
        text = " ".join(_fill(f, dict(brand=brand, obj=rng.choice(pool["obj"]), gain=rng.choice(pool["gain"])))
                        for f in rng.sample(BG_FRAMES, k))
        t = EPOCH + timedelta(days=rng.uniform(0, 90))
        r = rng.random()
        ads.append(Ad(ad_id=f"synthetic_background:{i:05d}", source="synthetic_background", first_seen_at=t, delivery_start=t,
                      page_id=brand_pid[brand], page_name=brand, body=text, link_caption=brand_dom[brand], lang="pl",
                      truth_topic=topic, meta={"split": "fit" if r < 0.4 else ("dev" if r < 0.7 else "test"), "kind": "background"}))
    return ads


def simulate_cert(ads: list[Ad], rng: np.random.Generator, mu: float, sigma: float, p_listed: float = 0.7, p_deleted: float = 0.1) -> list[dict]:
    """SIMULATION: CERT insert date = first appearance of the domain + LogNormal(mu, sigma) days."""
    first: dict[str, datetime] = {}
    for a in ads:
        if a.truth_campaign and a.link_caption:
            first[a.link_caption] = min(first.get(a.link_caption, a.t), a.t)
    out = []
    for d in sorted(first):
        if rng.random() < p_listed:
            ins = first[d] + timedelta(days=float(rng.lognormal(mu, sigma)))
            dele = ins + timedelta(days=30) if rng.random() < p_deleted else None
            out.append({"domain": d, "insert_date": ins.isoformat(), "delete_date": dele.isoformat() if dele else None, "simulated": True})
    return out


def generate_all(seed: int, n_campaigns: int, dev_fraction: float, variants: tuple[int, int], n_background: int, n_controls: int,
                 mu: float = 1.6, sigma: float = 0.6, generator: str = "rule"):
    rng = random.Random(seed)
    specs = make_specs(n_campaigns, dev_fraction, variants, rng)
    camp: list[Ad] = []
    for s in specs:
        camp += make_campaign_ads(s, rng)
    if generator == "llm":
        llm_rewrite(specs, camp, rng)
    controls = make_controls(n_controls, rng)
    bg = make_background(n_background, rng)
    cert = simulate_cert(camp, np.random.default_rng(seed), mu, sigma)
    return specs, camp, controls, bg, cert


def write_jsonl(path: str | Path, ads: list[Ad]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.writelines(a.model_dump_json() + "\n" for a in ads)


def write_fixtures(out_dir: str | Path, seed: int = 1, **kw) -> dict:
    out = Path(out_dir)
    specs, camp, controls, bg, cert = generate_all(seed, **kw)
    write_jsonl(out / "synth.jsonl", camp + controls)
    write_jsonl(out / "ads_background.jsonl", bg)
    (out / "campaigns.json").write_text(json.dumps([s.model_dump(mode="json") for s in specs], indent=1, ensure_ascii=False))
    (out / "cert_sample.json").write_text(json.dumps({"note": "SIMULATED", "domains": cert}, indent=1))
    return {"campaign_ads": len(camp), "controls": len(controls), "background": len(bg), "cert": len(cert)}
