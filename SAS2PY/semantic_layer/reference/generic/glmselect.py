"""
glmselect.py
============
A faithful Python port of the ``PROC GLMSELECT ... SELECTION=STEPWISE`` call
used in ``p2b.sas``:

    proc glmselect data=model namelen=26;
        class node arb_ind_new / param=glm;
        model targt = open_per_hr logit_tsl serv_util rb_pcb serv_per_hr
                      TE_TNX_per_hr*node availability ncf_per_hr open_util
              / selection=stepwise maxstep=20 include=1;
    run;

Design decisions (confirmed with the user)
------------------------------------------
* ``SELECTION=STEPWISE`` with no explicit SELECT/STOP/CHOOSE uses the SAS
  default: **SELECT=SBC, STOP=SBC, CHOOSE=SBC**.  So at every step we add the
  effect (or drop the effect) that yields the largest decrease in SBC and stop
  when no add/drop improves SBC (or ``maxstep`` is reached).
* Selection operates on **whole effects** (a CLASS main effect or a
  continuous*CLASS interaction enters/leaves as a group of columns).
* ``PARAM=GLM`` reference coding: every CLASS level gets a column; columns that
  are linearly dependent given earlier columns are *aliased* (estimate 0, no
  std err), reproducing the SAS sweep.  Rank / SBC use the sequential
  singularity detection from ``glspln_v123_best`` (``_sas_rank``).
* ``INCLUDE=1`` forces the first listed effect (``open_per_hr``) to stay in the
  model at every step.

SBC formula (matches glspln / GLT):  ``n*log(SSE/n) + k*log(n)``  where ``k`` is
the model rank (parameters actually in the fit, intercept included).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, cast

import numpy as np
import pandas as pd
import scipy.linalg
from scipy import stats


_SINGULAR = 1e-7


# ==================================================================================
# Sequential singularity detection (SAS sweep, from glspln_v123_best._sas_rank)
# ==================================================================================
def sas_rank(X: np.ndarray, singular: float = _SINGULAR) -> Tuple[int, List[int]]:
    """Return ``(rank, active_cols)`` using SAS PROC-REG sweep singularity logic.

    Each column is tested against the previously accepted columns; a column
    whose residual sum of squares relative to its own SS falls below
    ``singular`` is treated as aliased and skipped.
    """
    X = np.asarray(X, dtype=float)
    p = X.shape[1]
    active: List[int] = []
    for k in range(p):
        xk = X[:, k]
        orig_ss = float(np.dot(xk, xk))
        if orig_ss <= 0:
            continue
        if active:
            Q = X[:, active]
            coefs, _, _, _ = np.linalg.lstsq(Q, xk, rcond=None)
            resid = xk - Q @ coefs
            resid_ss = float(np.dot(resid, resid))
        else:
            resid_ss = orig_ss
        if resid_ss / orig_ss < singular:
            continue
        active.append(k)
    return len(active), active


# ==================================================================================
# Effect definitions
# ==================================================================================
@dataclass
class Effect:
    """One MODEL-statement effect.

    ``terms`` is an ordered list of ``(var, is_class)`` tuples.  A single
    continuous variable is ``[(var, False)]``; a CLASS main effect is
    ``[(var, True)]``; a continuous*CLASS interaction is
    ``[(cont, False), (cls, True)]``.
    """

    name: str
    terms: List[Tuple[str, bool]]

    @property
    def vars(self) -> List[str]:
        return [v for v, _ in self.terms]

    @property
    def class_vars(self) -> List[str]:
        return [v for v, is_c in self.terms if is_c]


def _fmt_level(level) -> str:
    """Format a CLASS level value the way SAS prints it in parameter names."""
    if isinstance(level, float) and float(level).is_integer():
        return str(int(level))
    return str(level)


def _sas_best(value, width: int = 12) -> str:
    """Emulate SAS ``BESTw.`` (default ``BEST12.``) numeric-to-character format.

    Picks the representation with the most significant digits that still fits
    within the field width, dropping trailing zeros the way SAS does.
    """
    if value is None:
        return ""
    v = float(value)
    if v != v:  # NaN
        return ""
    if v == 0.0:
        return "0"
    for sig in range(width, 0, -1):
        s = f"{v:.{sig}g}"
        if len(s) <= width:
            return s
    return f"{v:.1g}"


# ==================================================================================
# GLMSELECT stepwise model
# ==================================================================================
class GLMSelectStepwise:
    """SBC-based effect-level stepwise regression (PARAM=GLM class coding)."""

    def __init__(
        self,
        response: str,
        effects: List[Effect],
        class_vars: List[str],
        include: int = 0,
        maxstep: Optional[int] = None,
    ):
        self.response = response
        self.effects = effects
        self.class_vars = class_vars
        self.include = int(include)
        self.maxstep = maxstep

        # populated by fit()
        self.class_levels: Dict[str, List] = {}
        self.selected_: List[Effect] = []
        self.beta_: np.ndarray = np.array([])
        self.param_names_: List[str] = []
        self.active_: List[int] = []
        self.selection_summary: pd.DataFrame = pd.DataFrame()
        self.parameter_estimates: pd.DataFrame = pd.DataFrame()
        self.anova: pd.DataFrame = pd.DataFrame()
        self.fit_statistics: pd.DataFrame = pd.DataFrame()
        self._fitted = False

    # ------------------------------------------------------------------ design
    def _all_model_vars(self) -> List[str]:
        seen: List[str] = []
        for eff in self.effects:
            for v in eff.vars:
                if v not in seen:
                    seen.append(v)
        return seen

    def _effect_columns(
        self, effect: Effect, df: pd.DataFrame
    ) -> List[Tuple[str, np.ndarray]]:
        """Build the design columns (name, values) for a single effect."""
        cols: List[Tuple[str, np.ndarray]] = [("", np.ones(len(df)))]
        for var, is_class in effect.terms:
            new_cols: List[Tuple[str, np.ndarray]] = []
            if not is_class:
                x = pd.to_numeric(df[var], errors="coerce").to_numpy(dtype=float)
                for name, vals in cols:
                    nm = var if name == "" else f"{name}*{var}"
                    new_cols.append((nm, vals * x))
            else:
                levels = self.class_levels[var]
                s = df[var]
                for name, vals in cols:
                    for lev in levels:
                        ind = (s == lev).to_numpy(dtype=float)
                        lev_txt = _fmt_level(lev)
                        nm = f"{var} {lev_txt}" if name == "" else f"{name}*{var} {lev_txt}"
                        new_cols.append((nm, vals * ind))
            cols = new_cols
        return cols

    def _build_design(
        self, df: pd.DataFrame, in_effects: List[Effect]
    ) -> Tuple[np.ndarray, List[str], List[int]]:
        """Assemble intercept + selected effect columns.

        Returns ``(X, names, effect_index)`` where ``effect_index[j]`` is the
        index into ``in_effects`` for column ``j`` (or -1 for the intercept).
        """
        names = ["Intercept"]
        mats = [np.ones(len(df))]
        eff_index = [-1]
        for ei, eff in enumerate(in_effects):
            for nm, vals in self._effect_columns(eff, df):
                names.append(nm)
                mats.append(vals)
                eff_index.append(ei)
        X = np.column_stack(mats)
        return X, names, eff_index

    def _effect_levelcols(self, effect: Effect) -> List[Tuple[str, Dict[str, object]]]:
        """Return ``(column_name, {class_var: level})`` for a single effect.

        Mirrors :meth:`_effect_columns` naming exactly (without building the
        numeric values) so callers can recover, per design column, which CLASS
        level it represents.
        """
        cols: List[Tuple[str, Dict[str, object]]] = [("", {})]
        for var, is_class in effect.terms:
            new_cols: List[Tuple[str, Dict[str, object]]] = []
            if not is_class:
                for name, lev in cols:
                    nm = var if name == "" else f"{name}*{var}"
                    new_cols.append((nm, lev))
            else:
                for name, lev in cols:
                    for L in self.class_levels[var]:
                        lev_txt = _fmt_level(L)
                        nm = f"{var} {lev_txt}" if name == "" else f"{name}*{var} {lev_txt}"
                        d = dict(lev)
                        d[var] = L
                        new_cols.append((nm, d))
            cols = new_cols
        return cols

    def _column_meta(
        self, in_effects: List[Effect]
    ) -> List[Tuple[str, Dict[str, object]]]:
        """Per-column ``(effect_name, {class_var: level})`` aligned with ``_build_design``."""
        meta: List[Tuple[str, Dict[str, object]]] = [("Intercept", {})]
        for eff in in_effects:
            for _, lev in self._effect_levelcols(eff):
                meta.append((eff.name, lev))
        return meta

    # --------------------------------------------------------------------- SBC
    @staticmethod
    def _sbc(X: np.ndarray, y: np.ndarray) -> Tuple[float, int, List[int]]:
        """Return ``(SBC, rank, active_cols)`` for design ``X`` and response ``y``."""
        n = X.shape[0]
        k, active = sas_rank(X, singular=_SINGULAR)
        if k == 0:
            return np.inf, 0, []
        Xa = X[:, active]
        XtX = Xa.T @ Xa
        Xty = Xa.T @ y
        beta = scipy.linalg.solve(XtX, Xty, assume_a="sym")
        resid = y - Xa @ beta
        sse = float(resid @ resid)
        sse = max(sse, 1e-300)
        sbc = n * np.log(sse / n) + k * np.log(n)
        return sbc, k, active

    def _sbc_for(self, df: pd.DataFrame, y: np.ndarray, in_effects: List[Effect]) -> float:
        X, _, _ = self._build_design(df, in_effects)
        return self._sbc(X, y)[0]

    # ------------------------------------------------------------------- fit
    def fit(self, dsin: pd.DataFrame) -> "GLMSelectStepwise":
        df = dsin.reset_index(drop=True)

        # listwise deletion on every variable in the MODEL statement (SAS behaviour)
        model_vars = [self.response] + self._all_model_vars()
        work = df.dropna(subset=model_vars).reset_index(drop=True)
        y = pd.to_numeric(work[self.response], errors="coerce").to_numpy(dtype=float)
        n = y.size
        if n == 0:
            raise ValueError("GLMSELECT: no complete observations.")
        self.n_obs_ = n

        # CLASS levels, sorted ascending (numeric where possible)
        for cv in self.class_vars:
            levs = pd.unique(work[cv].dropna())
            try:
                levs = sorted(levs, key=lambda v: float(v))
            except (ValueError, TypeError):
                levs = sorted(levs, key=lambda v: str(v))
            self.class_levels[cv] = list(levs)

        # forced (INCLUDE=) effects: the first `include` listed effects
        forced = self.effects[: self.include]
        in_effects: List[Effect] = list(forced)

        # Accepted model states for the selection summary.  SAS emits the
        # intercept-only model as the first step-0 row, then one step-0 row per
        # forced (INCLUDE=) effect, then one row per stepwise move.
        states: List[Dict[str, object]] = [
            {"step": 0, "label": "Included", "entered": "Intercept",
             "removed": "", "in_effects": []}
        ]
        cumulative: List[Effect] = []
        for feff in forced:
            cumulative = cumulative + [feff]
            states.append(
                {"step": 0, "label": "Included", "entered": feff.name,
                 "removed": "", "in_effects": list(cumulative)}
            )

        cur_sbc = self._sbc_for(work, y, in_effects)

        max_steps = self.maxstep if self.maxstep is not None else len(self.effects) * 2
        step = 0
        while step < max_steps:
            best_sbc = cur_sbc
            best_move: Optional[Tuple[str, Effect]] = None

            # candidate additions
            for eff in self.effects:
                if eff in in_effects:
                    continue
                trial = in_effects + [eff]
                # keep the listed order for a stable design
                trial = [e for e in self.effects if e in trial]
                sbc = self._sbc_for(work, y, trial)
                if sbc < best_sbc - 1e-10:
                    best_sbc = sbc
                    best_move = ("add", eff)

            # candidate removals (never remove a forced effect)
            for eff in list(in_effects):
                if eff in forced:
                    continue
                trial = [e for e in in_effects if e is not eff]
                sbc = self._sbc_for(work, y, trial)
                if sbc < best_sbc - 1e-10:
                    best_sbc = sbc
                    best_move = ("remove", eff)

            if best_move is None:
                break

            action, eff = best_move
            if action == "add":
                in_effects = [e for e in self.effects if (e in in_effects or e is eff)]
                entered, removed = eff.name, ""
            else:
                in_effects = [e for e in in_effects if e is not eff]
                entered, removed = "", eff.name

            cur_sbc = best_sbc
            step += 1
            label = f"{step}+{entered}" if entered else f"{step}-{removed}"
            states.append(
                {"step": step, "label": label, "entered": entered,
                 "removed": removed, "in_effects": list(in_effects)}
            )

        self.selected_ = in_effects
        self.selection_summary = self._build_selection_summary(work, y, states)
        self._finalize(work, y)
        self._fitted = True
        return self

    def _sse_and_k(self, work: pd.DataFrame, y: np.ndarray,
                   in_effects: List[Effect]) -> Tuple[float, int]:
        """Return ``(SSE, rank)`` for the model spanned by ``in_effects``."""
        X, _, _ = self._build_design(work, in_effects)
        k, active = sas_rank(X, singular=_SINGULAR)
        Xa = X[:, active]
        XtX = Xa.T @ Xa
        Xty = Xa.T @ y
        beta = scipy.linalg.solve(XtX, Xty, assume_a="sym")
        resid = y - Xa @ beta
        return float(resid @ resid), k

    def _build_selection_summary(
        self, work: pd.DataFrame, y: np.ndarray, states: List[Dict[str, object]]
    ) -> pd.DataFrame:
        """Assemble the SAS-style ``Selection`` summary table.

        Columns match the PROC GLMSELECT ODS ``SelectionSummary`` layout:
        ``Step, StepLabel, EffectEntered, EffectRemoved, nEffectsIn, nParmsIn,
        RSquare, AdjRSq, OptAdjRSq, AIC, OptAIC, AICC, OptAICC, SBC, OptSBC,
        FValue, ProbF, ASE, Control``.
        """
        n = y.size
        ybar = float(np.mean(y))
        sst = float(np.sum((y - ybar) ** 2))

        rows: List[Dict[str, object]] = []
        prev_sse: Optional[float] = None
        prev_k: Optional[int] = None
        for st in states:
            in_effects = cast(List[Effect], st["in_effects"])
            sse, k = self._sse_and_k(work, y, in_effects)
            dfe = n - k
            rsq = 1.0 - sse / sst if sst > 0 else np.nan
            adj = (1.0 - (sse / dfe) / (sst / (n - 1))
                   if (dfe > 0 and sst > 0) else np.nan)
            mse_aic = sse / n
            aic = n * np.log(mse_aic) + 2 * k + n + 2 if sse > 0 else np.nan
            aicc = (n * np.log(mse_aic) + n * (n + k) / (n - k - 2)
                    if (sse > 0 and (n - k - 2) > 0) else np.nan)
            sbc = n * np.log(mse_aic) + k * np.log(n) if sse > 0 else np.nan
            ase = sse / n

            # partial F test for the effect entered/removed at this step
            if prev_sse is None or prev_k is None or k == prev_k:
                fval, probf = 0.0, 1.0
            else:
                df1 = abs(k - prev_k)
                num = (prev_sse - sse) / (k - prev_k)
                den = sse / dfe if dfe > 0 else np.nan
                fval = num / den if (den and den == den) else np.nan
                probf = (float(stats.f.sf(fval, df1, dfe))
                         if (fval == fval and dfe > 0) else np.nan)

            rows.append(
                {
                    "Step": st["step"],
                    "StepLabel": st["label"],
                    "EffectEntered": st["entered"],
                    "EffectRemoved": st["removed"],
                    "nEffectsIn": len(in_effects) + 1,  # + intercept
                    "nParmsIn": k,
                    "RSquare": rsq,
                    "AdjRSq": adj,
                    "OptAdjRSq": 0,
                    "AIC": aic,
                    "OptAIC": 0,
                    "AICC": aicc,
                    "OptAICC": 0,
                    "SBC": sbc,
                    "OptSBC": 0,
                    "FValue": fval,
                    "ProbF": probf,
                    "ASE": ase,
                    "Control": "",
                }
            )
            prev_sse, prev_k = sse, k

        summary = pd.DataFrame(rows)
        if not summary.empty:
            # flag the optimal step for each criterion (max AdjRSq, min others)
            summary.loc[summary["AdjRSq"].idxmax(), "OptAdjRSq"] = 1
            summary.loc[summary["AIC"].idxmin(), "OptAIC"] = 1
            summary.loc[summary["AICC"].idxmin(), "OptAICC"] = 1
            summary.loc[summary["SBC"].idxmin(), "OptSBC"] = 1
        return summary

    def _design_and_y(self, work, y, in_effects):
        X, _, _ = self._build_design(work, in_effects)
        return X, y

    # -------------------------------------------------------------- finalize
    def _finalize(self, work: pd.DataFrame, y: np.ndarray) -> None:
        X, names, eff_index = self._build_design(work, self.selected_)
        n = X.shape[0]
        k, active = sas_rank(X, singular=_SINGULAR)
        Xa = X[:, active]
        XtX = Xa.T @ Xa
        XtX_inv = np.linalg.inv(XtX)
        Xty = Xa.T @ y
        beta_a = XtX_inv @ Xty
        resid = y - Xa @ beta_a
        sse = float(resid @ resid)
        dfe = n - k
        mse = sse / dfe if dfe > 0 else np.nan
        rmse = np.sqrt(mse) if mse == mse else np.nan

        # full-length beta with 0 for aliased columns
        beta_full = np.zeros(len(names))
        for pos, col in enumerate(active):
            beta_full[col] = beta_a[pos]
        self.beta_ = beta_full
        self.param_names_ = names
        self.active_ = active
        self._eff_index = eff_index

        # standard errors (only for active columns)
        se_full = np.full(len(names), np.nan)
        diag = np.diag(XtX_inv)
        for pos, col in enumerate(active):
            se_full[col] = np.sqrt(mse * diag[pos]) if mse == mse else np.nan

        # ---- ParameterEstimates ----
        # meta[j] = (effect_name, {class_var: level}) aligned with `names`
        meta = self._column_meta(self.selected_)
        active_set = set(active)

        # forced (INCLUDE=) effect names and the CLASS variables that actually
        # appear in the final model - SAS only shows a level column per CLASS
        # variable that is present in a selected effect.
        forced_names = {e.name for e in self.effects[: self.include]}
        used_class_vars = [
            cv for cv in self.class_vars
            if any(cv in eff.class_vars for eff in self.selected_)
        ]

        # standardized estimates: beta_j * sd(X_j) / sd(y)  (sample sd, ddof=1)
        sd_y = float(np.std(y, ddof=1))
        sd_x = X.std(axis=0, ddof=1)

        rows = []
        for j, nm in enumerate(names):
            est = beta_full[j]
            if j in active_set:
                se = se_full[j]
                tval = est / se if se and se == se else np.nan
                pval = float(2 * stats.t.sf(abs(tval), dfe)) if (dfe > 0 and se == se) else np.nan
                dfp = 1
            else:
                se, tval, pval, dfp = np.nan, np.nan, np.nan, 0  # aliased / biased
            eff_name, lev_map = meta[j] if j < len(meta) else (nm, {})
            is_intercept = (nm == "Intercept")
            std_est = 0.0 if is_intercept else (
                est * sd_x[j] / sd_y if sd_y else np.nan
            )
            forced_in = 0 if is_intercept else (1 if eff_name in forced_names else 0)

            row: Dict[str, object] = {"Effect": eff_name}
            # one level column per CLASS variable used in the model; missing
            # (NaN) when the row does not involve that variable - SAS stores
            # these as numeric columns with missing values, not strings.
            for cv in used_class_vars:
                lev = lev_map.get(cv, None)
                row[cv] = lev if lev is not None else np.nan
            row["ForcedIn"] = forced_in
            row["Parameter"] = nm
            row["DF"] = dfp
            row["Estimate"] = est
            row["StandardizedEst"] = std_est
            row["StdErr"] = se
            row["tValue"] = tval
            row["Probt"] = pval
            rows.append(row)
        self.parameter_estimates = pd.DataFrame(rows)
        # Keep numeric CLASS-level columns numeric (SAS represents them as
        # numbers, e.g. node = 1, not "1").  Only convert columns whose levels
        # are all numeric so character CLASS levels are left untouched.
        for cv in used_class_vars:
            col = self.parameter_estimates[cv]
            present = col.dropna()
            coerced = pd.to_numeric(present, errors="coerce")
            if len(present) and coerced.notna().all():
                num = pd.to_numeric(col, errors="coerce")
                non_null = num.dropna()
                if (non_null == non_null.round()).all():
                    self.parameter_estimates[cv] = num.astype("Int64")
                else:
                    self.parameter_estimates[cv] = num

        # ---- ANOVA ----
        ybar = float(np.mean(y))
        sst = float(np.sum((y - ybar) ** 2))
        ssm = sst - sse
        dfm = k - 1
        msm = ssm / dfm if dfm > 0 else np.nan
        fval = msm / mse if (mse and mse == mse and dfm > 0) else np.nan
        fp = float(stats.f.sf(fval, dfm, dfe)) if (fval == fval and dfe > 0) else np.nan
        self.anova = pd.DataFrame(
            {
                "Source": ["Model", "Error", "Corrected Total"],
                "DF": [dfm, dfe, n - 1],
                "SumOfSquares": [ssm, sse, sst],
                "MeanSquare": [msm, mse, np.nan],
                "FValue": [fval, np.nan, np.nan],
                "ProbF": [fp, np.nan, np.nan],
            }
        )

        # ---- FitStatistics ----
        # AIC / AICC / SBC follow the SAS (PROC GLMSELECT) definitions, matching
        # the tested glspln_v123 implementation:
        #   mse_aic = SSE / n
        #   AIC  = n*log(mse_aic) + 2*k + n + 2
        #   AICC = n*log(mse_aic) + n*(n + k)/(n - k - 2)
        #   SBC  = n*log(mse_aic) + k*log(n)
        rsq = ssm / sst if sst > 0 else np.nan
        adj_rsq = 1 - (1 - rsq) * (n - 1) / dfe if dfe > 0 else np.nan
        mse_aic = sse / n if sse > 0 else np.nan
        aic = n * np.log(mse_aic) + 2 * k + n + 2 if sse > 0 else np.nan
        aicc = (
            n * np.log(mse_aic) + n * (n + k) / (n - k - 2)
            if (sse > 0 and (n - k - 2) > 0) else np.nan
        )
        sbc = n * np.log(mse_aic) + k * np.log(n) if sse > 0 else np.nan

        # SAS emits FitStatistics as one row per statistic with a character
        # (cValue1) and numeric (nValue1) copy of the value, matching the ODS
        # OUTPUT layout: Label1, cValue1, nValue1.
        labels = ["Root MSE", "Dependent Mean", "R-Square", "Adj R-Sq",
                  "AIC", "AICC", "SBC"]
        values = [rmse, ybar, rsq, adj_rsq, aic, aicc, sbc]
        cvalues = [_sas_best(v) for v in values]
        self.fit_statistics = pd.DataFrame(
            {
                "Label1": labels,
                "cValue1": cvalues,
                "nValue1": values,
            }
        )

    # ------------------------------------------------------------- predict
    def predict(self, dsin: pd.DataFrame) -> np.ndarray:
        """Linear prediction (``guide_est_t``) for ``dsin`` using the final model.

        This is the mathematical equivalent of applying the score code produced
        by ``%glmselect_score_code`` to the data.
        """
        self._check_fitted()
        X, names, _ = self._build_design(dsin.reset_index(drop=True), self.selected_)
        # names should line up with training param order
        return X @ self.beta_

    def _check_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("Call fit() before predict().")
