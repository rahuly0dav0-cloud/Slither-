import pandas as pd
import numpy as np
from typing import Tuple, List, Optional
import warnings

warnings.filterwarnings('ignore')

# Input_Path = r"C:\Users\N818004\OneDrive - JPMorgan Chase\Essex\r\Survival_params_r\Prec_reg\SAS Datasets"
# Output_Path = r"C:\Users\N818004\OneDrive - JPMorgan Chase\Essex\r\Survival_params_r\Prec_reg\Python_output"

def proc_reg_outest(
    data: pd.DataFrame,
    y_var: str,
    x_vars: List[str],
    by_vars: List[str],
    noint: bool = False,
    singular: float = 1e-7
) -> pd.DataFrame:

    results = []

    if by_vars:
        grouped = data.groupby(by_vars, sort=True, dropna=False)
    else:
        grouped = [('_ALL_', data)]

    for group_key, group in grouped:

        if by_vars and not isinstance(group_key, tuple):
            group_key = (group_key,)

        row = {}

        if by_vars:
            for var, val in zip(by_vars, group_key):
                row[var] = val

        row['_MODEL_'] = 'MODEL1'
        row['_TYPE_'] = 'PARMS'
        row['_DEPVAR_'] = y_var

        group_clean = group.dropna(subset=[y_var] + x_vars)

        n_obs = len(group_clean)

        if n_obs == 0:
            row['_RMSE_'] = np.nan
            if not noint:
                row['Intercept'] = np.nan
            for xv in x_vars:
                row[xv] = np.nan
            row[y_var] = -1
            results.append(row)
            continue

        y = group_clean[y_var].to_numpy(dtype=np.float64)
        X_raw = group_clean[x_vars].to_numpy(dtype=np.float64)

        # SAS SINGULAR= tolerance (matches PROC REG SINGULAR= option)
        tol = singular

        # Build full design matrix (with intercept column if needed)
        if not noint:
            X_full = np.column_stack([np.ones(n_obs), X_raw])
        else:
            X_full = X_raw.copy()

        p = X_full.shape[1]

        # --- Step 1: Sequential singularity detection on X directly ---
        # Same logic as SAS sweep (column-by-column, in order) but operates
        # on X instead of X'X to avoid squaring the condition number.
        # For each column k: check if it's linearly dependent on columns 0..k-1
        # by projecting it out and comparing residual SS to original SS.
        aliased = np.zeros(p, dtype=bool)
        active_cols = []

        for k in range(p):
            xk = X_full[:, k]
            orig_ss = np.dot(xk, xk)

            if orig_ss <= 0:
                aliased[k] = True
                continue

            if len(active_cols) > 0:
                Q = X_full[:, active_cols]
                coefs, _, _, _ = np.linalg.lstsq(Q, xk, rcond=None)
                residual = xk - Q @ coefs
                resid_ss = np.dot(residual, residual)
            else:
                resid_ss = orig_ss

            if resid_ss / orig_ss < tol:
                aliased[k] = True
            else:
                active_cols.append(k)

        # --- Step 2: Solve using only non-aliased columns via SVD ---
        active_idx = np.array(active_cols)
        beta_full = np.zeros(p)

        if len(active_idx) > 0:
            X_active = X_full[:, active_idx]
            beta_active, _, _, _ = np.linalg.lstsq(X_active, y, rcond=None)
            beta_full[active_idx] = beta_active

        y_hat = X_full @ beta_full
        sse = float(np.sum((y - y_hat) ** 2))

        rank = len(active_idx)
        df = n_obs - rank

        if df > 0:
            row['_RMSE_'] = np.sqrt(sse / df)
        else:
            row['_RMSE_'] = np.nan

        if not noint:
            row['Intercept'] = beta_full[0]
            for i, xv in enumerate(x_vars):
                row[xv] = beta_full[i + 1]
        else:
            for i, xv in enumerate(x_vars):
                row[xv] = beta_full[i]

        row[y_var] = -1
        results.append(row)

    result_df = pd.DataFrame(results)

    # Column order matching SAS PROC REG OUTEST
    col_order = []
    if by_vars:
        col_order.extend(by_vars)
    col_order.extend(['_MODEL_', '_TYPE_', '_DEPVAR_', '_RMSE_'])
    if not noint:
        col_order.append('Intercept')
    col_order.extend(x_vars)
    col_order.append(y_var)
    result_df = result_df[col_order]

    return result_df


# Import Python and SAS Input

# d_2

d_2 = pd.read_csv('d_2_sample.csv')

by_vars_2 = ['ORG_ID', 'ORG_NAME', 'LOB_DESC', 'Bad_Interval']

d_2 = d_2.sort_values(by_vars_2)

parameters_lin_2 = proc_reg_outest(
    d_2,
    'WaitTime',
    ['x1', 'x2'],
    by_vars_2,
    noint=True
)

#c_2

# c_2 = pd.read_csv('c_2.csv')

# by_vars_2 = ['ORG_ID', 'ORG_NAME', 'lob_desc', 'Bad_Interval']

# c_2 = c_2.sort_values(by_vars_2)

# parameters_nonlin_2 = proc_reg_outest(
#     c_2, 'WaitTime', ['x1', 'x2', 'x3', 'x4', 'x5', 'x6', 'x7'], by_vars_2, noint=False
# )

# Export

# parameters_nonlin_2.to_csv('parameters_nonlin_2.csv', index=False)
parameters_lin_2.to_csv('parameters_lin_2_py.csv', index=False)