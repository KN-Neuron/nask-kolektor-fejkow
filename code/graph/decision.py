"""Kontrakt decyzji zapisywanej w grafie: kampania, operator i konto reklamowe to TRZY różne rzeczy.

Wcześniej scraper wpisywał ten sam identyfikator twórcy w pole grupy (kampania) i operatora, więc jeden operator nie mógł mieć dwóch
kampanii. Teraz:

  kampania   `Campaign` (id `kam:<operator>#<skrót>`): ten sam przekaz. Wiele kampanii może mieć jednego operatora.
  operator   `Creator`: ten, kto stoi za reklamami (strony, płatnicy, domeny, identyczne teksty).
  konto      `Advertiser` (strona reklamodawcy, id `fb:<page_id>`) albo `AdAccount`: z czego reklama poszła. Zapisane osobno, nigdy
             jako kampania ani operator.

W grafie (dla każdego materiału, w JEDNEJ transakcji):

  (n)-[:CREATED_BY {source, method}]->(Creator)        operator
  (n)-[:IN_CAMPAIGN {source, method, score}]->(Campaign)-[:RUN_BY]->(Creator)
  (n)-[:HAS_DECISION]->(d:Decision)                    d: verdict, source, method, score, text, at, campaign_id, operator_id, account_id
  (d)-[:CAMPAIGN]->(Campaign), (d)-[:OPERATOR]->(Creator), (d)-[:ACCOUNT]->(Advertiser)
  (d)-[:CONFLICTS_WITH]->(Creator)                     gdy dokładna zgodność wskazała kilku twórców (do weryfikacji)
  (n)-[:SIMILAR_TO {score, operator_score, channels, reasons}]->(inne)   top-k z silnika

`method` to wersja metody (silnik + konfiguracja + wersja kontraktu), więc po zmianie progów stare decyzje zostają obok nowych.
Decyzja ma id z (materiał, metoda), więc ponowny zapis tego samego nic nie dubluje.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import provenance

CONTRACT = "graf-v2"
EXACT = """
MATCH (n:$label {id: $id})
CALL (n) {
  MATCH (n)-[r:BY|PAID_BY|LINKS_TO|ADVERTISED_BY|LANDS_ON]->(x)-[:PART_OF]->(c:Creator)
  RETURN c, type(r) + ': ' + x.name AS why
  UNION
  MATCH (b:Ad {text_hash: n.text_hash})-[:CREATED_BY]->(c:Creator) WHERE n.text_hash IS NOT NULL AND b <> n
  WITH c, count(b) AS k WHERE k <= 100
  RETURN c, 'identyczny tekst (' + k + ' reklam)' AS why
}
RETURN c.id AS creator, c.name AS name, collect(DISTINCT why) AS why
ORDER BY size(why) DESC, c.id
"""
HUB_OF = {"host": "Domain {name: x}", "kit": "PageKit {prefix: x}", "scheme": "UrlScheme {fingerprint: x}"}


def q(cypher: str, label: str) -> str:
    return cypher.replace("$label", label)  # etykieta nie może być parametrem Cyphera; tu tylko "Ad" albo "Material"


@dataclass
class DecisionRecord:
    label: str                  # "Ad" | "Material"
    node_id: str
    verdict: str                # werdykt silnika po poprawce grafu (hub -> nowy_wzorzec)
    campaign_id: str
    operator_id: str
    operator_name: str
    account_id: str | None
    source: str                 # skąd wiemy: dokładna zgodność / podobieństwo / nowy wzorzec
    method: str
    score: float
    text: str = ""
    new_campaign: bool = False
    new_operator: bool = False
    conflicts: list[str] = field(default_factory=list)   # inni twórcy pasujący dokładnie (do weryfikacji)
    matches: list[dict] = field(default_factory=list)

    @property
    def decision_id(self) -> str:
        return hashlib.sha1(f"{self.label}:{self.node_id}|{self.method}".encode()).hexdigest()[:16]


def method_version(gallery) -> str:
    """Wersja metody: silnik, jego konfiguracja i profil progów, wersja kontraktu zapisu."""
    cfg = getattr(getattr(gallery, "cfg", None), "name", None) or "embsim"
    return f"embsim:{cfg}:{getattr(gallery, 'profile', None) or 'domyślny'}|{CONTRACT}"


def campaign_of(group: str | None, operator: str | None) -> str | None:
    """Stare galerie miały w polu grupy id twórcy (`tw:…`); to jest kampania domyślna tego twórcy."""
    if not group:
        return None
    return group if group.startswith("kam:") else f"kam:{group}#0"


def new_campaign_id(operator: str, node_id: str) -> str:
    return f"kam:{operator}#{hashlib.sha1(node_id.encode()).hexdigest()[:8]}"


def only_hubs(session, m) -> list[str]:
    """Pospolite ślady (hub w grafie), jeśli to JEDYNE, co łączy z najbliższym materiałem; inaczej pusta lista.
    Silnik embsim potrafi dać 0,95 za samo wspólne google.com; graf wie, że to hub, więc takiego połączenia nie przyjmujemy."""
    chans = {k for k, v in m.channels.items() if v > 0}
    if not chans or not chans <= set(HUB_OF):
        return []
    hubs = []
    for ch in chans:
        vals = m.shared.get(ch, [])
        if not vals:
            return []
        n = session.run(f"UNWIND $v AS x MATCH (h:{HUB_OF[ch]}) WHERE h.hub RETURN count(h) AS n", v=vals).single()["n"]
        if n < len(vals):
            return []
        hubs += vals
    return hubs


def _key_match(d):
    km = getattr(d, "key_match", None)           # nowsze embsim: materiał, który rozstrzygnął decyzję
    if km is not None:
        return km()
    if not d.matches:
        return None
    return d.matches[0] if d.verdict == "znana_kampania" else max(d.matches, key=lambda m: m.operator_score)


def resolve(session, label: str, node_id: str, d, *, gallery_campaign: dict, gallery_operator: dict, account: str | None,
            method: str, matches: list[dict]) -> DecisionRecord:
    """Z wyniku silnika i dokładnych zgodności w grafie wybiera: kampanię, operatora i konto (osobno).

    Kolejność: dokładna zgodność z twórcą (mocniejszy dowód niż próg) rozstrzyga OPERATORA; kampanię wskazuje silnik, ale tylko wtedy,
    gdy należy do tego samego operatora. Inaczej to nowa kampania tego operatora."""
    exact = list(session.run(q(EXACT, label), id=node_id))
    best = _key_match(d) if d.verdict in ("znana_kampania", "znany_operator_nowa_kampania") and d.matches else None
    hubs = only_hubs(session, best) if best else []
    if hubs:
        best = None
    verdict = d.verdict
    eng_campaign = campaign_of(gallery_campaign.get(best.id), None) if best else None
    eng_operator = gallery_operator.get(best.id) if best else None
    conflicts: list[str] = []
    score = float(getattr(d, "campaign_score", 0.0) or 0.0)

    if exact:
        op, opname = exact[0]["creator"], exact[0]["name"]
        src = "dokładna zgodność: " + "; ".join(exact[0]["why"][:3])
        conflicts = [e["creator"] for e in exact[1:]]
        if conflicts:
            src += f" (uwaga: pasuje też do {len(conflicts)} innych twórców: do weryfikacji)"
        if verdict == "znana_kampania" and eng_campaign and eng_operator == op:
            camp, new_c = eng_campaign, False
        else:
            camp, new_c = new_campaign_id(op, node_id), True
            if verdict == "znana_kampania" and eng_operator and eng_operator != op:
                src += f"; silnik wskazał kampanię innego twórcy ({eng_operator}), więc to nowa kampania twórcy z dokładnej zgodności"
                conflicts.append(eng_operator)
        new_op = False
    elif best and eng_operator:
        op = eng_operator
        name = session.run("MATCH (c:Creator {id: $c}) RETURN c.name AS n", c=op).single()
        opname = name["n"] if name else op
        src = f"podobieństwo do {best.id} ({verdict.replace('_', ' ')})"
        if verdict == "znana_kampania" and eng_campaign:
            camp, new_c = eng_campaign, False
        else:
            camp, new_c = new_campaign_id(op, node_id), True
        new_op = False
    else:
        op, opname = f"tw:{node_id}", "nowy twórca"
        camp, new_c, new_op = new_campaign_id(op, node_id), True, True
        if hubs:
            src = f"nowy wzorzec: silnik łączył z {best_id(d)} tylko przez pospolity ślad ({', '.join(hubs[:3])}), więc to pomijamy"
        else:
            src = "nowy wzorzec: brak dokładnej zgodności i podobnego materiału"
        verdict = "nowy_wzorzec"
        score = 0.0 if hubs else score
    if hubs:
        verdict = "nowy_wzorzec"
    return DecisionRecord(label=label, node_id=node_id, verdict=verdict, campaign_id=camp, operator_id=op, operator_name=opname,
                          account_id=account, source=src, method=method, score=round(score, 3), new_campaign=new_c,
                          new_operator=new_op, conflicts=conflicts, matches=matches)


def best_id(d) -> str:
    m = _key_match(d)
    return m.id if m else "?"


# --------------------------------------------------------------------------------------------------------------------
# zapis: jedna transakcja na materiał, powtarzalna bez skutków ubocznych

_ENSURE = """
MERGE (op:Creator {id: $operator})
  ON CREATE SET op.name = $operator_name, op.new = true, op.n_ads = 0, op.n_flagged = 0, op.label = 'brak sygnału', op.scam_share = 0.0
