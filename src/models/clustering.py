"""Segmentation de tes séries par style de consommation (clustering non supervisé).

KMeans sur des features comportementales normalisées, projection PCA 2D pour la visualisation.
Révèle des profils : binge intense, séries « doudou » très revisionnées, abandons précoces, etc.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .completion import build_features


def cluster_series(series: pd.DataFrame, k: int = 4, ref_date: pd.Timestamp | None = None) -> dict:
    df, feats = build_features(series, ref_date)
    if len(df) < k:
        return {"error": "Trop peu de séries pour ce nombre de clusters.", "table": df}

    X = df[feats].values
    Xs = StandardScaler().fit_transform(X)

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(Xs)

    coords = PCA(n_components=2, random_state=42).fit_transform(Xs)
    df = df.copy()
    df["cluster"] = labels
    df["pca_x"] = coords[:, 0]
    df["pca_y"] = coords[:, 1]

    # Profil moyen de chaque cluster (pour étiqueter les segments)
    profile = df.groupby("cluster")[feats].mean()
    profile["taille"] = df.groupby("cluster").size()
    return {"table": df, "features": feats, "profile": profile, "error": None}
