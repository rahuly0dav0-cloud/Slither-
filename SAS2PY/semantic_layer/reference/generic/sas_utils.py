"""
sas_utils.py
============
SAS-faithful numeric helpers used by the Python port of ``p2b.sas``.

Contents
--------
* :class:`SASRandom`      - reproduces the SAS ``RANUNI`` stream (the legacy
                            Fishman & Moore prime-modulus multiplicative
                            congruential generator, m = 2**31 - 1,
                            a = 397204094).  Needed so the MODEL / HOLDOUT
                            split matches SAS.
* :func:`sas_percent`     - formats a fraction the way the SAS ``PERCENTN.``
                            format does (e.g. ``0.8123 -> '81.2%'``).
* :func:`proc_univariate` - reproduces the key tables of ``PROC UNIVARIATE``
                            (Moments, Basic Measures, Tests for Location,
                            Quantiles [PCTLDEF=5], Extreme Observations).
* :func:`export_xlsx`     - thin wrapper around ``DataFrame.to_excel`` matching
                            ``PROC EXPORT ... DBMS=XLSX REPLACE``.

NOTE ON RANUNI
--------------
SAS documents ``RANUNI`` as a prime-modulus multiplicative congruential
generator with modulus ``2**31 - 1`` and multiplier ``397204094``
(Fishman and Moore 1982).  With a fixed positive seed the stream is
reproducible.  This is replicated below.  If a future SAS validation run
disagrees, this generator is the single place to adjust.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Union

import numpy as np
import pandas as pd
from scipy import stats


# ==================================================================================
# SAS RANUNI
# ==================================================================================
class SASRandom:
    """Reproduce the legacy SAS ``RANUNI`` uniform(0,1) stream.

    Parameters
    ----------
    seed : int
        The positive integer seed (as passed to ``ranuni(seed)`` in SAS).
        A non-positive seed would make SAS use the time of day; that is not
        reproducible and is therefore rejected here.
    """

    _M = 2147483647            # 2**31 - 1  (prime modulus)
    _A = 397204094             # multiplier (Fishman & Moore 1982)

    def __init__(self, seed: int):
        seed = int(seed)
        if seed <= 0:
            raise ValueError("SASRandom requires a positive integer seed.")
        self._seed = seed % self._M
        if self._seed == 0:
            self._seed = 1

    def uniform(self) -> float:
        """Return the next uniform(0,1) draw (advances the stream)."""
        self._seed = (self._A * self._seed) % self._M
        return self._seed / self._M


# ==================================================================================
# SAS PERCENT format
# ==================================================================================
def sas_percent(value: float, width: int = 5, decimals: int = 1) -> str:
    """Format ``value`` like the SAS ``PERCENTw.d`` format (default ``percent5.1``).

    SAS multiplies by 100, appends ``%`` and right-justifies within ``width``.
    Missing values render as ``.``.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "."
    txt = f"{value * 100:.{decimals}f}%"
    return txt.rjust(width)


# ==================================================================================
# SAS skewness / kurtosis (bias-corrected, PROC UNIVARIATE formulas)
# ==================================================================================
def _sas_skewness(x: np.ndarray, mean: float, std: float) -> float:
    n = x.size
    if n < 3 or std == 0:
        return np.nan
    z = (x - mean) / std
    return (n / ((n - 1) * (n - 2))) * float(np.sum(z ** 3))


def _sas_kurtosis(x: np.ndarray, mean: float, std: float) -> float:
    n = x.size
    if n < 4 or std == 0:
        return np.nan
    z = (x - mean) / std
    term1 = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3)) * float(np.sum(z ** 4))
    term2 = 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return term1 - term2