MERGE (camp:Campaign {id: $campaign})
  ON CREATE SET camp.origin = 'graf', camp.created_at = datetime(), camp.method = $method
MERGE (camp)-[:RUN_BY]->(op)
"""
_DETACH_OLD_OPERATOR = """
MATCH (n:$label {id: $id})-[old:CREATED_BY]->(p:Creator) WHERE p.id <> $operator
DELETE old RETURN collect(DISTINCT p.id) AS prev
"""
_LINK = """
MATCH (n:$label {id: $id}), (op:Creator {id: $operator}), (camp:Campaign {id: $campaign})
MERGE (n)-[cb:CREATED_BY]->(op) SET cb.source = $source, cb.method = $method, cb.at = datetime()
WITH n, camp
OPTIONAL MATCH (n)-[oc:IN_CAMPAIGN]->(:Campaign) WHERE oc.method IS NOT NULL
DELETE oc
WITH DISTINCT n, camp
MERGE (n)-[ic:IN_CAMPAIGN]->(camp) SET ic.source = $source, ic.method = $method, ic.score = $score, ic.at = datetime()
"""
_DECISION = """
MATCH (n:$label {id: $id}), (op:Creator {id: $operator}), (camp:Campaign {id: $campaign})
MERGE (d:Decision {id: $did})
  SET d.node_id = $id, d.node_label = $node_kind, d.verdict = $verdict, d.source = $source, d.method = $method, d.score = $score,
      d.text = $text, d.at = datetime(), d.campaign_id = $campaign, d.operator_id = $operator, d.account_id = $account,
      d.new_campaign = $new_campaign, d.new_operator = $new_operator, d.conflicts = $conflicts
