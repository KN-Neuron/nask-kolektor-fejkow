from fejki.demo import linkgraph as lg
from fejki.demo.similar import Campaign, Evidence, Pair


def ev(code, w, reason):
    return Evidence(code=code, channel=code, weight=w, reason=reason)


PAIRS = [
    Pair(a="1", b="2", score=1.0, relation="duplikat", evidence=[
        ev("shared_pixel", 0.9, "ten sam piksel Meta: 123 (to samo konto reklamowe lub operator)"),
        ev("same_path_template", 0.7, "ten sam wzorzec ścieżki: /_cdn/production/landing-cdn/<UUID>/fonts/a.woff"),
        ev("topic", 0.05, "ta sama główna tematyka: news"),
    ]),
    Pair(a="3", b="4", score=1.0, relation="duplikat", evidence=[
        ev("same_path_template", 0.7, "ten sam wzorzec ścieżki: /_cdn/production/landing-cdn/666/<UUID>/logo.svg"),
    ]),
    Pair(a="1", b="3", score=0.9, relation="wspólna infrastruktura / operator", evidence=[
        ev("same_path_template", 0.7, "ten sam wzorzec ścieżki: /aio-static/sdk/main.js"),
    ]),
    Pair(a="2", b="3", score=0.9, relation="wspólna infrastruktura / operator", evidence=[
        ev("same_path_template", 0.7, "ten sam wzorzec ścieżki: /aio-static/sdk/main.js"),
    ]),
]
CAMPS = [Campaign(id="K1", name="", members=["1", "2"], strength=1), Campaign(id="K2", name="", members=["3", "4"], strength=1),
         Campaign(id="K3", name="", members=["5"], strength=0)]
NETS = [Campaign(id="S1", name="", members=["1", "2", "3", "4"], strength=1), Campaign(id="S2", name="", members=["5"], strength=0)]


def test_same_trace_in_many_pairs_is_one_node_and_weak_evidence_dropped():
    ts = lg.traces(PAIRS)
    js = [t for t in ts if t.value == "/aio-static/sdk/main.js"]
    assert len(js) == 1 and js[0].members == {"1", "2", "3"}
    assert not [t for t in ts if t.code == "topic"]
    assert [t.value for t in ts if t.code == "shared_pixel"] == ["123"]


def test_different_paths_with_common_prefix_stay_apart():
    cdn = [t for t in lg.traces(PAIRS) if t.value.startswith("/_cdn")]
    assert sorted(sorted(t.members) for t in cdn) == [["1", "2"], ["3", "4"]]


def test_dot_draws_networks_campaigns_and_skips_lonely():
    d = lg.dot(["1", "2", "3", "4", "5"], NETS, CAMPS, PAIRS, {"1": 'tytuł "x"'})
    assert "sieć S1" in d and "kampania K1" in d and "kampania K2" in d
    assert '"m:5"' not in d and "sieć S2" not in d
    assert d.count("subgraph cluster_") == 3
    assert lg.lonely(["1", "5"], PAIRS) == ["5"]


def test_summary_says_what_links_campaigns():
    lines = lg.summary(NETS[0], CAMPS, lg.traces(PAIRS), {})
    assert any(line.startswith("**1, 2** to jedna kampania") and "piksel Meta" in line for line in lines)
    assert any("**1, 2, 3** łączy" in line and "/aio-static/sdk/main.js" in line for line in lines)
