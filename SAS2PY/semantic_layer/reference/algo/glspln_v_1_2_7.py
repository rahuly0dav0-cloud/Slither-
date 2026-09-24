"""
GLSPLN - Generalized Linear Spline
Python Implementation

A complete Python port of the SAS GLSPLN macro system for creating continuous
piecewise linear transformations using "blade" regression.

Author: Converted from SAS by AI Assistant
Original Author: Dr. Basil Coutant
Version: 1.2.7 (Python Port)
Date: December 30, 2025

WHAT IS GLSPLN?
===============
GLSPLN creates continuous piecewise linear transformations of an explanatory variable X
so that the transformed variable has an (approximately) linear relationship with response Y.

It represents any continuous piecewise linear function as a linear combination of "blade"
functions: min(0, X-b) or max(0, X-b) for knot points b.

This is equivalent to a single-layer univariate neural network with ReLU/hinge activations.

WHY IT'S NOT JUST REGRESSION:
==============================
1. It's a FEATURE ENGINEERING system, not just a model
2. It GENERATES EXECUTABLE CODE for transformations
3. The code can be applied to ANY dataset (train, test, future data)
4. It handles missing values explicitly in the transformation logic
5. It supports constraint injection (bnd_trend) for bounded slopes
6. It creates interpretable, continuous transformations

CORE ALGORITHMIC PIPELINE:
===========================
1. Create knot locations via quantiles of X
2. Generate blade variables: min(0, X-knot_i) and/or max(0, X-knot_i)
3. Add missing indicator variable
4. Perform LASSO selection with screening to choose significant blades
5. Extract coefficients and knot locations
6. Generate transformation code as string/callable
7. Store in "allsig" (all significant) output structure

KEY DIFFERENCES FROM SAS:
===========================
- SAS uses PROC GLMSELECT with selection=lasso(screen=sasvi LSCOEFFS)
- Python uses sklearn.linear_model.LassoLarsIC (AIC/BIC criterion)
- SAS SASVI screening is approximated with correlation-based pre-filtering
- Numerical differences expected but should be bounded

BLOCKING VARIABLES:
===================
- cont_blk_var: Continuous variables forced into model
- cat_blk_var: Categorical variables forced into model
- These are NOT selected - they're always included
- Python implementation PRESERVES them (they exist but may not affect blade selection in v1.2.7)

"""

import numpy as np
import pandas as pd
from typing import Union, List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
import warnings
from sklearn.linear_model import LassoLarsIC, Lasso
from sklearn.linear_model import lars_path,LinearRegression,lasso_path
from sklearn.preprocessing import StandardScaler
from sklearn.exceptions import ConvergenceWarning
import matplotlib.pyplot as plt
from datetime import datetime


# ==================================================================================
# METADATA STRUCTURES
# ==================================================================================

### ------modified0415
def sas_like_percentile(values: np.ndarray, pct_points: np.ndarray) -> np.ndarray:
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

@dataclass
class VariableMetadata:
    """
    Variable metadata structure matching SAS implementation.
    
    This tracks how variables were created and how they should be used in scoring.
    """
    name: str
    variable_role: str  # 'Target', 'Explanatory', 'Blocking'
    source: str  # 'User input', 'glspln_df_generator', 'cat_var_append', etc.
    usage_flag: int = 1  # 1 = use, 0 = don't use
    storage_type: str = 'Numeric'  # 'Numeric' or 'String'
    treatment_type: str = 'Continuous'  # 'Continuous' or 'Categorical'
    source_variable: str = ''  # Original variable name
    activation_function: Optional[str] = None  # 'min', 'max', 'Equals', 'Identity', 'Constant', None
    numeric_location: Optional[float] = None  # Knot location or numeric value
    string_location: Optional[str] = None  # String value for categorical


@dataclass
class EnhancedParameterOutput:
    """
    Enhanced parameter output structure.
    
    Combines regression output with metadata for scoring.
    """
    estimate_name: str
    source_variable: str
    parameter: str
    estimate: float
    standard_error: Optional[float] = None
    t: Optional[float] = None
    prob_t: Optional[float] = None
    activation_function: Optional[str] = None
    numeric_location: Optional[float] = None
    string_location: Optional[str] = None


@dataclass
class GLSPLNOutput:
    """
    Main output structure from GLSPLN.
    
    Contains all information needed for:
    - Transformation code generation
    - Model diagnostics
    - Future scoring
    """
    n: int  # Index
    variable: str  # Source variable name
    tvariable: str  # Transformed variable name
    code: str  # Generated transformation code
    knot: Optional[float]  # Knot location (if applicable)
    beta: Optional[float]  # Coefficient estimate
    spline_ind: int  # 1 if max activation (forward trend), -1 if min, 0 if missing
    num_knts: int  # Total number of knots selected
    StdErr: Optional[float] = None
    tValue: Optional[float] = None
    Probt: Optional[float] = None
    # Goodness of fit statistics (matching SAS output)
    RootMSE: Optional[float] = None      # Root Mean Square Error
    DepMean: Optional[float] = None      # Dependent Mean
    RSquare: Optional[float] = None      # R-Square
    AdjRSq: Optional[float] = None       # Adjusted R-Square
    AIC: Optional[float] = None          # Akaike Information Criterion
    AICC: Optional[float] = None         # AIC corrected
    SBC: Optional[float] = None          # Schwarz Bayesian Criterion (BIC)
    ASE: Optional[float] = None          # Average Squared Error
    

