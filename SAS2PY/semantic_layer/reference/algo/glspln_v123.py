#######################################
# Code Begin
#######################################
import pandas as pd
import numpy as np
from datetime import date, datetime
import statsmodels.api as sm
from scipy import stats
import os, re
import matplotlib.pyplot as plt
import heapq
import scipy ###modified0520

glspln_version = '1.2.3'
glspln_last_update = '4/6/20'

# data GLSPLN_help
help_text = [
    "",
    "***************************************************************",
    "%glspln(dsin, resp_var, expl_var, n=1, allsig=allsig, cont_blk_var=,",
    "   cat_blk_var=, maxstep=10, num_knot=100, last_knot=, name=,",
    "   initialize = 0, activation=0)",
    "",
    "****************",
    "REQUIRED INPUT",
    "****************",
    "",
    "   dsin = the input dataset",
    "          (you may use thestatements such as keep and where with this dataset.)",
    "          (It reads from this data - it does not write to it,)",
    "",
    "   resp_var = the target or response variable.",
    "",
    "   expl_var = a continuous variable to model resp_var with",
    "",
    "   n = an index for the output - must be a number",
    "",
    "****************",
    "OPTIONAL INPUT",
    "****************",
    "",
    "   allsig = an output dataset with the code for the spline info including the",
    "            code for adding the transformation to another dataset.",
    "",
    "   allplotdat = The data used in the \"bin\" plots. (to be used to plot macro)",
    "",
    "   cont_blk_var = continuous (linear) variables to block on.",
    "",
    "   cat_blk_var = categorical variables to block on.",
    "",
    "   levels = the number of bins to use in the bin plot. (to be moved to plot)",
    "",
    "   maxstep = The maximum number of stepwise steps used in creating the spline.",
    "             The number of knots will be at most this value, but could be less.",
    "",
    "   last_knot = the largest value for a continuous knot. If used the code,",
    "               includes step functions to model changes larger than this value",
    "",
    "   num_knot = The number of knots to use. It is recommended that there be at",
    "              least 5 obs per knot. Values are limited to 25, 50, 100, 200, 250",
    "",
    "   slentry = The probability criteria for adding a knot into the model. (See",
    "             Proc Logistic for documentation.) (not used, BIC/SBC)",
    "",
    "   slstay = The probability criteria for keeping knots in the model. (See",
    "            Proc Logistic for documentation.) (not used, BIC/SBC)",
    "",
    "   name = The name for the transformed variable in the output. (The default is",
    "          the old variable name with \"_ut\" appended to the end.)",
    "",
    "   initialize = an indicator to initialize the output. 1 triggers the",
    "                initialization any value other than 1 causes the output to be",
    "                appended to the previous output. The code will yield errors if things",
    "                haven't been initialized",
    "",
    "   activation = indicators to switch activation functions.",
    "                -1 uses min(0,x), 1 uses max(0,x), and 0 uses both types",
    "",
    "Notes:",
    "",
    "   ==> the code is not idiot proof1 Review the log for errors. <==",
    "   ==> Make sure that the output is reasonable. Odd things happen!  <==",
]

glspln_help = pd.DataFrame({'help': help_text})
print(glspln_help)


# %macro GLSPLNHelp(x) equivalent
def glsplnhelp(x, glspln_help):

    if x == 1:
        output = glspln_help.head(11)

    else:
        output = glspln_help

    print(output.to_string(index=False))


# data About_GLSPLN
about_glspln_data = [
    ('', 'glspln', 'the glspln macro package'),
    ('', '', 'generalized linear spline'),
    ('', '', ''),
    ('', 'version', ''),
    ('', 'last update', ''),
    ('', 'author', 'dr. basil coutant (basil.w.coutant@chase.com)'),
    ('', '', ''),
    ('', 'usergroup', 'send an email to basil.w.coutant@chase.com to be'),
    ('', '', 'put on the update distribution list.'),
    ('', '', ''),
    ('', 'notes:', '1) verify any use of the last knot feature!'),
    ('', '', '2) see notes that the end for running this on'),
    ('', '', 'multiple variables.'),
    ('', '', ''),
    ('', '', '3) the activation parameter switches the'),
    ('', '', 'activation functions.'),
    ('', '', '-1 uses min(0,x), 1 uses max(0,x), and'),
    ('', '', '0 uses both types'),
    ('', '', ''),
    ('', 'help:', '%glsplnhelp(x) x = 1 a for restricted version.')
]

about_glspln = pd.DataFrame(
    about_glspln_data,
    columns = ['pad', 'description', 'value']
)

glspln_version = '1.2.3'
glspln_last_update = '4/6/20'

about_glspln.loc[
    about_glspln['description'] == 'version',
    'value'
] = glspln_version

about_glspln.loc[
    about_glspln['description'] == 'last update',
    'value'
] = glspln_last_update

print(about_glspln.to_string(index=False))

del about_glspln

glsplnhelp(1, glspln_help)             # %GLSPLNHelp(1); equivalent

