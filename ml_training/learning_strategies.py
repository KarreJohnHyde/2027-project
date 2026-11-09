"""Offline research learning on explicit feature matrices. Never updates serving models.

Features can be numeric CSV columns or frozen image/text/volume embeddings with
verified subject joins. Labels/identifiers must be excluded by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.semi_supervised import SelfTrainingClassifier


def features(values):
    result = np.asarray(values, dtype=np.float32)
    if result.ndim != 2 or not len(result) or not result.shape[1] or not np.isfinite(result).all():
        raise ValueError("Features must be a nonempty, finite, numeric 2-D matrix.")
    return result


def assert_disjoint_groups(train, validation, test):
    groups = [set(map(str, values)) for values in (train, validation, test)]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("Subject/group leakage between training, validation and test.")


def fit_feature_learners(train_x, seed_labels, *, seed=42, components=64):
    """Fit preprocessing, novelty and self-training on training rows only.

    -1 means unlabeled; hidden labels are never supplied to the learner.
    Novelty scores describe feature distributions, never disease probability.
    """
    train_x = features(train_x)
    labels = np.asarray(seed_labels).reshape(-1)
    if len(labels) != len(train_x) or not np.issubdtype(labels.dtype, np.integer) or (labels < -1).any():
        raise ValueError("One integer seed label per row is required; -1 denotes unlabeled.")
    known = labels >= 0
    if len(np.unique(labels[known])) < 2:
        raise ValueError("At least two labeled classes are required.")
    transform = make_pipeline(StandardScaler(), PCA(n_components=min(components, train_x.shape[1], len(train_x) - 1),
                                                    svd_solver="randomized", random_state=seed))
    encoded = transform.fit_transform(train_x)
    novelty = IsolationForest(n_estimators=150, contamination="auto", random_state=seed, n_jobs=2).fit(encoded)
    baseline = LogisticRegression(max_iter=1000, C=1.0).fit(encoded[known], labels[known])
    semi = SelfTrainingClassifier(LogisticRegression(max_iter=1000, C=1.0), threshold=0.9, max_iter=10)
    semi.fit(encoded, labels)
    return {"transform": transform, "novelty": novelty, "baseline": baseline, "semi_supervised": semi,
            "labeled_rows": int(known.sum()), "unlabeled_rows": int((~known).sum()),
            "pseudo_labeled_rows": int(((semi.transduction_ >= 0) & ~known).sum())}


@dataclass
class OfflineQPolicy:
    """Masked tabular Q-learning from logged research rewards; unseen states defer.

    An action is an analysis workflow, never medication, diagnosis or treatment.
    Learning requires explicit rewards; no reward is invented from patient data.
    """
    actions: int = 3
    defer: int = 2
    alpha: float = 0.15
    gamma: float = 0.9
    q: dict = field(default_factory=dict)
    seen: dict = field(default_factory=dict)

    def update(self, state, action, reward, *, allowed, next_state=None, next_allowed=None, terminal=True):
        mask = np.asarray(allowed, dtype=bool)
        if mask.shape != (self.actions,) or action < 0 or action >= self.actions or not mask[action]:
            raise ValueError("Logged action is forbidden by the eligibility mask.")
        if not np.isfinite(reward):
            raise ValueError("Reward must be finite.")
        continuation = 0.0
        if not terminal:
            next_mask = np.asarray(next_allowed, dtype=bool)
            if next_state is None or next_mask.shape != (self.actions,) or not next_mask.any():
                raise ValueError("Nonterminal transitions need a next state and eligible actions.")
            continuation = float(np.max(self.q.get(next_state, np.zeros(self.actions))[next_mask]))
        values = self.q.setdefault(state, np.zeros(self.actions, dtype=float))
        values[action] += self.alpha * (float(reward) + self.gamma * continuation - values[action])
        self.seen.setdefault(state, np.zeros(self.actions, dtype=int))[action] += 1

    def select(self, state, allowed):
        mask = np.asarray(allowed, dtype=bool)
        if mask.shape != (self.actions,) or not mask[self.defer]:
            raise ValueError("A valid defer action must always remain available.")
        if state not in self.q:
            return self.defer
        eligible = mask & (self.seen[state] > 0)
        # Unobserved actions cannot acquire apparent value from zero initialization.
        scores = np.where(eligible, self.q[state], -np.inf)
        best = int(np.argmax(scores))
        return best if scores[best] > 0 else self.defer


def policy_state(probabilities):
    return tuple((int(np.argmax(p)), min(9, int(float(np.max(p)) * 10))) for p in probabilities)


def eligibility(probabilities, minimum=0.7):
    return [float(np.max(p)) >= minimum for p in probabilities] + [True]