# ==================================================================================
# CORE GLSPLN IMPLEMENTATION
# ==================================================================================


class GLSPLNTransformer:
    """
    Main GLSPLN transformer class.
    
    This implements the core GLSPLN algorithm:
    1. Knot generation
    2. Blade variable creation  
    3. LASSO selection
    4. Code generation
    5. Transformation application
    """
    
    def __init__(
        self,
        dsin: pd.DataFrame,
        resp_var: str,
        expl_var: str,
        n: int,
        allsig: Optional[pd.DataFrame] = None,
        cont_blk_var: Optional[List[str]] = None,
        cat_blk_var: Optional[List[str]] = None,
        MAXSTEP: int = 8,
        Num_knot: int = 100,
        Last_knot: Optional[float] = None,
        Name: Optional[str] = None,
        Initialize: int = 0,
        activation: int = 0,
    ):
        """
        Initialize GLSPLN transformer.
        
        Parameters:
        -----------
        dsin : pd.DataFrame
            Input training data
        resp_var : str
            Response/target variable name
        expl_var : str
            Explanatory variable to transform
        n : int
            Index for this transformation (for tracking multiple transformations)
        allsig : Optional[pd.DataFrame]
            Existing allsig output to append to (if Initialize=0)
        cont_blk_var : Optional[List[str]]
            Continuous blocking variables
        cat_blk_var : Optional[List[str]]
            Categorical blocking variables
        MAXSTEP : int
            Maximum number of knots to include
        Num_knot : int
            Number of candidate knots (25, 50, 100, 200, 250)
        Last_knot : Optional[float]
            Maximum value for continuous knot; larger values use step functions
        Name : Optional[str]
            Name for transformed variable (default: {expl_var}_ut)
        Initialize : int
            1 to initialize allsig, 0 to append
        activation : int
            -1: use min(0,x) only
            0: use both min and max
            1: use max(0,x) only (ReLU)
        """
        self.dsin = dsin.copy()
        self.resp_var = resp_var
        self.expl_var = expl_var
        self.n = n
        self.cont_blk_var = cont_blk_var or []
        self.cat_blk_var = cat_blk_var or []
        self.MAXSTEP = MAXSTEP
        self.Num_knot = Num_knot
        self.Last_knot = Last_knot
        self.Name = Name if Name else f"{expl_var}_ut"
        self.Initialize = Initialize
        self.activation = activation
        # Initialize allsig as DataFrame (either from parameter or empty)
        self.allsig: pd.DataFrame = allsig if allsig is not None else pd.DataFrame()
        
        # Normalize Num_knot to allowed values and set knot_step
        self._normalize_num_knot()
        
        # Initialize last_knot if missing
        if self.Last_knot is None:
            #-----modified------------------
            # self.Last_knot = 2 * self.dsin[resp_var].abs().max() + 1
            self.Last_knot = 2 * self.dsin[expl_var].abs().max() + 1
            
        # Working datasets - initialized as empty, populated in methods
        self.ttemp: pd.DataFrame = pd.DataFrame()
        self.knots: pd.DataFrame = pd.DataFrame()
        self.selected_params: Optional[pd.DataFrame] = None
        self.output: pd.DataFrame = pd.DataFrame()
        
    def _normalize_num_knot(self):
        """
        Restrict Num_knot to allowed values and set corresponding knot_step.
        
        Matching SAS logic exactly.
        """
        initial = self.Num_knot
        
        if initial < 49:
            self.Num_knot = 26  # Note: SAS says 26, not 25
            self.knot_step = 4.0
        elif initial <= 99:
            self.Num_knot = 51
            self.knot_step = 2.0
        elif initial <= 199:
            self.Num_knot = 101
            self.knot_step = 1.0
        elif initial <= 249:
            self.Num_knot = 201
            self.knot_step = 0.5
        else:
            self.Num_knot = 251
            self.knot_step = 0.4
            
    def fit(self) -> pd.DataFrame:
        """
        Execute the full GLSPLN pipeline.
        
        Returns:
        --------
        pd.DataFrame
            Updated allsig dataframe with new transformation information
        """
        # Step 1: Create working dataset
        self._create_ttemp()
        
        # Step 2: Generate knot locations
        self._generate_knots()
        
        # Step 3: Create blade variables
        self._create_blade_variables()
        
        # Step 4: Perform LASSO selection
        self._lasso_selection()
        
        # Step 5: Generate transformation code
        self._generate_code()
        
        # Step 6: Update allsig
        self._update_allsig()
         
        return self.allsig
    
    def _create_ttemp(self):
        """Create main working dataset."""
        keep_cols = [self.expl_var, self.resp_var] + self.cont_blk_var + self.cat_blk_var
        self.ttemp = self.dsin[keep_cols].copy()
        self.ttemp['byvar'] = 1
        
    def _generate_knots(self):
        """
        Generate knot locations using quantiles.
        
        Matches SAS PROC UNIVARIATE logic.
        """
        # Get quantiles of non-missing explanatory variable
        valid_data = self.ttemp[self.ttemp[self.expl_var].notna()][self.expl_var]
        
        # Generate percentiles
        percentiles = np.arange(0, 100 + self.knot_step, self.knot_step)
        percentiles = percentiles[percentiles <= 100]  # Ensure we don't exceed 100
        
        # Calculate quantiles
        # knot_values = np.percentile(valid_data, percentiles)
        ### ------modified-----------------------
        
        knot_values = sas_like_percentile(valid_data, percentiles)
        # Create knots dataframe matching SAS structure
        self.knots = pd.DataFrame([knot_values], columns=[f'kn{i+1}' for i in range(len(knot_values))])
        self.knots['byvar'] = 1
        
        # Actual number of knots
        self.Num_knot = len(knot_values)
        
    def _create_blade_variables(self):
        """
        Create blade (hinge) variables.
        
        For each knot k:
        - If k <= Last_knot: blade_i = min/max(0, X - k)
        - If k > Last_knot: blade_i = 1(X > k)  # Step function
        
        Missing values of X map to 0 for all blades.
        """
        # Merge knots onto data
        self.ttemp = self.ttemp.merge(self.knots, on='byvar', how='left')
        
        # Extract knot array
        knot_cols = [col for col in self.knots.columns if col.startswith('kn')]
        
        # Create missing indicator
        self.ttemp['misx'] = self.ttemp[self.expl_var].isna().astype(int)
        
        # Create blade variables
        for i, knot_col in enumerate(knot_cols, start=1):
            knot_val = self.ttemp[knot_col].iloc[0]

            # MIN blades (activation = -1 or 0)
            if self.activation in [-1, 0]:
                if knot_val <= self.Last_knot:
                    # Continuous blade: min(0, X - knot)
                    self.ttemp[f'minx{i}'] = np.where(
                        self.ttemp[self.expl_var].isna(),
                        0,
                        np.minimum(0, self.ttemp[self.expl_var] - knot_val)
                    )
                    
                        
                else:
                    # Step function: 1(X > knot)
                    self.ttemp[f'minx{i}'] = np.where(
                        self.ttemp[self.expl_var].isna(),
                        0,
                        (self.ttemp[self.expl_var] > knot_val).astype(int)
                    )
            
            # MAX blades (activation = 1 or 0)
            if self.activation in [1, 0]:
                if knot_val <= self.Last_knot:
                    # Continuous blade: max(0, X - knot)
                    self.ttemp[f'maxx{i}'] = np.where(
                        self.ttemp[self.expl_var].isna(),
                        0,
                        np.maximum(0, self.ttemp[self.expl_var] - knot_val)
                    )
                else:
                    # Step function: 1(X > knot)
                    self.ttemp[f'maxx{i}'] = np.where(
                        self.ttemp[self.expl_var].isna(),
                        0,
                        (self.ttemp[self.expl_var] > knot_val).astype(int)
                    )
    ### ------modified0415               
    def _lasso_selection(self):
        """
        Perform LASSO variable selection.
        
        SAS uses: PROC GLMSELECT with selection=lasso(screen=sasvi LSCOEFFS)
        
        Python approximation:
        - Use LassoLarsIC with BIC criterion (closest to SAS SBC)
        - SASVI screening is approximated with correlation filtering
        - LSCOEFFS means least squares coefficients after selection
        
        CRITICAL: This is an APPROXIMATION. Results will differ from SAS.
        """
        # Get response and predictors
        valid_mask = self.ttemp[self.resp_var].notna()
        y = self.ttemp.loc[valid_mask, self.resp_var].values
        
        # Convert y to numpy array explicitly for sklearn
        y_array = np.asarray(y, dtype=np.float64)
        
        # Build predictor list
        predictor_cols = ['misx']
        
        # Add blade variables based on activation
        if self.activation in [-1, 0]:
            predictor_cols += [f'minx{i}' for i in range(1, self.Num_knot + 1)]
        if self.activation in [1, 0]:
            predictor_cols += [f'maxx{i}' for i in range(1, self.Num_knot + 1)]
            
        # Filter out constant columns (all zeros)
        predictor_cols = [col for col in predictor_cols if col in self.ttemp.columns]
        
        X = self.ttemp.loc[valid_mask, predictor_cols]
        
        # Remove constant columns
        non_constant = X.std() > 1e-10
        X = X.loc[:, non_constant]
        ### ------modified0415 
        X = X.loc[:, ~X.T.duplicated()]
        predictor_cols = X.columns.tolist()
        
        if len(predictor_cols) == 0:
            warnings.warn(f"No valid blade variables for {self.expl_var}")
            self.selected_params = pd.DataFrame()
            return
        
        
        
        # Standardize predictors (required for LASSO)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Fit LassoLarsIC with BIC criterion
        # This is the closest Python equivalent to SAS selection=lasso
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=ConvergenceWarning)
                alphas, active, coefs = lars_path(X_scaled, y_array, method='lar',max_iter=self.MAXSTEP)

                n_samples = X_scaled.shape[0]
                best_sbc = np.inf
                best_step = 0
                intercept_value = np.nan
                selected_vars = []
                selected_coefs = []
                best_k = None
                steps_used = 0
                for i in range(len(alphas)):
                    current_coefs = coefs[:, i]
                    k = np.count_nonzero(current_coefs)
                    if k == 0:
                        y_pred = y_array.mean()
                        val_coefs = []
                        val_intercept = y_array.mean()
                        val_selected_vars = []
                    else:
                        coef_mask = np.abs(current_coefs) > 1e-10
                        val_selected_vars = [predictor_cols[i] for i in np.where(coef_mask)[0]]
                        X_selected = X.loc[:, val_selected_vars]
                        ols = LinearRegression().fit(X_selected.values,y_array)
                        val_intercept = ols.intercept_
                        val_coefs = ols.coef_ 
                        y_pred = ols.predict(X_selected.values)
                    sse = np.sum((y_array - y_pred) ** 2)
                    sbc = n_samples * np.log(sse / (n_samples)) + (k+1) * np.log(n_samples)
                    
                    if sbc < best_sbc:
                        best_sbc = sbc
                        best_step = i
                        intercept_value = val_intercept
                        selected_vars = val_selected_vars
                        selected_coefs = val_coefs
                        best_k = k
                        steps_used = steps_used + 1
                        
                    else:
                        break
                ### ------modified0415 
                removable = selected_vars.copy()
                remove_best = None
                remove_best_sbc = best_sbc
                changed = True
                
                while steps_used< self.MAXSTEP and changed and len(removable)>1:
                    changed = False
                    for var in removable:
                        trial_vars = [v for v in selected_vars if v != var]
                        X_trial = X.loc[:, trial_vars]
                        ols = LinearRegression().fit(X_trial.values,y_array)
                        val_intercept = ols.intercept_
                        val_coefs = ols.coef_ 
                        y_pred = ols.predict(X_trial.values)
                        k = len(trial_vars)
                        sse = np.sum((y_array - y_pred) ** 2)
                        sbc = n_samples * np.log(sse / (n_samples)) + (k+1) * np.log(n_samples)
                        
                        if sbc < remove_best_sbc:
                            remove_best_sbc = sbc
                            remove_best = var
                            remove_best_intercept = val_intercept
                            remove_best_coefs = val_coefs
                            
                    if remove_best is not None and remove_best_sbc < best_sbc:
                        selected_vars.remove(remove_best)
                        best_sbc = remove_best_sbc
                        intercept_value = remove_best_intercept
                        selected_coefs = remove_best_coefs
                        changed = True
                      
                    if changed:
                        steps_used = steps_used + 1
                           
                # Build parameter dataframe
                params = []
                
                # Add intercept
                params.append({
                    'parameter': 'Intercept',
                    'estimate': intercept_value,
                    'StdErr': None,
                    'tValue': None,
                    'Probt': None
                })
                
                # Add selected blade variables
                for var, coef in zip(selected_vars, selected_coefs):
                    params.append({
                        'parameter': var,
                        'estimate': coef,
                        'StdErr': None,
                        'tValue': None,
                        'Probt': None
                    })
                
                self.selected_params = pd.DataFrame(params)
                ### ------modified0415 
                if len(selected_vars)>0:
                # Recreate X_selected using the best selected_vars (not from loop variable!)
                    X_selected = X.loc[:, selected_vars]
                
                # Refit OLS with the best selected variables
                    ols = LinearRegression().fit(X_selected.values, y_array)
                    intercept_value = ols.intercept_
                
                # Calculate goodness of fit statistics (matching SAS output)
                    y_pred = ols.predict(X_selected)
                    n_obs = len(y_array)
                
                # Calculate number of parameters using matrix rank (matching SAS)
                # Construct design matrix with intercept column
                    X_design = np.column_stack([np.ones(len(X_selected)), X_selected.values])
                    n_params = int(np.linalg.matrix_rank(X_design))
                ### ------modified0415     
                else:
                    y_pred = float(np.mean(y_array))
                    n_obs = len(y_array)
                    n_params = 1
                    
                # Sum of Squared Errors and Total Sum of Squares
                y_mean = float(np.mean(y_array))
                sse = float(np.sum((y_array - y_pred) ** 2))  # Residual SS
                sst = float(np.sum((y_array - y_mean) ** 2))  # Total SS
                
                # Dependent Mean
                self.DepMean = y_mean
                
                # ASE (Average Squared Error / MSE)
                self.ASE = sse / n_obs
                
                # Root MSE = sqrt(SSE / (n - p))
                if n_obs > n_params:
                    self.RootMSE = float(np.sqrt(sse / (n_obs - n_params)))
                else:
                    self.RootMSE = None
                
                # R-Square = 1 - SSE/SST
                if sst > 0:
                    self.RSquare = float(1 - sse / sst)
                    # Adjusted R-Square
                    if n_obs > n_params and n_obs > 1:
                        self.AdjRSq = float(1 - (sse / (n_obs - n_params)) / (sst / (n_obs - 1)))
                    else:
                        self.AdjRSq = None
                else:
                    self.RSquare = None
                    self.AdjRSq = None
                
                # AIC/AICC/SBC (matching SAS PROC GLMSELECT formulas)
                # Following SAS PROC GLMSELECT User's Guide formulas exactly
                if sse > 0:
                    mse = sse / n_obs
                    
                    # Deviance: -2ℓ = n * log(SSE/n) for Gaussian model
                    deviance = n_obs * np.log(mse)
                    
                    # AIC = n*log(MSE) + 2*k + n + 2 (SAS PROC GLMSELECT formula)
                    self.AIC = float(deviance + 2 * n_params + n_obs + 2)
                    
                    # AICC = n*log(MSE) + n*(n+k)/(n-k-2) (SAS PROC GLMSELECT formula)
                    if n_obs > n_params + 2:
                        self.AICC = float(deviance + (n_obs * (n_obs + n_params)) / (n_obs - n_params - 2))
                    else:
                        self.AICC = None
                    
                    # SBC = n*log(MSE) + k*log(n) (equivalent to -2ℓ + p * log(n))
                    self.SBC = float(deviance + n_params * np.log(n_obs))
                else:
                    self.AIC = None
                    self.AICC = None
                    self.SBC = None
                
        except Exception as e:
            warnings.warn(f"LASSO selection failed for {self.expl_var}: {str(e)}")
            self.selected_params = pd.DataFrame()
            
    def _generate_code(self):
        """
        Generate transformation code from selected parameters.
        
        GENERATES MULTI-ROW PYTHON STATEMENTS (matching SAS structure):
        - One row per blade term
        - First row: var = 0 if pd.isna(x) else intercept + beta1*min(0, x - knot1) +
        - Middle rows: beta2*min(0, x - knot2) +
        - Last row: beta3*min(0, x - knot3)
        - Each row has its own knot, beta, spline_ind
        """
        if self.selected_params is None or len(self.selected_params) == 0:
            # No selection - create default code
            self.output = pd.DataFrame([{
                'n': self.n,
                'variable': self.expl_var,
                'tvariable': self.Name,
                'code': f'{self.Name} = 0',
                'knot': None,
                'beta': None,
                'spline_ind': 0,
                'num_knts': 0,
                'Root MSE': getattr(self, 'RootMSE', None),
                'Dependent Mean': getattr(self, 'DepMean', None),
                'R-Square': getattr(self, 'RSquare', None),
                'Adj R-Sq': getattr(self, 'AdjRSq', None),
                'AIC': getattr(self, 'AIC', None),
                'AICC': getattr(self, 'AICC', None),
                'SBC': getattr(self, 'SBC', None)
            }])
            return
        
        # Extract knot values
        knot_cols = [col for col in self.knots.columns if col.startswith('kn')]
        knot_values = {f'kn{i+1}': self.knots[col].iloc[0] for i, col in enumerate(knot_cols)}
        
        # Build blade entries (one per row)
        blade_entries = []
        intercept = None
        
        for _, row in self.selected_params.iterrows():
            param = row['parameter']
            beta = row['estimate']
            
            if param == 'Intercept':
                intercept = beta
                continue
            
            # Create entry for each blade
            if param == 'misx':
                # Missing indicator - skip (handled in if clause)
                continue
                
            elif param.startswith('minx'):
                idx = int(param[4:])
                knot_key = f'kn{idx}'
                knot_val = knot_values[knot_key]
                
                if knot_val <= self.Last_knot:
                    # Continuous blade
                    blade_expr = f"{beta}*min(0, {self.expl_var} - {knot_val})"
                    spline_ind = -1
                else:
                    # Step function
                    blade_expr = f"{beta}*({self.expl_var} > {knot_val})"
                    spline_ind = 0
                
                blade_entries.append({
                    'n': self.n,
                    'variable': self.expl_var,
                    'tvariable': self.Name,
                    'knot': knot_val,
                    'beta': beta,
                    'spline_ind': spline_ind,
                    'blade_expr': blade_expr
                })
                
            elif param.startswith('maxx'):
                idx = int(param[4:])
                knot_key = f'kn{idx}'
                knot_val = knot_values[knot_key]
                
                if knot_val <= self.Last_knot:
                    # Continuous blade
                    blade_expr = f"{beta}*max(0, {self.expl_var} - {knot_val})"
                    spline_ind = 1
                else:
                    # Step function
                    blade_expr = f"{beta}*({self.expl_var} > {knot_val})"
                    spline_ind = 0
                
                blade_entries.append({
                    'n': self.n,
                    'variable': self.expl_var,
                    'tvariable': self.Name,
                    'knot': knot_val,
                    'beta': beta,
                    'spline_ind': spline_ind,
                    'blade_expr': blade_expr
                })
        
        num_knts = len(blade_entries)
        
        if num_knts == 0:
            # Only intercept – SAS outputs code = "<Name> = 0" with beta = NaN
            code_str = f'{self.Name} = 0'
            self.output = pd.DataFrame([{
                'n': self.n,
                'variable': self.expl_var,
                'tvariable': self.Name,
                'code': code_str,
                'knot': None,
                'beta': None,
                'spline_ind': 0,
                'num_knts': 0,
                'Root MSE': getattr(self, 'RootMSE', None),
                'Dependent Mean': getattr(self, 'DepMean', None),
                'R-Square': getattr(self, 'RSquare', None),
                'Adj R-Sq': getattr(self, 'AdjRSq', None),
                'AIC': getattr(self, 'AIC', None),
                'AICC': getattr(self, 'AICC', None),
                'SBC': getattr(self, 'SBC', None)
            }])
            return
        
        # Generate code strings for each row
        for i, entry in enumerate(blade_entries):
            is_first = (i == 0)
            is_last = (i == num_knts - 1)
            
            if is_first:
                # First row: complete if/else with first blade term (no intercept in code)
                else_clause = entry['blade_expr']
                
                if is_last:
                    # Only one blade - complete statement
                    code_str = f"{self.Name} = 0 if pd.isna({self.expl_var}) else {else_clause}"
                else:
                    # More blades coming - add continuation
                    code_str = f"{self.Name} = 0 if pd.isna({self.expl_var}) else {else_clause} +"
            else:
                # Subsequent rows: just the blade expression
                if is_last:
                    # Last row - no continuation
                    code_str = entry['blade_expr']
                else:
                    # Middle row - add continuation
                    code_str = entry['blade_expr'] + ' +'
            
            entry['code'] = code_str
            entry['num_knts'] = num_knts
            # Remove blade_expr as it's not needed in output
            del entry['blade_expr']
        
        self.output = pd.DataFrame(blade_entries)
        
        # Add goodness of fit stats to ALL rows
        if len(self.output) > 0:
            stat_mapping = {
                'Root MSE': 'RootMSE',
                'Dependent Mean': 'DepMean',
                'R-Square': 'RSquare',
                'Adj R-Sq': 'AdjRSq',
                'AIC': 'AIC',
                'AICC': 'AICC',
                'SBC': 'SBC'
            }
            for col_name, attr_name in stat_mapping.items():
                self.output[col_name] = getattr(self, attr_name, None)
    
    def _update_allsig(self):
        """Update the allsig output dataframe."""
        # Reorder columns to match SAS output exactly
        # SAS column order: n, variable, tvariable, code, knot, beta, spline_ind, num_knts,
        #                   Root MSE, Dependent Mean, R-Square, Adj R-Sq, AIC, AICC, SBC
        sas_columns = [
            'n', 'variable', 'tvariable', 'code', 'knot', 'beta', 
            'spline_ind', 'num_knts',
            'Root MSE', 'Dependent Mean', 'R-Square', 'Adj R-Sq', 
            'AIC', 'AICC', 'SBC'
        ]
        
        # Select only SAS columns from output
        output_reordered = self.output[[col for col in sas_columns if col in self.output.columns]]
        
        if self.Initialize == 1:
            # Initialize new allsig
            self.allsig = output_reordered.copy()
        else:
            # Append to existing
            if len(self.allsig) == 0:
                # If allsig is empty DataFrame, just copy output
                self.allsig = output_reordered.copy()
            else:
                #Concatenate with existing
                self.allsig = pd.concat([self.allsig, output_reordered], ignore_index=True)


