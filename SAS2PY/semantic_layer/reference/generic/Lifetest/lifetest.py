import pandas as pd
import numpy as np
from scipy.stats import norm
import warnings

warnings.filterwarnings('ignore')


def life_table(
    df,
    time_col,
    event_col,
    freq_col,
    strata_cols,
    step=1,
    alpha=0.05
):
    z = norm.ppf(1 - alpha / 2)
    results = []
    stratum_num = 0

    for strata_vals, g in df.groupby(strata_cols):
        stratum_num += 1

        if not isinstance(strata_vals, tuple):
            strata_vals = (strata_vals,)

        strata_dict = dict(zip(strata_cols, strata_vals))

        max_time = g[time_col].max()
        n_intervals = int(np.ceil(max_time / step))
        interval_starts = np.arange(0, n_intervals * step + step, step)

        g_agg = g.copy()
        g_agg['_interval'] = (g_agg[time_col] // step).astype(int) * step

        events = g_agg[g_agg[event_col] == 1].groupby('_interval')[freq_col].sum()
        censored = g_agg[g_agg[event_col] == 0].groupby('_interval')[freq_col].sum()

        d = np.array([events.get(t, 0) for t in interval_starts], dtype=float)
        w = np.array([censored.get(t, 0) for t in interval_starts], dtype=float)

        n_enter = np.zeros(len(interval_starts))
        n_enter[0] = g[freq_col].sum()
        for i in range(1, len(interval_starts)):
            n_enter[i] = n_enter[i - 1] - d[i - 1] - w[i - 1]

        n_prime = n_enter - w / 2.0

        q = np.where(n_prime > 0, d / n_prime, 0.0)
        p = 1.0 - q

        n_bnd = len(interval_starts) + 1
        S = np.ones(n_bnd)
        for i in range(1, n_bnd):
            S[i] = S[i - 1] * p[i - 1]

        greenwood = np.zeros(n_bnd)
        for i in range(1, n_bnd):
            j = i - 1
            if n_prime[j] > 0 and p[j] > 0:
                greenwood[i] = greenwood[i - 1] + q[j] / (n_prime[j] * p[j])
            else:
                greenwood[i] = greenwood[i - 1]

        var_S = S ** 2 * greenwood
        se_S = np.sqrt(np.maximum(var_S, 0))

        sdf_lcl = np.ones(n_bnd)
        sdf_ucl = np.ones(n_bnd)
        for i in range(n_bnd):
            if S[i] >= 1.0:
                sdf_lcl[i] = 1.0
                sdf_ucl[i] = 1.0
            elif S[i] <= 0.0:
                sdf_lcl[i] = 0.0
                sdf_ucl[i] = 0.0
            else:
                H = -np.log(S[i])
                log_H = np.log(H)
                se_g = se_S[i] / (S[i] * H)
                sdf_lcl[i] = max(0.0, np.exp(-np.exp(log_H + z * se_g)))
                sdf_ucl[i] = min(1.0, np.exp(-np.exp(log_H - z * se_g)))

        pdf_vals = S[:len(interval_starts)] * q / step

        hazard_vals = np.where(
            (1 + p) > 0,
            2 * q / (step * (1 + p)),
            0.0
        )

        midpoints = interval_starts + step / 2.0

        # Trim to last interval with events or censoring (match SAS behavior)
        active = np.where((d > 0) | (w > 0))[0]
        if len(active) > 0:
            last_active = active[-1] + 1
            interval_starts = interval_starts[:last_active]
            midpoints = midpoints[:last_active]
            d = d[:last_active]
            w = w[:last_active]
            n_enter = n_enter[:last_active]
            n_prime = n_prime[:last_active]
            q = q[:last_active]
            p = p[:last_active]
            pdf_vals = pdf_vals[:last_active]
            hazard_vals = hazard_vals[:last_active]
            S = S[:last_active + 1]
            greenwood = greenwood[:last_active + 1]
            sdf_lcl = sdf_lcl[:last_active + 1]
            sdf_ucl = sdf_ucl[:last_active + 1]

        pdf_lcl = np.full(len(interval_starts), np.nan)
        pdf_ucl = np.full(len(interval_starts), np.nan)
        for i in range(len(interval_starts)):
            if q[i] > 0 and n_prime[i] > 0:
                pdf_var = pdf_vals[i] ** 2 * (
                    greenwood[i] + p[i] / (n_prime[i] * q[i])
                )
                se_pdf = np.sqrt(max(pdf_var, 0))
                pdf_lcl[i] = max(0.0, pdf_vals[i] - z * se_pdf)
                pdf_ucl[i] = pdf_vals[i] + z * se_pdf

        haz_lcl = np.full(len(interval_starts), np.nan)
        haz_ucl = np.full(len(interval_starts), np.nan)
        for i in range(len(interval_starts)):
            if q[i] > 0 and n_prime[i] > 0:
                haz_var = (
                    hazard_vals[i] ** 2
                    * (1 - (step * hazard_vals[i] / 2) ** 2)
                    / (n_prime[i] * q[i])
                )
                se_haz = np.sqrt(max(haz_var, 0))
                haz_lcl[i] = max(0.0, hazard_vals[i] - z * se_haz)
                haz_ucl[i] = hazard_vals[i] + z * se_haz

        rows = []
        for i in range(len(interval_starts)):
            rows.append({
                **strata_dict,
                'WaitTime': interval_starts[i],
                'SURVIVAL': S[i],
                'SDF_LCL': sdf_lcl[i],
                'SDF_UCL': sdf_ucl[i],
                'MIDPOINT': midpoints[i],
                'PDF': pdf_vals[i],
                'PDF_LCL': pdf_lcl[i],
                'PDF_UCL': pdf_ucl[i],
                'HAZARD': hazard_vals[i],
                'HAZ_LCL': haz_lcl[i],
                'HAZ_UCL': haz_ucl[i],
                'STRATUM': stratum_num,
            })

        terminal_idx = len(interval_starts)
        rows.append({
            **strata_dict,
            'WaitTime': interval_starts[-1] + step,
            'SURVIVAL': S[terminal_idx],
            'SDF_LCL': sdf_lcl[terminal_idx],
            'SDF_UCL': sdf_ucl[terminal_idx],
            'MIDPOINT': np.nan,
            'PDF': np.nan,
            'PDF_LCL': np.nan,
            'PDF_UCL': np.nan,
            'HAZARD': np.nan,
            'HAZ_LCL': np.nan,
            'HAZ_UCL': np.nan,
            'STRATUM': stratum_num,
        })

        out = pd.DataFrame(rows)
        results.append(out)

    result = pd.concat(results, ignore_index=True)

    float_cols = result.select_dtypes(float).columns
    result[float_cols] = result[float_cols].round(10)

    return result

#Import Input Data

Survival_Data_1_sample = pd.read_csv('Survival_Data_1_sample.csv')


survtest_1a_sample_py = life_table(
    Survival_Data_1_sample,
    time_col='WaitTime',
    event_col='Abandon',
    freq_col='Records',
    strata_cols=['ORG_NAME', 'ORG_ID'],
    step=1
)

survtest_1a_sample_py.to_csv('survtest_1a_sample_py.csv', index=False)