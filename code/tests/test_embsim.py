import numpy as np

from embsim.similarity import clusters, sim_matrix


def test_clusters_threshold_and_missing_channel():
    a, b, c = np.array([1.0, 0]), np.array([0.99, 0.14]), np.array([0.0, 1])
    b = b / np.linalg.norm(b)
    S = sim_matrix([a, b, c, None])
    assert np.isnan(S[3, 0])
    assert sorted(map(sorted, clusters(np.nan_to_num(S, nan=-1), 0.9))) == [[0, 1], [2], [3]]