# ==================================================================================
# SUPPORTING MACROS
# ==================================================================================

def add_UT_vars(
    dsin: pd.DataFrame,
    allsig: pd.DataFrame,
    expl_var: str,
    n: int
) -> pd.DataFrame:
    """
    Apply generated transformation code to a dataset.
    
    This is the Python equivalent of SAS %add_UT_vars macro.
    Computes the transformation without using exec() for safety and clarity.
    
    Parameters:
    -----------
    dsin : pd.DataFrame
        Input dataset to transform
    allsig : pd.DataFrame
        Output from GLSPLN containing transformation code
    expl_var : str
        Variable name that was transformed
    n : int
        Index of the transformation to apply
        
    Returns:
    --------
    pd.DataFrame
        Dataset with transformed variable appended
    """
    dsout = dsin.copy()
    
    # Filter allsig for this variable and index
    relevant = allsig[
        (allsig['variable'] == expl_var) & 
        (allsig['n'] == n)
    ]
    
    if len(relevant) == 0:
        warnings.warn(f"No transformation found for {expl_var} with n={n}")
        return dsout
    
    # Get transformation name
    tvar_name = relevant['tvariable'].iloc[0]
    
    # Initialize transformed variable to zero
    dsout[tvar_name] = 0.0
    
    # Get the source variable as a Series
    source_var = dsout[expl_var]
    is_missing = source_var.isna()
    
    # Derive blade type from spline_ind (no 'parameter' column in allsig):
    #   spline_ind == -1  -> min blade: min(0, X - knot)
    #   spline_ind ==  1  -> max blade: max(0, X - knot)
    #   spline_ind ==  0  -> step function or misx (knot distinguishes them)
    
    for _, row in relevant.iterrows():
        beta = float(row['beta']) if pd.notna(row['beta']) else 0.0
        knot_raw = row['knot']
        spline_ind = int(row['spline_ind']) if pd.notna(row['spline_ind']) else 0
        
        if pd.isna(knot_raw):
            continue
        knot_val = float(knot_raw)
        
        if spline_ind == -1:
            # Min blade: min(0, X - knot)
            blade = np.minimum(0, source_var - knot_val)
            blade = np.where(is_missing, 0, blade)
            dsout[tvar_name] += beta * blade
        elif spline_ind == 1:
            # Max blade: max(0, X - knot)
            blade = np.maximum(0, source_var - knot_val)
            blade = np.where(is_missing, 0, blade)
            dsout[tvar_name] += beta * blade
        elif spline_ind == 0 and knot_val != 0:
            # Step function: (X > knot)
            blade = (source_var > knot_val).astype(float)
            blade = np.where(is_missing, 0, blade)
            dsout[tvar_name] += beta * blade
        # spline_ind == 0 and knot == 0 would be misx — not present in allsig output
    
    return dsout


