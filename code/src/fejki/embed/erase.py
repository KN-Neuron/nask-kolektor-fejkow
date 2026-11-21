"""LEACE concept erasure plus topic rule-labeler. FIT only on background FIT split with external labels."""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F
from concept_erasure import LeaceEraser

from .encoder import l2

TOPIC_KEYWORDS = {
    "invest_crypto": ["bitcoin", "krypto", "inwestycj", "tradingow", "giełd", "akcj", "odsetk"],
    "health": ["suplement", "odchudzani", "stawów", "ciśnieni", "cholesterol", "wzrok", "zdrowi"],
    "institution": ["bankow", "urzęd", "podatk", "konta", "kart", "nadpłat"],
    "ecommerce": ["wyprzedaż", "mebl", "buty", "robot sprzątający", "rabat", "dostaw"],
    "lottery": ["loteri", "konkurs", "losowani", "nagrod", "ankiet", "wygran"],
    "remote_work": ["praca zdalna", "dorabianie", "etat", "zlecenia", "wypłat"],
    "loans": ["pożyczk", "dotacj", "kredyt", "raty", "bik"],
}
LABELER_VERSION = "rule-v1"


def rule_label(text: str) -> str:
    t = text.lower()
    scores = {k: sum(t.count(w) for w in ws) for k, ws in TOPIC_KEYWORDS.items()}
    k = max(scores, key=lambda x: scores[x])
    return k if scores[k] > 0 else "other"


def to_onehot(labels: list[str]) -> tuple[torch.Tensor, list[str]]:
    classes = sorted(set(labels))
    idx = torch.tensor([classes.index(l) for l in labels])
    return F.one_hot(idx, len(classes)).float(), classes


def fit_leace(X_fit: np.ndarray, labels: list[str]) -> tuple[LeaceEraser, int]:
    z, _ = to_onehot(labels)
    er = LeaceEraser.fit(torch.tensor(X_fit, dtype=torch.float32), z)
    rank = int(torch.linalg.matrix_rank((er.proj_left @ er.proj_right).double(), rtol=1e-4))  # removed rank <= k-1
    return er, rank


def apply_leace(er: LeaceEraser, X: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        out = er(torch.tensor(X, dtype=torch.float32)).numpy()
    return l2(out)


def length_bucket(text: str) -> str:
    n = len(text)
    return "s" if n < 120 else "m" if n < 250 else "l"
