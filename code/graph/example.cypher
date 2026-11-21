// Przykład na FIKCYJNYCH danych (domeny .example), żeby zobaczyć schemat w Neo4j Browser.
// Odwzorowuje typową sytuację: dwa duplikaty na różnych domenach (A, B) i trzeci materiał (C) z innym przekazem,
// ale tym samym zestawem strony i schematem adresów (= ten sam operator). Materiał D jest niezależny.
// Czyszczenie przykładu: MATCH (n) WHERE n.demo = true DETACH DELETE n;

MERGE (a:Material {id: 'A'}) SET a.demo = true, a.name = 'Reklama A', a.source = 'folder', a.title = 'Szokujące wyznanie znanej osoby', a.observed_at = datetime('2026-10-09T08:24:00')
MERGE (b:Material {id: 'B'}) SET b.demo = true, b.name = 'Reklama B', b.source = 'folder', b.title = 'Szokujące wyznanie znanej osoby', b.observed_at = datetime('2026-10-09T09:10:00')
MERGE (c:Material {id: 'C'}) SET c.demo = true, c.name = 'Reklama C', c.source = 'folder', c.title = 'Prezenterka po ataku przerywa milczenie', c.observed_at = datetime('2026-10-09T10:47:00')
MERGE (d:Material {id: 'D'}) SET d.demo = true, d.name = 'Reklama D', d.source = 'folder', d.title = 'Cudowny lek na stawy', d.observed_at = datetime('2026-10-20T14:00:00')

// wspólne ślady
MERGE (px:Tracker {id: 'meta:1111111111111111'}) SET px.demo = true, px.kind = 'meta_pixel', px.name = 'piksel Meta 1111…'
MERGE (kit:PageKit {prefix: '/_cdn/production/landing-cdn'}) SET kit.demo = true, kit.name = 'zestaw /_cdn/production/landing-cdn'
MERGE (tds:UrlScheme {fingerprint: 'utm_id:20|utm_medium:10|utm_campaign:10|utm_content:10|utm_visit:uuid'}) SET tds.demo = true, tds.name = 'schemat utm_* (TDS)'
MERGE (p1:Person {name: 'Znana Osoba'}) SET p1.demo = true
MERGE (p2:Person {name: 'Prezenterka TV'}) SET p2.demo = true
MERGE (br:Brand {name: 'Podrobiony Portal'}) SET br.demo = true
MERGE (prod:Product {name: 'Lek X'}) SET prod.demo = true

MERGE (da:Domain {name: 'civic-news.example'})  SET da.demo = true, da.registered = datetime('2026-10-08T21:02:00')
MERGE (db:Domain {name: 'across-news.example'}) SET db.demo = true, db.registered = datetime('2026-10-08T21:03:00')
MERGE (dc:Domain {name: 'health-link.example'}) SET dc.demo = true, dc.registered = datetime('2026-10-08T22:40:00')
MERGE (dd:Domain {name: 'stawy-shop.example'})  SET dd.demo = true, dd.registered = datetime('2026-09-01T10:00:00')
MERGE (reg:Registrar {name: 'Rejestrator 1'}) SET reg.demo = true
MERGE (da)-[:REGISTERED_AT]->(reg)
MERGE (db)-[:REGISTERED_AT]->(reg)
MERGE (db)-[:REDIRECTS_TO]->(dc)

MERGE (a)-[:LANDS_ON]->(da)   MERGE (b)-[:LANDS_ON]->(db)   MERGE (c)-[:LANDS_ON]->(dc)   MERGE (d)-[:LANDS_ON]->(dd)
MERGE (b)-[:REDIRECTS_THROUGH {hop: 1}]->(dc)
MERGE (a)-[:USES_TRACKER]->(px)  MERGE (b)-[:USES_TRACKER]->(px)
MERGE (a)-[:USES_KIT]->(kit)     MERGE (b)-[:USES_KIT]->(kit)     MERGE (c)-[:USES_KIT]->(kit)
MERGE (a)-[:USES_URL_SCHEME]->(tds) MERGE (b)-[:USES_URL_SCHEME]->(tds) MERGE (c)-[:USES_URL_SCHEME]->(tds)
MERGE (a)-[:MENTIONS {count: 4}]->(p1) MERGE (b)-[:MENTIONS {count: 4}]->(p1) MERGE (c)-[:MENTIONS {count: 6}]->(p2)
MERGE (a)-[:IMPERSONATES]->(br) MERGE (b)-[:IMPERSONATES]->(br)
MERGE (d)-[:PROMOTES]->(prod)

// wynik porównania (liczony w Pythonie) z przesłankami
MERGE (a)-[s1:SIMILAR]->(b) SET s1.score = 1.0, s1.relation = 'duplikat',
  s1.channels = ['śledzenie', 'tekst', 'szablon'], s1.reasons = ['ten sam piksel Meta', 'identyczny tytuł', 'ten sam zestaw strony']
MERGE (b)-[s2:SIMILAR]->(c) SET s2.score = 0.99, s2.relation = 'ta sama infrastruktura',
  s2.channels = ['adres', 'szablon'], s2.reasons = ['przekierowanie na tę samą domenę', 'ten sam schemat utm_*', 'ten sam zestaw strony']

MERGE (k1:Campaign {id: 'K1'}) SET k1.demo = true, k1.name = 'K1: Szokujące wyznanie'
MERGE (k2:Campaign {id: 'K2'}) SET k2.demo = true, k2.name = 'K2: Prezenterka po ataku'
MERGE (k3:Campaign {id: 'K3'}) SET k3.demo = true, k3.name = 'K3: Lek na stawy'
MERGE (s:Network {id: 'S1'}) SET s.demo = true, s.name = 'Sieć S1'
MERGE (a)-[:IN_CAMPAIGN {score: 1.0}]->(k1) MERGE (b)-[:IN_CAMPAIGN {score: 1.0}]->(k1)
MERGE (c)-[:IN_CAMPAIGN {score: 1.0}]->(k2) MERGE (d)-[:IN_CAMPAIGN {score: 1.0}]->(k3)
MERGE (k1)-[:IN_NETWORK]->(s) MERGE (k2)-[:IN_NETWORK]->(s);