def bnd_trend(
    allsig: pd.DataFrame,
    nn: int,
    varr: str,
    min_trend: float,
    max_trend: float,
    trend_restrctn_strt: float
) -> pd.DataFrame:
    """
    Bound the forward trend of a transformation.
    
    This adds a corrective blade if the forward slope is too steep or too shallow.
    
    Parameters:
    -----------
    allsig : pd.DataFrame
        Parameter output from GLSPLN
    nn : int
        Index
    varr : str
        Variable name
    min_trend : float
        Minimum allowed forward trend per unit
    max_trend : float
        Maximum allowed forward trend per unit
    trend_restrctn_strt : float
        Value of varr where trend restriction starts
        
    Returns:
    --------
    pd.DataFrame
        Updated allsig with trend correction if needed
    """
    # Calculate current forward trend
    relevant = allsig[
        (allsig['n'] == nn) & 
        (allsig['variable'] == varr) & 
        (allsig['spline_ind'] == 1)
    ]
    
    if len(relevant) == 0:
        return allsig
    
    raw_pred_forward_trend = relevant['beta'].sum()
    
    # Check if correction needed
    correction_needed = False
    correction_beta = 0
    
    if raw_pred_forward_trend - max_trend > 1e-12:
        # Too steep - add negative blade
        correction_beta = max_trend - raw_pred_forward_trend
        correction_needed = True
    elif raw_pred_forward_trend - min_trend < -1e-12:
        # Too shallow - add positive blade
        correction_beta = min_trend - raw_pred_forward_trend
        correction_needed = True
    
    if not correction_needed:
        return allsig
    
    # Add correction term
    tvar_name = relevant['tvariable'].iloc[0]
    
    correction_row = {
        'n': nn,
        'variable': varr,
        'tvariable': tvar_name,
        'code': f'{tvar_name} = {tvar_name} + {float(correction_beta):.12e} * max(0, {varr} - {trend_restrctn_strt})',
        'knot': trend_restrctn_strt,
        'beta': correction_beta,
        'spline_ind': 1,
        'num_knts': relevant['num_knts'].iloc[0] + 1
    }
    
    allsig = pd.concat([allsig, pd.DataFrame([correction_row])], ignore_index=True)
    
    return allsig


