"""Prévision du volume de visionnage (épisodes + films par semaine).

Lissage exponentiel de Holt-Winters (statsmodels) : capte tendance et saisonnalité
annuelle. Adapté à un historique hebdomadaire de quelques années, sans sur-apprentissage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def weekly_series(events: pd.DataFrame, exclude_bulk: bool = True) -> pd.Series:
    """Agrège les événements en nombre de visionnages par semaine (index datetime)."""
    ev = events
    if exclude_bulk and "is_bulk_import" in ev.columns:
        ev = ev[~ev["is_bulk_import"]]
    if ev.empty:
        return pd.Series(dtype=float)
    s = (
        ev.set_index("watched_at")
        .assign(n=1)["n"]
        .resample("W")
        .sum()
        .astype(float)
    )
    return s


def forecast_weekly(
    events: pd.DataFrame, horizon: int = 12, exclude_bulk: bool = True
) -> dict:
    """Prévoit `horizon` semaines. Renvoie history, forecast, et intervalle de confiance."""
    s = weekly_series(events, exclude_bulk=exclude_bulk)
    # On rogne les longues traînées de zéros au début (avant le vrai démarrage d'usage)
    if (s > 0).any():
        s = s.loc[s[s > 0].index[0] :]

    if len(s) < 20:
        return {"history": s, "forecast": None, "error": "Historique trop court pour une prévision fiable."}

    seasonal = "add" if len(s) >= 2 * 52 else None
    periods = 52 if seasonal else None
    try:
        model = ExponentialSmoothing(
            s, trend="add", seasonal=seasonal, seasonal_periods=periods,
            initialization_method="estimated",
        ).fit()
    except Exception:
        model = ExponentialSmoothing(s, trend="add", initialization_method="estimated").fit()

    fc = model.forecast(horizon).clip(lower=0)
    # Intervalle approché à partir de l'écart-type des résidus
    resid_std = np.nanstd(model.resid) if hasattr(model, "resid") else s.std()
    lower = (fc - 1.96 * resid_std).clip(lower=0)
    upper = fc + 1.96 * resid_std
    return {
        "history": s,
        "forecast": fc,
        "lower": lower,
        "upper": upper,
        "resid_std": resid_std,
        "error": None,
    }