# data GLSPLN_meta
glspln_meta = pd.DataFrame(
    [
        ('', 'version',        'glspln version',       '1'),
        ('', 'date',           'run date',             '1'),
        ('', 'dsin',           'data set',             '1'),
        ('', 'resp_var',       'response variable',    '1'),
        ('', 'expl_var',       'explanatory variable', '1'),
        ('', 'n',              'output index',         '1'),
        ('', 'allsig',         'spline code output',   '1'),
        ('', 'cont_blk_var',   'cont. block vars.',    '1'),
        ('', 'cat_blk_var',    'cat. block vars.',     '1'),
        ('', 'maxstep',        'max number of knots',  '1'),
        ('', 'num_knot',       'number of knots used', '1'),
        ('', 'last_knot',      'max value for a bend', '1'),
        ('', 'name',           'spline var. name',     '1'),
        ('', 'initialize',     'init. trigger',        '1'),
        ('', 'activation',     'act. fn choice',       '1'),
    ],
    columns=['pad', 'macro_var', 'macro_var_desc', 'value']
)

##############################################
# Replicate SAS PROC UNIVARIATE default percentile definition
##############################################
def sas_pctldef5(values: np.ndarray, pct_points: np.ndarray) -> np.ndarray:
    """
    Replicate SAS PROC UNIVARIATE default percentile definition: PCTLDEF=5.
    pct_points are in [0, 100].
    """
    x = np.asarray(values, dtype=float)
    x = x[~np.isnan(x)]

    if x.size == 0:
        return np.full(len(pct_points), np.nan, dtype=float)

    x.sort()
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



##################################################
# Initialising / defining Macros
##################################################

# data ttemp
def create_ttemp(dsin, expl_var, resp_var, cont_blk_var, cat_blk_var):

    cont_blk_var = cont_blk_var or []
    cat_blk_var = cat_blk_var or []

    keep_cols = (
        [expl_var, resp_var] + list(cont_blk_var) + list(cat_blk_var)
    )

    ttemp = dsin.loc[:, keep_cols].copy()

    ttemp['byvar'] = 1

    return ttemp

# Restrict Num_knot to allowed values
# Set the corresponding value for knot_step
def normalize_num_knot(num_knot):

    initial = num_knot

    if initial <= 49:
        num_knot = 26
        knot_step = 4
    elif initial <= 99:
        num_knot = 51
        knot_step = 2
    elif initial <= 199:
        num_knot = 101
        knot_step = 1
    elif initial <= 249:
        num_knot = 201
        knot_step = 0.5
    else:
        num_knot = 251
        knot_step = 0.4

    return num_knot, knot_step


def normalize_var_list(x):
    if x is None or str(x).strip() == "":
        return []
    if isinstance(x, str):
        return x.split()
    return list(x)

### modified0520
def custom_sort(items):
    month_pat = re.compile(r'^month_(\d+)$')
    minmax_pat = re.compile(r'^(minx|maxx)(\d+)$')
    
    fixed_order = [
        "bankdays",
        "bk_mondays",
        "bk_fridays",
        "bk_saturdays",
        "actualdays",
        'misx'
    ]
    
    

    month_list = []   
    fixed_list = []   
    minx_list = []    
    maxx_list = []  
    others = [] ##modified0608

    for item in items:
        s = str(item).strip()
        
        m_month = month_pat.match(s)
        if m_month:
            num = int(m_month.group(1))
            month_list.append((num, s))
            continue
        
        
        m_mm = minmax_pat.match(s)
        if m_mm:
            prefix, num_str = m_mm.groups()
            num = int(num_str)
            if prefix == "minx":
                minx_list.append((num, s))
            else:
                maxx_list.append((num, s))
            continue
        
        if s in fixed_order:
            fixed_list.append(s)
        else: ##modified0608
        
            others.append(s) ##modified0608

    
    month_sorted = [x for _, x in sorted(month_list)] 
    minx_sorted = [x for _, x in sorted(minx_list)]
    maxx_sorted = [x for _, x in sorted(maxx_list)]
    
    fixed_sorted = [f for f in fixed_order if f in fixed_list]
    
    return month_sorted + fixed_sorted + minx_sorted + maxx_sorted + others ##modified0608


def _sas_rank(X, singular=1e-7):
    """
    Sequential singularity detection matching SAS PROC REG sweep logic.
    Checks each column against previously accepted columns, in order.
    Uses relative tolerance (resid_ss / orig_ss < singular) like SAS SINGULAR= option.

    Returns (rank, active_cols) where active_cols is the list of non-aliased
    column indices.
    """
    X = np.asarray(X, dtype=float)
    p = X.shape[1]
    active_cols = []

    for k in range(p):
        xk = X[:, k]
        orig_ss = float(np.dot(xk, xk))

        if orig_ss <= 0:
            continue

        if len(active_cols) > 0:
            Q = X[:, active_cols]
            coefs, _, _, _ = np.linalg.lstsq(Q, xk, rcond=None)
            residual = xk - Q @ coefs
            resid_ss = float(np.dot(residual, residual))
        else:
            resid_ss = orig_ss

        if resid_ss / orig_ss < singular:
            continue
        else:
            active_cols.append(k)

    return len(active_cols), active_cols