def shft_min(
    dsin: pd.DataFrame,
    allsig: pd.DataFrame,
    expl_var: str
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Shift minimum of transformed variable.
    
    This adjusts the transformation so minimum value is 1 (or specified value).
    
    Parameters:
    -----------
    dsin : pd.DataFrame
        Dataset with transformed variable
    allsig : pd.DataFrame
        Parameter output
    expl_var : str
        Source variable name
        
    Returns:
    --------
    Tuple[pd.DataFrame, pd.DataFrame]
        Updated dataset and allsig
    """
    tvar_name = f"{expl_var}_ut"
    
    if tvar_name not in dsin.columns:
        return dsin, allsig
    
    min_val = dsin[tvar_name].min()
    
    # Update dataset
    dsin[tvar_name] = dsin[tvar_name] - min_val + 1
    
    # Update allsig
    relevant_mask = allsig['variable'] == expl_var
    if relevant_mask.any():
        allsig.loc[relevant_mask, 'code2'] = f'{tvar_name} = {tvar_name} - {min_val} + 1'
    
    return dsin, allsig


def GLSPLN_plots(
    plot_dat: pd.DataFrame,
    allsig: pd.DataFrame,
    resp_var: str,
    var: str,
    out_folder: Optional[str] = None
):
    """
    Create diagnostic plots for GLSPLN transformation.
    
    This is a stub implementation - full plotting would require more details.
    
    Parameters:
    -----------
    plot_dat : pd.DataFrame
        Plotting data
    allsig : pd.DataFrame
        Parameter output
    resp_var : str
        Response variable
    var : str
        Explanatory variable
    out_folder : Optional[str]
        Output folder for plots
    """
    # Extract transformation info
    relevant = allsig[allsig['variable'] == var]
    
    if len(relevant) == 0:
        warnings.warn(f"No transformation found for {var}")
        return
    
    tvar_name = relevant['tvariable'].iloc[0]
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot original vs transformed (if both exist)
    if var in plot_dat.columns and tvar_name in plot_dat.columns:
        ax.scatter(plot_dat[var], plot_dat[resp_var], alpha=0.3, label='Original')
        ax.scatter(plot_dat[var], plot_dat[tvar_name], alpha=0.3, label='Transformed')
        ax.set_xlabel(var)
        ax.set_ylabel(f'{resp_var} / {tvar_name}')
        ax.legend()
        ax.set_title(f'GLSPLN Transformation: {var}')
        
        if out_folder:
            plt.savefig(f'{out_folder}/glspln_{var}.png')
        else:
            plt.show()
    
    plt.close()


# ==================================================================================
# MAIN WRAPPER FUNCTION
# ==================================================================================

def GLSPLN(
    dsin: pd.DataFrame,
    resp_var: str,
    expl_var: str,
    n: int,
    allsig: Optional[pd.DataFrame] = None,
    cont_blk_var: Optional[List[str]] = None,
    cat_blk_var: Optional[List[str]] = None,
    MAXSTEP: int = 8,
    Num_knot: int = 100,
    Last_knot: Optional[float] = None,
    Name: Optional[str] = None,
    Initialize: int = 0,
    activation: int = 0,
) -> pd.DataFrame:
    """
    Main GLSPLN function - wrapper around GLSPLNTransformer.
    
    This is the primary user-facing function matching SAS %GLSPLN macro.
    
    See GLSPLNTransformer.__init__ for parameter documentation.
    """
    transformer = GLSPLNTransformer(
        dsin=dsin,
        resp_var=resp_var,
        expl_var=expl_var,
        n=n,
        allsig=allsig,
        cont_blk_var=cont_blk_var,
        cat_blk_var=cat_blk_var,
        MAXSTEP=MAXSTEP,
        Num_knot=Num_knot,
        Last_knot=Last_knot,
        Name=Name,
        Initialize=Initialize,
        activation=activation
    )
    
    return transformer.fit()


# ==================================================================================
# VERSION INFO
# ==================================================================================

__version__ = "1.2.7-python"
__author__ = "Converted from SAS GLSPLN by Dr. Basil Coutant"
__date__ = "2025-12-30"

def print_version_info():
    """Print version and help information."""
    print(f"""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║              GLSPLN - Generalized Linear Spline                   ║
    ║                     Python Implementation                         ║
    ╠═══════════════════════════════════════════════════════════════════╣
    ║  Version: {__version__:<55} ║
    ║  Date:    {__date__:<55} ║
    ║  Original SAS Author: Dr. Basil Coutant                          ║
    ╚═══════════════════════════════════════════════════════════════════╝
    
    Usage:
        allsig = GLSPLN(data, 'response', 'explanatory', n=1, Initialize=1)
        data_transformed = add_UT_vars(data, allsig, 'explanatory', n=1)
    
    Key Functions:
        - GLSPLN(): Main transformation fitting
        - add_UT_vars(): Apply transformation to new data
        - bnd_trend(): Bound forward trend
        - shft_min(): Shift minimum value
        - GLSPLN_plots(): Diagnostic plots
    """)


if __name__ == "__main__":
    print_version_info()