MERGE (n)-[:HAS_DECISION]->(d)
WITH n, d, op, camp
OPTIONAL MATCH (d)-[old:CAMPAIGN|OPERATOR|ACCOUNT|CONFLICTS_WITH]->()
DELETE old
WITH DISTINCT n, d, op, camp
MERGE (d)-[:CAMPAIGN]->(camp)
MERGE (d)-[:OPERATOR]->(op)
SET n.verdict = $verdict, n.verdict_text = $text, n.creator_source = $source, n.added_at = coalesce(n.added_at, datetime()),
    n.method = $method
"""
_ACCOUNT = """
MATCH (d:Decision {id: $did})
OPTIONAL MATCH (a:Advertiser {key: $account})
OPTIONAL MATCH (b:AdAccount {id: $account})
WITH d, coalesce(a, b) AS acc WHERE acc IS NOT NULL
MERGE (d)-[:ACCOUNT]->(acc)
"""
_CONFLICTS = """
MATCH (d:Decision {id: $did}) UNWIND $conflicts AS cid MATCH (x:Creator {id: cid}) MERGE (d)-[:CONFLICTS_WITH]->(x)
"""
_SIMILAR = """
MATCH (n:$label {id: $id})
OPTIONAL MATCH (n)-[old:SIMILAR_TO]->() DELETE old
WITH DISTINCT n
UNWIND $matches AS m
CALL (m) { MATCH (o:Ad {id: m.id}) RETURN o UNION MATCH (o:Material {id: m.id}) RETURN o }
MERGE (n)-[s:SIMILAR_TO]->(o)
SET s.score = m.score, s.operator_score = m.operator_score, s.channels = m.channels, s.reasons = m.reasons
"""


def write_decision(tx, node_cypher: str, node_rows: list[dict], make_rec) -> DecisionRecord:
    """Zapisuje węzeł i decyzję w JEDNEJ transakcji (przy `session.execute_write`; sterownik powtarza ją przy błędach przejściowych).

    `make_rec(tx)` wybiera kampanię i operatora PO zapisie węzła (dokładne zgodności szukają jego krawędzi w grafie), ale w tej samej
    transakcji, więc przy błędzie nie zostaje ani węzeł, ani połowa decyzji.

    Liczniki twórcy liczone są z krawędzi (`provenance.refresh`), więc ponowienie, przepięcie do innego twórcy i dodanie nowego
    materiału zmieniają je tylko wtedy, gdy zmienił się zbiór reklam twórcy."""
    tx.run(node_cypher, rows=node_rows).consume()
    rec = make_rec(tx)
    lab = rec.label
    p = dict(id=rec.node_id, node_kind=lab, operator=rec.operator_id, operator_name=rec.operator_name, campaign=rec.campaign_id,
             method=rec.method, source=rec.source, score=rec.score, verdict=rec.verdict, text=rec.text, did=rec.decision_id,
             account=rec.account_id, new_campaign=rec.new_campaign, new_operator=rec.new_operator, conflicts=rec.conflicts)
    tx.run(_ENSURE, **p).consume()
    prev = tx.run(q(_DETACH_OLD_OPERATOR, lab), **p).single()["prev"]
    tx.run(q(_LINK, lab), **p).consume()
    tx.run(q(_DECISION, lab), **p).consume()
    if rec.account_id:
        tx.run(_ACCOUNT, **p).consume()
    if rec.conflicts:
        tx.run(_CONFLICTS, **p).consume()
    tx.run(q(_SIMILAR, lab), id=rec.node_id, matches=rec.matches).consume()
    touched = sorted({rec.operator_id, *prev, *rec.conflicts})
    provenance.refresh(tx.run, touched)
    return rec


def decided(session, label: str, ids: list[str], method: str) -> set[str]:
    """Rejestr przetworzonych: id materiałów, dla których w grafie jest już decyzja tej wersji metody."""
    if not ids:
        return set()
    dids = {hashlib.sha1(f"{label}:{i}|{method}".encode()).hexdigest()[:16]: i for i in ids}
    got = session.run("UNWIND $d AS x MATCH (d:Decision {id: x}) RETURN d.id AS id", d=list(dids)).value()
    return {dids[g] for g in got}
