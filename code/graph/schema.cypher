// Kolekcjoner Fejków: schemat bazy grafowej (Neo4j 5, Community).
// Uruchamianie: zob. docs/13_BAZA_GRAFOWA.md ("Jak odpalić"). Skrypt jest idempotentny (IF NOT EXISTS).
//
// Zasada: każdy ślad, który dwa materiały mogą mieć WSPÓLNY, jest osobnym węzłem.
// Dwa materiały podpięte do tego samego węzła = konkretna, sprawdzalna przesłanka powiązania.

// ---------- 1. Materiał i jego pliki ----------
CREATE CONSTRAINT material_id      IF NOT EXISTS FOR (n:Material)    REQUIRE n.id IS UNIQUE;     // jeden incydent / zgłoszenie
CREATE CONSTRAINT artifact_sha     IF NOT EXISTS FOR (n:Artifact)    REQUIRE n.sha256 IS UNIQUE; // plik (zrzut, HTML, HAR, wideo...)
CREATE CONSTRAINT imagehash_v      IF NOT EXISTS FOR (n:ImageHash)   REQUIRE n.phash IS UNIQUE;  // odcisk percepcyjny obrazu

// ---------- 2. Treść (co reklama mówi) ----------
CREATE CONSTRAINT person_name      IF NOT EXISTS FOR (n:Person)      REQUIRE n.name IS UNIQUE;   // osoba z bazy referencyjnej
CREATE CONSTRAINT product_name     IF NOT EXISTS FOR (n:Product)     REQUIRE n.name IS UNIQUE;   // "Metabo RX", "Uromexil Forte"
CREATE CONSTRAINT brand_name       IF NOT EXISTS FOR (n:Brand)       REQUIRE n.name IS UNIQUE;   // podrabiany portal / logo (TVN24...)
CREATE CONSTRAINT topic_name       IF NOT EXISTS FOR (n:Topic)       REQUIRE n.name IS UNIQUE;   // tematyka (inwestycje, zdrowie...)
CREATE CONSTRAINT contact_value    IF NOT EXISTS FOR (n:Contact)     REQUIRE n.value IS UNIQUE;  // telefon / e-mail / komunikator

// ---------- 3. Reklama (kto i gdzie ją kupił) ----------
CREATE CONSTRAINT ad_id            IF NOT EXISTS FOR (n:Ad)          REQUIRE n.id IS UNIQUE;     // ad_id Meta / id w Ad Library
CREATE CONSTRAINT advertiser_key   IF NOT EXISTS FOR (n:Advertiser)  REQUIRE n.key IS UNIQUE;    // page_id albo znormalizowana nazwa
CREATE CONSTRAINT payer_name       IF NOT EXISTS FOR (n:Payer)       REQUIRE n.name IS UNIQUE;   // płatnik z Ad Library (beneficiary_payers)
CREATE CONSTRAINT adaccount_id    IF NOT EXISTS FOR (n:AdAccount)   REQUIRE n.id IS UNIQUE;     // oznaczenie kupującego ruch (acc=...)
CREATE CONSTRAINT tracker_id       IF NOT EXISTS FOR (n:Tracker)     REQUIRE n.id IS UNIQUE;     // piksel Meta, AW-..., GTM-... (kind=...)

// ---------- 4. Strona i ruch (jak zbudowano wabik) ----------
CREATE CONSTRAINT domain_name      IF NOT EXISTS FOR (n:Domain)      REQUIRE n.name IS UNIQUE;   // domena rejestrowalna
CREATE CONSTRAINT urlscheme_fp     IF NOT EXISTS FOR (n:UrlScheme)   REQUIRE n.fingerprint IS UNIQUE; // odcisk parametrów (TDS)
CREATE CONSTRAINT pagekit_prefix   IF NOT EXISTS FOR (n:PageKit)     REQUIRE n.prefix IS UNIQUE; // zestaw strony (/_cdn/production/...)

// ---------- 5. Infrastruktura (bierne źródła: DNS, RDAP, crt.sh) ----------
CREATE CONSTRAINT registrar_name   IF NOT EXISTS FOR (n:Registrar)   REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT ip_addr          IF NOT EXISTS FOR (n:IP)          REQUIRE n.addr IS UNIQUE;
CREATE CONSTRAINT asn_number       IF NOT EXISTS FOR (n:ASN)         REQUIRE n.number IS UNIQUE;
CREATE CONSTRAINT cert_serial      IF NOT EXISTS FOR (n:Certificate) REQUIRE n.serial IS UNIQUE;

// ---------- 6. Wynik grupowania ----------
CREATE CONSTRAINT campaign_id      IF NOT EXISTS FOR (n:Campaign)    REQUIRE n.id IS UNIQUE;     // ten sam przekaz
CREATE CONSTRAINT network_id       IF NOT EXISTS FOR (n:Network)     REQUIRE n.id IS UNIQUE;     // ten sam operator (wspólna infra)
CREATE CONSTRAINT creator_id       IF NOT EXISTS FOR (n:Creator)     REQUIRE n.id IS UNIQUE;     // twórca: strony+płatnicy jednego operatora (graph/creators.py)

// ---------- Indeksy pomocnicze ----------
CREATE INDEX material_source   IF NOT EXISTS FOR (n:Material) ON (n.source);
CREATE INDEX artifact_kind     IF NOT EXISTS FOR (n:Artifact) ON (n.kind);
CREATE INDEX domain_registered IF NOT EXISTS FOR (n:Domain)   ON (n.registered);
CREATE INDEX ad_start          IF NOT EXISTS FOR (n:Ad)       ON (n.delivery_start);
CREATE FULLTEXT INDEX material_text IF NOT EXISTS FOR (n:Material) ON EACH [n.title, n.text, n.ocr_text];

// ---------- Indeksy wektorowe (embeddingi) ----------
// Wymiar zależy od modelu, który wybierzemy (1024 = np. jina-clip-v2). Zmiana modelu = DROP INDEX i założenie na nowo.
CREATE VECTOR INDEX material_embedding IF NOT EXISTS FOR (n:Material) ON n.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX artifact_embedding IF NOT EXISTS FOR (n:Artifact) ON n.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

// ---------- Unikalny tekst reklamy i jego embedding (Meta) ----------
// Wiele reklam ma identyczny tekst, więc wektor trzyma węzeł Text, a reklamy wskazują go przez HAS_TEXT.
CREATE CONSTRAINT text_hash IF NOT EXISTS FOR (n:Text) REQUIRE n.hash IS UNIQUE;
CREATE VECTOR INDEX text_embedding IF NOT EXISTS FOR (n:Text) ON n.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}};

// ---------- Decyzja grafu: kampania, operator i konto osobno (graph/decision.py) ----------
CREATE CONSTRAINT decision_id        IF NOT EXISTS FOR (n:Decision)        REQUIRE n.id IS UNIQUE;   // (materiał, wersja metody)
CREATE INDEX decision_node           IF NOT EXISTS FOR (n:Decision) ON (n.node_id);

// ---------- Pochodzenie etykiety scam (graph/provenance.py) ----------
CREATE CONSTRAINT labelevidence_id   IF NOT EXISTS FOR (n:LabelEvidence)   REQUIRE n.id IS UNIQUE;   // twórca|rodzaj dowodu
CREATE CONSTRAINT analystverdict_id  IF NOT EXISTS FOR (n:AnalystVerdict)  REQUIRE n.id IS UNIQUE;   // ocena analityka (historia)
CREATE CONSTRAINT graphmeta_key      IF NOT EXISTS FOR (n:GraphMeta)       REQUIRE n.key IS UNIQUE;   // stan przebudowy twórców
