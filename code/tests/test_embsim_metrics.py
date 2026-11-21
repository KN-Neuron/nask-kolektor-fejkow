import numpy as np

from embsim.metrics import assignment, bcubed, clustering, pairwise


def toy():
    # dwie grupy po 3 i dwa negatywy; wynik wysoki w grupie, niski poza nią
    labels = ["a", "a", "a", "b", "b", "b", None, None]
    S = np.full((8, 8), 0.1)
    for g in ([0, 1, 2], [3, 4, 5]):
        for i in g:
            for j in g:
                S[i, j] = 0.9
    np.fill_diagonal(S, 1.0)
    return S, labels


def test_perfect_scores_perfect_metrics():
    S, labels = toy()
    assert pairwise(S, labels)["AUC"] == 1.0
    c = clustering(S, labels, 0.5)
    assert c["ARI"] == 1.0 and c["B3_F"] == 1.0
    a = assignment(S, labels, 0.5)
    assert a["top1"] == 1.0 and a["znany_vs_nowy_AUC"] == 1.0 and a["błędnie_połączone"] == 0.0


def test_random_scores_near_chance_and_none_is_never_positive():
    rng = np.random.default_rng(0)
    A = rng.random((60, 60)); S = (A + A.T) / 2
    labels = [i % 6 for i in range(60)]
    assert abs(pairwise(S, labels)["AUC"] - 0.5) < 0.1
    # etykiety None nie tworzą par pozytywnych
    assert pairwise(np.ones((4, 4)), [None] * 4)["n_poz"] == 0


def test_bcubed_penalises_merging():
    pred = np.zeros(6, int)
    assert bcubed(pred, ["a", "a", "a", "b", "b", "b"])["B3_P"] < 1.0