# ==================================================================================
# PROC UNIVARIATE
# ==================================================================================
def proc_univariate(
    values: Union[Sequence[float], pd.Series, np.ndarray],
    var_name: str = "delta",
    mu0: float = 0.0,
    pctl_func: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None,
    title: Optional[str] = None,
) -> dict:
    """Reproduce the default output tables of ``PROC UNIVARIATE``.

    Parameters
    ----------
    values : sequence of float
        The analysis variable (missing values are dropped, as SAS does).
    var_name : str
        Name of the analysis variable (for display).
    mu0 : float
        Null value for the "Tests for Location" (SAS default 0).
    pctl_func : callable, optional
        Percentile function matching SAS PCTLDEF=5.  Pass
        ``glt.sas_like_percentile``.  If omitted, a local PCTLDEF=5
        implementation is used.
    title : str, optional
        Title printed above the output.

    Returns
    -------
    dict
        Keys ``moments``, ``measures``, ``location_tests``, ``quantiles`` and
        ``extremes`` each hold a :class:`pandas.DataFrame`.
    """
    x = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    x = x[~np.isnan(x)]
    n = x.size
    if n == 0:
        raise ValueError("proc_univariate: no non-missing observations.")

    if pctl_func is None:
        pctl_func = _local_pctldef5

    mean = float(np.mean(x))
    # SAS uses the sample (n-1) standard deviation.
    var = float(np.var(x, ddof=1)) if n > 1 else 0.0
    std = float(np.sqrt(var))
    css = float(np.sum((x - mean) ** 2))          # corrected SS
    uss = float(np.sum(x ** 2))                    # uncorrected SS
    cv = (std / mean * 100.0) if mean != 0 else np.nan
    std_err = std / np.sqrt(n) if n > 0 else np.nan
    skew = _sas_skewness(x, mean, std)
    kurt = _sas_kurtosis(x, mean, std)

    moments = pd.DataFrame(
        {
            "Label": [
                "N", "Mean", "Std Deviation", "Skewness", "Uncorrected SS",
                "Coeff Variation",
                "Sum Weights", "Sum Observations", "Variance", "Kurtosis",
                "Corrected SS", "Std Error Mean",
            ],
            "Value": [
                n, mean, std, skew, uss, cv,
                float(n), float(np.sum(x)), var, kurt, css, std_err,
            ],
        }
    )

    # ---- Basic Statistical Measures ----
    median = float(pctl_func(x, np.array([50.0]))[0])
    vals, counts = np.unique(x, return_counts=True)
    mode = float(vals[np.argmax(counts)]) if counts.max() > 1 else np.nan
    q1 = float(pctl_func(x, np.array([25.0]))[0])
    q3 = float(pctl_func(x, np.array([75.0]))[0])
    iqr = q3 - q1
    data_range = float(np.max(x) - np.min(x))
    measures = pd.DataFrame(
        {
            # SAS shows 3 location rows and 4 variability rows side by side;
            # pad the location columns so both sides have equal length.
            "LocationMeasure": ["Mean", "Median", "Mode", ""],
            "LocationValue": [mean, median, mode, np.nan],
            "VariabilityMeasure": ["Std Deviation", "Variance",
                                   "Range", "Interquartile Range"],
            "VariabilityValue": [std, var, data_range, iqr],
        }
    )

    # ---- Tests for Location: Mu0 = mu0 ----
    d = x - mu0
    # Student's t
    if std > 0:
        t_stat = (mean - mu0) / std_err
        t_p = float(2 * stats.t.sf(abs(t_stat), n - 1))
    else:
        t_stat, t_p = np.nan, np.nan
    # Sign test
    n_pos = int(np.sum(d > 0))
    n_neg = int(np.sum(d < 0))
    n_nonzero = n_pos + n_neg
    M = (n_pos - n_neg) / 2.0
    if n_nonzero > 0:
        # two-sided sign test p-value via the binomial distribution
        k = max(n_pos, n_neg)
        sign_p = float(min(1.0, 2 * stats.binom.sf(k - 1, n_nonzero, 0.5)))
    else:
        sign_p = np.nan
    # Wilcoxon signed rank
    if n_nonzero > 0:
        abs_d = np.abs(d[d != 0])
        ranks = stats.rankdata(abs_d)
        signs = np.sign(d[d != 0])
        w_plus = float(np.sum(ranks[signs > 0]))
        S = w_plus - n_nonzero * (n_nonzero + 1) / 4.0
        # normal approximation with tie/continuity handling (SAS uses a t approx)
        var_s = (n_nonzero * (n_nonzero + 1) * (2 * n_nonzero + 1)) / 24.0
        if var_s > 0:
            z = S / np.sqrt(var_s)
            sr_p = float(2 * stats.norm.sf(abs(z)))
        else:
            sr_p = np.nan
    else:
        S, sr_p = np.nan, np.nan

    location_tests = pd.DataFrame(
        {
            "Test": ["Student's t", "Sign", "Signed Rank"],
            "Statistic": [t_stat, M, S],
            "pValue": [t_p, sign_p, sr_p],
        }
    )

    # ---- Quantiles (Definition 5) ----
    pct_points = np.array([100, 99, 95, 90, 75, 50, 25, 10, 5, 1, 0], dtype=float)
    qvals = pctl_func(x, pct_points)
    quantiles = pd.DataFrame(
        {
            "Quantile": [
                "100% Max", "99%", "95%", "90%", "75% Q3", "50% Median",
                "25% Q1", "10%", "5%", "1%", "0% Min",
            ],
            "Estimate": qvals,
        }
    )

    # ---- Extreme Observations ----
    order = np.argsort(x, kind="mergesort")
    lowest_idx = order[:5]
    highest_idx = order[-5:]
    extremes = pd.DataFrame(
        {
            "LowestValue": x[lowest_idx],
            "LowestObs": (lowest_idx + 1),
            "HighestValue": x[highest_idx],
            "HighestObs": (highest_idx + 1),
        }
    )

    result = {
        "moments": moments,
        "measures": measures,
        "location_tests": location_tests,
        "quantiles": quantiles,
        "extremes": extremes,
    }

    if title:
        print(title)
    print(f"\nThe UNIVARIATE Procedure  -  Variable: {var_name}\n")
    print("Moments")
    print(moments.to_string(index=False))
    print("\nBasic Statistical Measures")
    print(measures.to_string(index=False))
    print(f"\nTests for Location: Mu0={mu0}")
    print(location_tests.to_string(index=False))
    print("\nQuantiles (Definition 5)")
    print(quantiles.to_string(index=False))
    print("\nExtreme Observations")
    print(extremes.to_string(index=False))
    return result


def _local_pctldef5(values: np.ndarray, pct_points: np.ndarray) -> np.ndarray:
    """Fallback PROC UNIVARIATE PCTLDEF=5 implementation (see glt.sas_like_percentile)."""
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return np.full(len(pct_points), np.nan, dtype=float)
    x = np.sort(x)
    n = x.size
    out = np.empty(len(pct_points), dtype=float)
    for i, t in enumerate(pct_points):
        p = float(t) / 100.0
        np_val = n * p
        j = int(np.floor(np_val))
        g = np_val - j

        def x_sas(k: int) -> float:
            if k <= 1:
                return x[0]
            if k >= n:
                return x[n - 1]
            return x[k - 1]

        if np.isclose(g, 0.0):
            out[i] = 0.5 * (x_sas(j) + x_sas(j + 1))
        else:
            out[i] = x_sas(j + 1)
    return out


# ==================================================================================
# PROC EXPORT ... DBMS=XLSX
# ==================================================================================
def export_xlsx(df: pd.DataFrame, path: str) -> None:
    """Write ``df`` to ``path`` as a single-sheet .xlsx (PROC EXPORT DBMS=XLSX)."""
    df.to_excel(path, index=False)
