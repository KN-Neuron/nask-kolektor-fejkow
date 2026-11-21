// Zapytania o twórców (węzeł :Creator z graph/creators.py). Wklejaj pojedynczo do Neo4j Browser.

// 1. Twórca jako obrazek: strony, płatnicy i domeny jednego twórcy (zmień nazwę strony)
MATCH (adv:Advertiser {name: 'Sharon Coleman'})-[:PART_OF]->(c:Creator)
MATCH p = (c)<-[:PART_OF]-(x)
RETURN p;

// 2. Co odróżnia twórcę A od B: wspólne ślady i ślady tylko jednego z nich (zmień obie nazwy stron)
MATCH (:Advertiser {name: 'Sharon Coleman'})-[:PART_OF]->(a:Creator), (:Advertiser {name: 'Evelyn Johnson'})-[:PART_OF]->(b:Creator)
UNWIND ['PAID_BY', 'LINKS_TO', 'ABOUT', 'MENTIONS', 'BY'] AS rel
CALL (a, b, rel) {
  MATCH (a)<-[:CREATED_BY]-(:Ad)-[r]->(x) WHERE type(r) = rel WITH collect(DISTINCT x.name) AS xa
  MATCH (b)<-[:CREATED_BY]-(:Ad)-[r]->(y) WHERE type(r) = rel WITH xa, collect(DISTINCT y.name) AS yb
  RETURN [v IN xa WHERE v IN yb] AS wspólne, [v IN xa WHERE NOT v IN yb] AS tylko_A, [v IN yb WHERE NOT v IN xa] AS tylko_B
}
RETURN rel AS ślad, wspólne, tylko_A[..10] AS tylko_A, tylko_B[..10] AS tylko_B;

// 3. Profil twórcy liczbami: skala, odsetek zdjętych, okres działania, platformy
MATCH (c:Creator)<-[:CREATED_BY]-(a:Ad)
WHERE c.label = 'scam' AND c.n_ads >= 10
RETURN c.name AS twórca, c.n_ads AS reklam, round(c.scam_share, 2) AS zdjętych, c.n_pages AS stron, c.n_payers AS płatników,
       min(a.delivery_start) AS od, max(a.delivery_start) AS do, count(DISTINCT a.text_hash) AS różnych_tekstów
ORDER BY reklam DESC LIMIT 25;

// 4. Propagacja: reklamy, których Meta NIE zdjęła, ale ich twórca to scam (kandydaci, których Meta przeoczyła)
MATCH (a:Ad {label: 'scam', label_source: 'twórca'})-[:CREATED_BY]->(c:Creator)
RETURN c.name AS twórca, round(c.scam_share, 2) AS zdjętych_u_twórcy, a.title AS tytuł, left(a.body, 120) AS tekst, a.library_url AS link
LIMIT 25;

// 5. Twórcy z wieloma stronami (ten sam płatnik/domena/tekst sklejają strony): typowy obraz siatki kont
MATCH (c:Creator) WHERE c.n_pages >= 3 AND c.label = 'scam'
MATCH p = (c)<-[:PART_OF]-(:Advertiser)
RETURN p LIMIT 300;

// 6. Przypadek NASK -> twórca z Mety
MATCH p = (m:Material)-[:CREATED_BY]->(c:Creator)<-[:PART_OF]-(x)
RETURN p;