def fit_bic_ols(df: pd.DataFrame, y_col: str, x_cols: list) -> tuple:
    """
    Fit OLS with constant and return (bic, model).
    Uses listwise deletion like SAS (rows with any missing in y or X dropped).
    Uses sequential singularity detection (_sas_rank) matching SAS sweep logic.
    Computes residuals via normal equations on active columns only.
    """
    X = df[x_cols].copy()
    y = df[y_col].copy()

    data = pd.concat([y, X], axis=1).dropna()
    if data.shape[0] == 0:
        return np.inf, None

    y2 = data[y_col]
    X2 = sm.add_constant(data[x_cols], has_constant='add')

    n_ = X2.shape[0]
    k_ = X2.shape[1]

    # Duplicate-column guard
    if len(x_cols) > 1:
        if (data[x_cols[-1]] == data[x_cols[-2]]).all():
            return np.inf, None

    model = sm.OLS(y2, X2).fit()

    # Saturated or under-determined
    if n_ <= k_:
        return -np.inf, model

    # Sequential singularity detection matching SAS sweep
    k, active_cols = _sas_rank(X2.values, singular=1e-7)

    # Residuals via normal equations on active columns only
    X_active = X2.values[:, active_cols]
    XtX = X_active.T @ X_active
    Xty = X_active.T @ y2.values
    beta_active = scipy.linalg.solve(XtX, Xty, assume_a='sym')
    resid = y2.values - X_active @ beta_active
    sse = float(np.dot(resid, resid))

    n_obs = n_
    mse_aic = sse / n_obs
    bic_sas = n_obs * np.log(mse_aic) + k * np.log(n_obs)

    return bic_sas, model
            

def expand_forced_class_glm(df: pd.DataFrame, class_vars: list):
    """
    Expand forced categorical block variables in a SAS PARAM=GLM style.
    SAS param=glm keeps all levels in the model statement but internally
    aliases (zeroes out) the last level to resolve collinearity with the
    intercept. We replicate this by dropping the last (highest-sorted) level,
    which makes the design matrix full-rank and matches SAS's OLS solution.
    """
    if not class_vars:
        return df.copy(), [], {}

    out = df.copy()
    expanded_cols = []
    effect_map = {}

    for var in class_vars:
        s = out[var].copy()

        dummies = pd.get_dummies(s, prefix=var, prefix_sep='_', drop_first=False, dummy_na=False)

        # Sort dummy columns by the original level values (numeric or string),
        # matching SAS's ascending sort of CLASS levels.
        # Extract the level suffix, cast back to the original dtype for sorting.
        level_map = {}
        for col in dummies.columns:
            suffix = col[len(var) + 1:]          # strip 'var_' prefix
            try:
                level_map[col] = float(suffix)   # numeric level
            except (ValueError, TypeError):
                level_map[col] = suffix           # string level
        sorted_cols = sorted(dummies.columns, key=lambda c: level_map[c])
        dummies = dummies[sorted_cols]

        # Drop the last level (highest sorted value) — SAS aliases this level
        last_col = dummies.columns[-1]
        dummies = dummies.drop(columns=[last_col])

        out = pd.concat([out, dummies.astype(float)], axis=1)

        cols = dummies.columns.tolist()
        expanded_cols.extend(cols)
        effect_map[var] = cols

    return out, expanded_cols, effect_map

def best_candidates_entry(df: pd.DataFrame, y_col: str, x_cols: list):
    X = df[x_cols].copy()
    y = df[y_col].copy()
    
    sbc_list = []
    data = pd.concat([y, X], axis=1).dropna()
    if data.shape[0] == 0:
        return x_cols
    for i in range(0, X.shape[1]):
        X1 = X[X.columns[i]]
        X2 = sm.add_constant(X1, has_constant='add')
        model = sm.OLS(y, X2).fit()
        resid = model.resid.to_numpy()
        xmat = np.asarray(X2, dtype=float)
        k = int(np.linalg.matrix_rank(xmat))
        n_obs = int(model.nobs)
        sse = (resid @ resid)
        mse_aic = sse / n_obs
        bic_sas = n_obs * np.log(mse_aic) + k * np.log(n_obs)
        sbc_list.append(bic_sas)
    
    len_cols = len(x_cols)
    heapq_indices = heapq.nsmallest(len_cols, range(len(sbc_list)), key=lambda i: sbc_list[i])
    x_cols_sorted= [x_cols[i] for i in heapq_indices]
    
    return x_cols_sorted
                    
    
