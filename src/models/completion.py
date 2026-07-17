"""Détection des séries « à risque d'abandon » (scoring de risque).

Objectif concret : parmi les séries en cours, lesquelles risques-tu de ne jamais finir ?

Approche : on apprend, sur l'ensemble des séries commencées, ce qui distingue une série
menée à terme d'une série délaissée, à partir de features comportementales (avancement,
ancienneté du dernier épisode, vitesse de visionnage, longueur…). Un RandomForest fournit
un score de risque + l'importance des facteurs. Label construit par heuristique, donc à lire
comme un outil d'aide à la décision, pas une vérité absolue.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict

STALE_DAYS = 120  # sans nouvel épisode depuis > 4 mois = potentiellement délaissée


def build_features(series: pd.DataFrame, ref_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """Construit les features par série à partir de la table `series` agrégée."""
    ref_date = ref_date or pd.Timestamp.now()
    df = series.copy()
    df = df[df["n_watched"] > 0].copy()  # séries réellement commencées

    df["days_since_last"] = (ref_date - df["last_watched"]).dt.days
    df["watch_span_days"] = (df["last_watched"] - df["first_watched"]).dt.days.clip(lower=1)
    df["velocity"] = df["n_watched"] / df["watch_span_days"]  # épisodes / jour
    df["rewatch_rate"] = df["total_rewatch"] / df["n_watched"].clip(lower=1)
    df["is_up_to_date"] = (df["status"] == "up_to_date").astype(int)

    feats = [
        "completion_rate", "n_episodes", "n_watched", "days_since_last",
        "watch_span_days", "velocity", "rewatch_rate", "is_up_to_date",
    ]
    df[feats] = df[feats].fillna(0)
    return df, feats


def _label_abandoned(df: pd.DataFrame) -> pd.Series:
    """Heuristique de vérité terrain : délaissée = pas à jour, incomplète et inactive."""
    return (
        (df["status"] != "up_to_date")
        & (df["completion_rate"] < 0.9)
        & (df["days_since_last"] > STALE_DAYS)
    ).astype(int)


def train_risk_model(series: pd.DataFrame, ref_date: pd.Timestamp | None = None) -> dict:
    df, feats = build_features(series, ref_date)
    y = _label_abandoned(df)

    result = {"table": df, "features": feats, "n_abandoned": int(y.sum()), "n_total": len(df)}
    if y.nunique() < 2 or len(df) < 20:
        result["error"] = "Pas assez de signal pour entraîner un modèle (classes déséquilibrées ou trop peu de séries)."
        result["model"] = None
        return result

    X = df[feats].values
    clf = RandomForestClassifier(n_estimators=300, random_state=42, class_weight="balanced")
    # Probabilité hors-échantillon via validation croisée (honnête, pas de fuite)
    proba = cross_val_predict(clf, X, y, cv=5, method="predict_proba")[:, 1]
    clf.fit(X, y)

    df = df.copy()
    df["risk_score"] = proba
    df["true_abandoned"] = y.values
    result["table"] = df
    result["model"] = clf
    result["importances"] = pd.Series(clf.feature_importances_, index=feats).sort_values(ascending=False)
    result["error"] = None
    return result
