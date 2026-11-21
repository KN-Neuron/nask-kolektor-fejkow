import numpy as np

from embsim.cv import bootstrap_ci, holm, inner_groups, outer_folds


def test_every_subject_is_test_exactly_once_and_folds_are_disjoint():
    for seed in range(4):
        folds = outer_folds(83, seed)
        allidx = np.concatenate(folds)
        assert sorted(allidx.tolist()) == list(range(83)) and len(folds) == 5
        assert max(len(f) for f in folds) - min(len(f) for f in folds) <= 1       # równe foldy
    assert not np.array_equal(np.concatenate(outer_folds(83, 0)), np.concatenate(outer_folds(83, 1)))   # różne podziały


def test_inner_groups_partition_only_training_subjects():
    train = np.setdiff1d(np.arange(60), outer_folds(60, 0)[0])
    g = inner_groups(train, 5)
    assert sorted(np.concatenate(g).tolist()) == train.tolist() and len(g) == 3
    assert not (set(np.concatenate(g)) & set(outer_folds(60, 0)[0]))              # test nigdy nie trafia do wewnętrznego doboru


def test_holm_matches_known_values_and_is_monotone():
    p = [0.01, 0.04, 0.03, 0.005]
    assert np.allclose(holm(p), [0.03, 0.06, 0.06, 0.02])                          # (m-rank)*p, kumulowane maksimum
    assert all(0 <= x <= 1 for x in holm([0.9, 0.8, 0.7]))


def test_bootstrap_ci_brackets_mean_and_shrinks_with_n():
    x = np.random.default_rng(0).normal(0.5, 0.1, 40)
    lo, hi = bootstrap_ci(x)
    assert lo < x.mean() < hi
    lo2, hi2 = bootstrap_ci(np.random.default_rng(1).normal(0.5, 0.1, 400))
    assert (hi2 - lo2) < (hi - lo)