# %macro GLSPLN
def glspln(
        dsin, resp_var, expl_var, n, allsig=None, cont_blk_var='', cat_blk_var='',
        maxstep=8, num_knot=100, last_knot='', name='' , initialize=0, activation=0,
        glspln_version='1.2.3', debug_stepwise=False, debug_max_steps=10,
        misx_min_step=1
):
    # ------- Guard: empty training dataset --------
    if dsin is None or len(dsin) == 0:
        print(f"GLSPLN fallback for n={n} - empty input dataset")
        return pd.DataFrame({
            'n': [n],
            'variable': [expl_var],
            'tvariable': [f"{expl_var}_ut"],
            'knot': [0],
            'beta': [0.0],
            'spline_ind': [0],
            'num_knts': [0]
        })

    if allsig is None:
        allsig = pd.DataFrame()

    global glspln_meta

    # %if 1 = &Initialize. %then %do; equivalent
    if initialize == 1:
        glspln_meta = glspln_meta.copy()
        full_values = []

        # data GLSPLN_meta;
        for _, row in glspln_meta.iterrows():
            mv = row['macro_var']

            if mv == 'version':
                full_value = glspln_version
            elif mv == 'date':
                full_value = date.today().strftime('%d%b%Y').upper()
            elif mv == 'dsin':
                full_value = str(dsin)
            elif mv == 'resp_var':
                full_value = resp_var
            elif mv == 'expl_var':
                full_value = expl_var
            elif mv == 'n':
                full_value = str(n)
            elif mv == 'allsig':
                full_value = allsig
            elif mv == 'cont_blk_var':
                full_value = cont_blk_var
            elif mv == 'cat_blk_var':
                full_value = cat_blk_var
            elif mv == 'maxstep':
                full_value = str(maxstep)
            elif mv == 'num_knot':
                full_value = str(num_knot)
            elif mv == 'last_knot':
                full_value = "" if last_knot in ("", None) else str(last_knot)
            elif mv == 'name':
                full_value = name
            elif mv == 'initialize':
                full_value = str(initialize)
            elif mv == 'activation':
                full_value = str(activation)
            else:
                full_value = ''

            full_values.append(str(full_value)[:50].strip())

        glspln_meta['value'] = full_values

        print('glspln model information. see glspln_meta.')
        print('(display limited to 50 characters.)\n')

        print(
            glspln_meta.loc[
                glspln_meta['macro_var_desc'] != 'explanatory variable',
                ['pad', 'macro_var_desc', 'value']
            ].to_string(index=False)
        )

    # delete datasets
    if initialize == 1:
        datasets_to_delete = [
            'allsig', 'association', 'parms', 'test_t', 'xvalue', 'temp', 'ttemp', 'min', 'max',
            'parm2', 'knot', 'knt', 'knt1', 'beta', 'blkvarnames', 'respvarnames'
        ]
    else:
        datasets_to_delete = [
            'association', 'parms', 'test_t', 'xvalue', 'temp', 'ttemp', 'min', 'max',
            'parm2', 'knot', 'knt', 'knt1', 'beta', 'blkvarnames', 'respvarnames'
        ]

    for ds in datasets_to_delete:
        globals().pop(ds, None)


    print()
    print(f'modeling: {resp_var} with {expl_var}')
    print(f'dsin data: \n{dsin}')

    # data ttemp creation
    ttemp = create_ttemp(dsin, expl_var, resp_var, cont_blk_var, cat_blk_var)

    # num_knot and knot_step values assigning
    num_knot, knot_step = normalize_num_knot(num_knot)

    # Initialize last_knot if it is missing.
    last_knt_default = 2 * (np.abs(ttemp[expl_var]).max() + 1)

    if last_knot is None or str(last_knot).strip() == '':
        last_knot = float(last_knt_default)

    else:
        last_knot = float(last_knot)

    # %let flip = 1;
    flip = 1


    # Count the number of block variables.
    cont_blk_var = normalize_var_list(cont_blk_var)
    cat_blk_var = normalize_var_list(cat_blk_var)

    cols = [resp_var] + cont_blk_var + cat_blk_var

    blkvarnames = pd.DataFrame({
        'name': cols,
        'type': [
            1 if np.issubdtype(ttemp[col].dtype, np.number) else 2
            for col in cols
        ]
    })

    num_blk_var = len(blkvarnames) - 1

    print(f'num_blk_var = {num_blk_var}')

    cols = [resp_var, expl_var]

    # Count the number of explanatory variables.
    respvarnames = pd.DataFrame({
        'name': cols,
        'type': [
            1 if np.issubdtype(ttemp[col].dtype, np.number) else 2
            for col in cols
        ]
    })

    num_resp_var = len(respvarnames) - 1

    print(f'num_resp_var = {num_resp_var}')


    # percentiles = np.linspace(0, 100, int(round(100/knot_step)) + 1)        # percentiles = percentiles[percentiles <= 100]

    # percentiles = np.round(np.linspace(0, 100, int(round(100/knot_step)) + 1)).astype(int)
    # percentiles[-1] = 100
    #modified0608
    percentiles = np.arange(0, 100 + knot_step, knot_step)
    percentiles = percentiles[percentiles <= 100]


    # data knots
    # q = ttemp[expl_var].dropna().to_numpy()
    # q = np.unique(q)
    # q = np.sort(q)

    knot_values = sas_pctldef5(
        ttemp[expl_var].to_numpy(),
        percentiles
    )

    knot_values = np.asarray(knot_values, dtype=float)

    knots = pd.DataFrame(
        [knot_values],
        columns=[f'kn{i+1}' for i in range(len(knot_values))]
    )

    knots['byvar'] = 1

    expected_kn_cols = [f'kn{i+1}' for i in range(num_knot)]
    for col in expected_kn_cols:
        if col not in knots.columns:
            knots[col] = np.nan

    knots = knots[['byvar'] + expected_kn_cols]

    # select max(&expl_var.), min(&expl_var.)  into :max_val, :min_val
    max_val = dsin[expl_var].max()
    min_val = dsin[expl_var].min()

    # data ttemp
    ttemp = ttemp.merge(knots, on='byvar', how='left')

    kn_cols = [f'kn{i+1}' for i in range(num_knot)]
    kn_matrix = ttemp[kn_cols].to_numpy()

    x = ttemp[expl_var].to_numpy()

    misx = pd.isna(x)
    ttemp['misx'] = misx.astype(int)

    minx = np.zeros((len(ttemp), num_knot), dtype=float)
    maxx = np.zeros((len(ttemp), num_knot), dtype=float)

    valid = ~np.isnan(x)

    for i in range(num_knot):

        ki = kn_matrix[0, i]
        linear_region = ki <= last_knot

        # SAS behavior: if missing(expl_var) then minx/maxx = 0
        # arrays already initialized to 0, so only fill valid rows
        lin_mask = valid & linear_region
        minx[lin_mask, i] = np.minimum(0.0, x[lin_mask] - ki)
        maxx[lin_mask, i] = np.maximum(0.0, x[lin_mask] - ki)

        step_mask = valid & (~linear_region)
        minx[step_mask, i] = (x[step_mask] > ki).astype(float)
        maxx[step_mask, i] = (x[step_mask] > ki).astype(float)


    for i in range(num_knot):
        ttemp[f'minx{i+1}'] = minx[:, i]
        ttemp[f'maxx{i+1}'] = maxx[:, i]

    keep_cols = (
        [expl_var, resp_var] + list(cont_blk_var) + list(cat_blk_var) + ['misx']
        + [f'minx{i+1}' for i in range(num_knot)] + [f'maxx{i+1}' for i in range(num_knot)] + ['byvar']
    )
    
    ttemp = ttemp.loc[:, keep_cols]


    # Main model fitting
    forced_cont = list(cont_blk_var)
    forced_cat = list(cat_blk_var)
    
    # Expand categorical block vars like CLASS / PARAM = GLM (closest practical match)
    ttemp, forced_cat_expanded, forced_cat_effect_map = expand_forced_class_glm(ttemp, forced_cat)
    
    ### ----modified----------------- (month_12 drop now handled by expand_forced_class_glm)
    ### ----modified-----------------     
    if "month" in forced_cat and "actualdays" in forced_cont:
        if "month" in ttemp.columns and "actualdays" in ttemp.columns:
            days_mapping = {
                1: 31, 2:28, 3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31
                }
            tmp_series = ttemp["month"].apply(lambda x:days_mapping[x])
            if (tmp_series == ttemp["actualdays"]).all():
                forced_cont.remove("actualdays")
            
    
    
    # Build forced columns
    ### ----modified-----------------
    # forced_vars = forced_cat_expanded + forced_cont + ['misx']
    forced_vars = forced_cat_expanded + forced_cont
    
    # Candidate pool in SAS model statement order
    if activation == 0:
        candidate_vars = ['misx'] + [f'minx{i+1}' for i in range(num_knot)] + [f'maxx{i+1}' for i in range(num_knot)]
    elif activation == 1:
        candidate_vars = ['misx'] + [f'maxx{i+1}' for i in range(num_knot)]
    else:
        candidate_vars = ['misx'] + [f'minx{i+1}' for i in range(num_knot)]
        # candidate_vars = [f'minx{i+1}' for i in range(num_knot)]

    selected_vars = forced_vars.copy()
    
    candidate_pool = candidate_vars.copy()
    ###modified0520
    # candidate_pool = best_candidates_entry(ttemp, resp_var,candidate_pool)
    
    best_bic, best_model = fit_bic_ols(ttemp, resp_var, selected_vars)
    
    ###-modified--
    steps_used = 0
    changed = True
    
    while changed and steps_used < maxstep:
        changed = False
        flag_forward = False
        flag_backward = False
        # Forward step
        add_best = None
        add_best_bic = np.inf
        add_best_model = None
        
        # Preserve candidate order — pick minimum BIC candidate
        for var in candidate_pool:
            if var == 'misx' and (steps_used + 1) < misx_min_step:
                continue
            bic_val, mdl = fit_bic_ols(ttemp, resp_var, selected_vars + [var])
            if bic_val < add_best_bic:
                add_best_bic = bic_val
                add_best = var
                add_best_model = mdl

        # Entry gate: candidate must improve current model BIC
        if add_best is not None and add_best_bic + 1e-12 < best_bic:
            if debug_stepwise and steps_used < debug_max_steps:
                print(
                    f"stepwise n={n} step={steps_used + 1} forward add={add_best} "
                    f"bic={add_best_bic:.12g} prev_bic={best_bic:.12g}"
                )
            selected_vars.append(add_best)
            candidate_pool.remove(add_best)
            best_bic = add_best_bic
            best_model = add_best_model
            changed = True
            flag_forward = True
        
        if flag_forward:
            steps_used += 1   
        if steps_used >=maxstep:
            break

        # Backward step
        removable = [v for v in selected_vars if v not in forced_vars]
        
        remove_best = None
        remove_best_bic = np.inf
        remove_best_model = None

        # Pick the variable whose removal gives the lowest BIC
        for var in removable:
            trial_vars = [v for v in selected_vars if v != var]
            bic_val, mdl = fit_bic_ols(ttemp, resp_var, trial_vars)

            if bic_val < remove_best_bic:
                remove_best_bic = bic_val
                remove_best = var
                remove_best_model = mdl

        if remove_best is not None and remove_best_bic + 1e-12 < best_bic:
            if debug_stepwise and steps_used < debug_max_steps:
                print(
                    f"stepwise n={n} step={steps_used + 1} backward remove={remove_best} "
                    f"bic={remove_best_bic:.12g} prev_bic={best_bic:.12g}"
                )
            selected_vars.remove(remove_best)
            candidate_pool.append(remove_best)
            best_bic = remove_best_bic
            best_model = remove_best_model
            changed = True
            flag_backward = True

        ### ----modified-----------------
        # SAS style step counting
        if flag_backward:
            steps_used += 1

    # Final backward cleanup: later additions can make an early candidate redundant.
    # This keeps the same BIC criterion but gives terms like misx one last removal check.
    cleanup_changed = True
    while cleanup_changed:
        cleanup_changed = False
        removable = [v for v in selected_vars if v not in forced_vars]

        remove_best = None
        remove_best_bic = np.inf
        remove_best_model = None

        for var in removable:
            trial_vars = [v for v in selected_vars if v != var]
            bic_val, mdl = fit_bic_ols(ttemp, resp_var, trial_vars)

            if bic_val < remove_best_bic:
                remove_best_bic = bic_val
                remove_best = var
                remove_best_model = mdl

        if remove_best is not None and remove_best_bic + 1e-12 < best_bic:
            if debug_stepwise:
                print(
                    f"stepwise n={n} cleanup remove={remove_best} "
                    f"bic={remove_best_bic:.12g} prev_bic={best_bic:.12g}"
                )
            selected_vars.remove(remove_best)
            candidate_pool.append(remove_best)
            best_bic = remove_best_bic
            best_model = remove_best_model
            cleanup_changed = True
	        
    # Calculate statistics manually (like SAS)
    # Use _sas_rank + normal equations on active columns (matches SAS sweep)
    X = np.asarray(best_model.model.exog, dtype=float)
    y_final = np.asarray(best_model.model.endog, dtype=float)
    n_obs = int(best_model.nobs)
    param_names = list(best_model.params.index)

    k, active_cols = _sas_rank(X, singular=1e-7)

    # Normal equations on active columns
    X_active = X[:, active_cols]
    XtX_active = X_active.T @ X_active
    Xty_active = X_active.T @ y_final
    beta_active = scipy.linalg.solve(XtX_active, Xty_active, assume_a='pos')

    resid = y_final - X_active @ beta_active
    sse = float(np.dot(resid, resid))

    # Full coefficient vector — aliased columns get 0 (like SAS)
    params = np.zeros(len(param_names))
    params[active_cols] = beta_active

    df_error = n_obs - k

    if df_error <= 0:
        sigma2_sas = np.nan
        mse = np.nan
        root_mse = np.nan
    else:
        sigma2_sas = sse / df_error
        mse = sigma2_sas
        root_mse = np.sqrt(mse)

    dep_mean = np.mean(y_final)

    # R² and adj-R² from own SSE (not statsmodels)
    sst = float(np.sum((y_final - dep_mean) ** 2))
    if sst > 0:
        r_squared = 1.0 - sse / sst
        adj_r2 = 1.0 - (sse / df_error) / (sst / (n_obs - 1)) if df_error > 0 else np.nan
    else:
        r_squared = np.nan
        adj_r2 = np.nan

    mse_aic = sse / n_obs

    if df_error <= 0:
        aic_sas = np.nan
        bic_sas = np.nan
        aicc_sas = np.nan
    else:
        aic_sas = n_obs * np.log(mse_aic) + 2 * k + n_obs + 2
        bic_sas = n_obs * np.log(mse_aic) + k * np.log(n_obs)
        aicc_sas = (n_obs * np.log(mse_aic) + n_obs*(n_obs+k)/(n_obs-k-2) if (n_obs-k-2) >0 else np.nan)

    association = pd.DataFrame({
        'label1': ['root_mse', 'dep_mean', 'r_squared', 'adj_r2', 'aic', 'aicc', 'sbc'],
        'nvalue1': [root_mse, dep_mean, r_squared, adj_r2, aic_sas, aicc_sas, bic_sas]})

    # Covariance from active columns — matches SAS sweep
    XtX_active_inv = np.linalg.inv(XtX_active)

    stderr_sas = np.full(len(param_names), np.nan)
    if not np.isnan(sigma2_sas):
        cov_active = sigma2_sas * XtX_active_inv
        stderr_sas[active_cols] = np.sqrt(np.diag(cov_active))

    tvalues_sas = np.where(np.isnan(stderr_sas) | (stderr_sas == 0), np.nan, params / stderr_sas)

    probt_sas = np.where(
        np.isnan(tvalues_sas),
        np.nan,
        2 * (1 - stats.t.cdf(np.abs(tvalues_sas), df=df_error))
    )

    parms = pd.DataFrame({
        'parameter': param_names,
        'estimate': params,
        'stderr': stderr_sas,
        'tvalue': tvalues_sas,
        'probt': probt_sas
    })


    # data knot
    knot = parms[
        parms['parameter'].str[:4].isin(['misx', 'minx', 'maxx'])
    ].copy()

    ...

    intercept_row = parms.loc[parms['parameter'] == 'const', 'estimate']

    intercept = (intercept_row.iloc[0] if not intercept_row.empty else None)

    knot['byvar'] = 1

    knot['dir'] = knot['parameter'].str[:3]

    knot = knot.reset_index(drop=True)
    knot['index'] = -1
    for i in range(len(knot)):
        param = str(knot.loc[i, 'parameter']).strip()
        if param.startswith('misx'):
            knot.loc[i, 'index'] = 0
        else:
            import re
            match = re.search(r'(minx|maxx)(\d+)', param)
            if match:
                knot.loc[i, 'index'] = int(match.group(2))
            else:
                knot.loc[i, 'index'] = -1

    knot = knot.merge(knots, on='byvar', how='left')

    kn_cols = [f'kn{i+1}' for i in range(num_knot)]

    expl_var_kt = np.zeros(len(knot))

    for i in range(len(knot)):
        idx = knot.loc[i, 'index']

        if idx > 0 and idx <= num_knot:
            expl_var_kt[i] = knot.loc[i, f'kn{idx}']

        elif idx == 0:
            expl_var_kt[i] = 0.0

        else:
            knot.loc[i, 'index'] = -1
            expl_var_kt[i] = np.nan

    knot[f'{expl_var}_kt'] = expl_var_kt

    knot.drop(columns=kn_cols, inplace=True)

    knot = knot.sort_values('index').reset_index(drop=True)

    if knot.empty:
        num_knts = 0
    else:
        num_knts = len(knot)

    # data code
    if knot.empty:
        ut_var = f"{expl_var}_ut"

        code = pd.DataFrame({
            "variable": [expl_var],
            "tvariable": [ut_var],
            "n": [n],
            "knot": [np.nan],
            "beta": [np.nan],
            "spline_ind": [0],
            "num_knts": [0],
            "flip_var": [expl_var],
            "line": [''],
            "end": [''],
            "code": [f"{ut_var} = 0;"]
        })
    ###--modified------------
        code.reset_index(drop=True)
        fitstat = (
        association
        .pivot_table(
            values='nvalue1',
            columns='label1',
            aggfunc='first'
        )
        .reset_index(drop=True)
    )   
        code = pd.concat([code,fitstat],axis=1)
        return code
    
    code = knot.copy()
    
    code['variable'] = expl_var
    code['tvariable'] = name
    code['n'] = n
    code['knot'] = knot[f'{expl_var}_kt']
    code['beta'] = knot['estimate']

    code['spline_ind'] = (
        (knot[f'{expl_var}_kt'] <= last_knot).astype(int) &
        (knot['index'] > 0).astype(int)
    ) * (2 * (knot['dir'] == 'max').astype(int) - 1)

    code['num_knts'] = num_knts
    code['flip_var'] = code['variable']

    
    if (pd.isna(code['tvariable'].iloc[0]) or str(code['tvariable'].iloc[0]).strip() == ''):
        code['tvariable'] = f'{expl_var}_ut'

    tvariable = code['tvariable'].iloc[0]

    code['line'] = ''
    code['end'] = ''
    code['code'] = ''

    row_numbers = np.arange(1, len(code) + 1)
    
    for i in range(len(code)):
        _n = row_numbers[i]
        idx = knot.loc[i, 'index']
        est = knot.loc[i, 'estimate']
        kt = knot.loc[i, f'{expl_var}_kt']

        #SAS - style coefficient formatting
        est_fmt = f"{est:.12g}"

        # Case 1: missing-indicator only
        if num_knts == 1 and _n == 1 and idx == 0:
            code.loc[i, 'code'] = (
                f"{code.loc[i, 'tvariable']} = {est_fmt} * missing({expl_var});"
            )
            continue

        # Case 2: Knots with missing indicator (first row)
        elif _n == 1:
            if idx == 0:
                code.loc[i, 'code'] = (
                    f"if missing({expl_var}) then {code.loc[i, 'tvariable']} = {est_fmt}; "
                    f"else {code.loc[i, 'tvariable']} = "
                )
            else:
                code.loc[i, 'code'] = (
                    f"if missing({expl_var}) then {code.loc[i, 'tvariable']} = 0; "
                    f"else {code.loc[i, 'tvariable']} = "
                )

        else:
            code.loc[i, 'code'] = ""

        # determine operator
        if _n == len(code):
            end_op = ";"
        else:
            end_op = " + "

        # Build spline term
        if idx > 0 and kt <= last_knot:

            direction = knot.loc[i, 'dir']

            code.loc[i, 'code'] += (
                f"{est_fmt}*{direction}(0, {code.loc[i, 'flip_var']} - {kt})"
                f"{end_op}"
            )

        elif idx > 0 and kt > last_knot:

            code.loc[i, 'code'] += (
                f"{est_fmt}*({code.loc[i, 'flip_var']} > {kt})"
                f"{end_op}"
            )

        elif idx < 0:
            code.loc[i, 'code'] = f"{code.loc[i, 'tvariable']} = 0;"
            
    keep_cols = ['n', 'variable', 'tvariable', 'code', 'stderr', 'tvalue', 'probt', 'byvar', 'spline_ind', 'num_knts', 'knot', 'beta']
    code = code[[c for c in keep_cols if c in code.columns]]
    
    # data fitstat
    fitstat = (
        association
        .pivot_table(
            values='nvalue1',
            columns='label1',
            aggfunc='first'
        )
        .reset_index(drop=True)
    )

    fitstat['byvar'] = 1

    # data knt1
    
    knt1 = code.merge(fitstat, on='byvar', how='left').drop(columns=['byvar'])
    
    code_macro = ' '.join(code['code'].astype(str).tolist())

    globals()['scr_code'] = code_macro

    # %if &Initialize. = 1 %then %do;
    if initialize == 1:
        allsig = pd.DataFrame({
            'n': [np.nan],
            'variable': ['12345678901234567890123456789012'],
            'tvariable': ['12345678901234567890123456789012']
        })
    
    # data &allsig.;
    # Align columns before concat (from _00: ensures consistent column order)
    all_cols = list(dict.fromkeys(list(allsig.columns) + list(knt1.columns)))
    for _c in all_cols:
        if _c not in allsig.columns:
            allsig[_c] = np.nan
        if _c not in knt1.columns:
            knt1[_c] = np.nan
    allsig = pd.concat(
        [allsig[all_cols], knt1[all_cols]],
        ignore_index=True
    )
    
    allsig = allsig[allsig['n'].notna()].reset_index(drop=True)
    
    # delete datasets
    for _var in [
        'association', 'parms', 'test_t', 'xvalue', 'temp', 'ttemp', 'min', 'max', 'code',
        'parm2', 'knot', 'knots', 'knt', 'knt1', 'beta', 'blkvarnames', 'name', 'respvarnames', 'kk'
    ]:
        if _var in globals():
            del globals()[_var]

    return allsig


