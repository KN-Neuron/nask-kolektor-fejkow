from fejki.process.extract import extract_artifacts, extract_domains
from fejki.process.hashing import hamming, hash_edges, simhash
from fejki.process.ner_gazetteer import find_entities


def test_artifacts_positive_and_negative():
    a = extract_artifacts("Pisz +48 123 456 789, t.me/test_abc, wa.me/48000111, bit.ly/xyz")
    kinds = {x.kind for x in a}
    assert {"phone", "telegram", "whatsapp", "shortlink"} <= kinds
    assert [x.value for x in a if x.kind == "shortlink"] == ["bit.ly/xyz"]
    assert extract_artifacts("Zadzwoń o 12:30, cena 1234 zł, kod 99") == []
    assert extract_artifacts("t.me/ab") == []  # too short


def test_domains():
    assert extract_domains("wejdź na www.super-zysk.example/x") == ["super-zysk.example"]
    assert extract_domains("brak linku tutaj.") == []


def test_simhash_copies_and_paraphrases():
    a = "Zarabiaj dziś na platformie inwestycyjnej, tylko dla pierwszych stu osób, kliknij i sprawdź"
    assert hamming(simhash(a), simhash(a)) == 0
    b = "Zarabiaj dziś na platformie inwestycyjnej tylko dla pierwszych stu osób kliknij i sprawdź!"
    assert hamming(simhash(a), simhash(b)) <= 6
    c = "Kawiarnia zaprasza na świeże ciasto i kawę w niedzielę po południu w centrum miasta"
    assert hamming(simhash(a), simhash(c)) > 12
    edges = hash_edges([a, a + " ", c], 3, 0.6)
    assert (0, 1) in edges and (0, 2) not in edges


def test_gazetteer_inflection():
    names = ["Anna Testowska"]
    assert find_entities("Reklama z udziałem Anny Testowskiej", names) == names
    assert find_entities("Nic tu nie ma", names) == []