def add_ut_vars(dsin, allsig, expl_var, n):
    df = dsin.copy()
    x = df[expl_var]

    sig = allsig[
        (allsig['variable'].str.upper() == expl_var.upper()) &
        (allsig['n'] == n)
    ].copy()

    # SAS behavior: create UT variable even if no spline selected
    tvar = f'{expl_var}_ut'

    if sig.empty:
        df[tvar] = 0.0
        return df

    ut = np.zeros(len(df))

    # missing indicator contribution
    mis_row = sig[sig['knot'] == 0]
    if not mis_row.empty:
        beta_mis = mis_row['beta'].iloc[0]
        ut += beta_mis * pd.isna(x).astype(int)

    # spline rows indicator contribution
    spline_rows = sig[sig['knot'] > 0]
    for _, row in spline_rows.iterrows():
        beta = row['beta']
        knot = row['knot']
        spline_ind = row['spline_ind']

        if spline_ind == -1:
            ut += beta * np.minimum(0, x - knot)
        else:
            ut += beta * np.maximum(0, x - knot)
    df[tvar] = ut
    return df


# %macro shft_min
def shft_min(dsin, allsig, expl_var):

    ut_var = f'{expl_var}_ut'
    min_val = dsin[ut_var].min()

    print(f'min = {min_val}')

    # data &allsig.;
    allsig = allsig.copy()
    allsig['code2'] = ''

    mask = (allsig['variable'].str.upper().str.strip() == expl_var.upper().strip())
    allsig.loc[mask, 'code2'] = (
        f'{ut_var} = {ut_var} - {min_val} + 1;'
    )

    # data &dsin.;
    dsin = dsin.copy()
    dsin[ut_var] = dsin[ut_var] - min_val + 0

    return dsin, allsig


# %macro GLSPLN_plots
def glspln_plots(plot_dat, allsig, resp_var, var, out_folder=None):

    if out_folder is None:
        out_folder = os.getcwd()

    mask = allsig['variable'].str.upper().str.strip() == var.upper().strip()

    var_trans = ' '.join(
        allsig.loc[mask, 'code'].astype(str).tolist()
    )

    tvar = (
        allsig.loc[mask, 'tvariable']
        .astype(str)
        .iloc[0]
    )

    # data tt_plot
    tt_plot = plot_dat.loc[
        (plot_dat['variable'].str.upper().str.strip() == var.upper().strip()) &
        (plot_dat['xrank'].notna())
    ].copy()

    tt_plot[var] = tt_plot['bin_mean']

    for idx, row in tt_plot.iterrows():
        local_env = row.to_dict()
        try:
            exec(var_trans, {}, local_env)
            for k, v in local_env.items():
                tt_plot.loc[idx, k] = v
        except Exception:
            pass


    shift = (
        tt_plot['resp_mean'].sum()
        - tt_plot[tvar].sum()
    ) / tt_plot[var].count()

    tt_plot[tvar] = tt_plot[tvar] + shift


    os.makedirs(out_folder, exist_ok=True)

    plt.figure(figsize=(8, 6))

    plt.scatter(
        tt_plot['bin_mean'],
        tt_plot['resp_mean'],
        color='blue',
        marker='+',
        label='response mean'
    )

    plt.plot(
        tt_plot['bin_mean'],
        tt_plot[tvar],
        color='red',
        marker='x',
        linestyle='-',
        label=tvar
    )


    plt.title(f'linear spline transform for {var}', fontsize=14)
    plt.xlabel('bin mean')
    plt.ylabel(resp_var)

    plt.legend(loc='upper center')

    output_path = os.path.join(out_folder, 'GLSPN.gif')
    plt.savefig(output_path, format='gif')
    plt.close()

    return tt_plot


#######################################
# Code end
#######################################
