#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
import pandas as pd
import numpy as np
import statsmodels.api as sm
import re
from typing import Optional, List, Dict, Union, Tuple
import warnings
import datetime as _datetime_module
from datetime import datetime
from sklearn.linear_model import LinearRegression
from sklearn.feature_selection import SequentialFeatureSelector
from statsmodels.formula.api import ols
import sys, traceback
import statsmodels.api as sm
import scipy
warnings.filterwarnings('ignore')

# modified0617
from decimal import Decimal, ROUND_HALF_UP

if 'RBNN_meta' not in globals():
    RBNN_meta = pd.DataFrame()

# ==============================================================
# META DATA AND VERSION INFO
# ==============================================================

RBNN_VERSION = '1.0.6'
RBNN_last_update = '2/8/21'

# ==============================================================
# RBNN HELP AND ABOUT INFO
# ==============================================================

RBNN_help = pd.DataFrame({
    "Help": [
        "************************************************************",
        "*RBNN(dsin, resp_var, max_nodes=5, max_layers=5, Cat_expl_vbar =,)",
        "    Cont_expl_var =, interact_level = 1, max_dir_reuse = 8, cont_blk_var =,",
        "    cat_blk_var =, sbout = ttemp_out, code_out = All_code, Activateion=0,",
        "    Suppress_meta=0)",
        "XAlteryx_code_out(All_code_in, Alteryx_out, code_index)",
        "******************** REQUIRED INPUT ************************",
        "dsin = the input dataset",
        "resp_var = the target or response variable."
        "******************** OPTIONAL INPUT ********************",
        "Cont_blk_var = continuous variables to block on. (feature not available)",
        "Cat_blk_var = categorical variables to block on. (feature not available)",
        "max_dir_reuse = maximum times to reuse a direction.",
        "Activation = 1 - min(0,x), 2 - max(0,x), 0 both types.",
        "Notes: Review log for errors. Odd things happen!"
    ]
})

def RBNNhelp(x):
    if x == 1:
        return 11
    return "max"
print(RBNN_help.head(RBNNhelp(1)).to_string(index=False))
print("*" * 79);print("Versions:");print("*" * 79)

About_RBNN = pd.DataFrame({
    "pad": ["   ", "    ", "    ", "    "],
    "description": ["RBNN", "Version", "Last update", "Author"],
    "value": [
        "The RBNN macro package",
        RBNN_VERSION,
        RBNN_last_update,
        "Dr. Basil Coutant(Basil.W.Coutant@Chase.com)"
    ]
})
print(About_RBNN.to_string(index=False))
if 'About_RBNN' in locals():del About_RBNN

# ========================
# RBNN_meta Initialization
# ========================

# Create RBNN_meta DataFrame
RBNN_META = pd.DataFrame({
    'Macro_var': ['version', 'date', 'dsin', 'resp_var', 'max_nodes', 'max_layers',
        'Cont_expl_var', 'Cat_expl_var','Code_out', 'Cont_blk_var', 'Cat_blk_var',
        'max_dir_reuse', 'Activation'],
    'Macro_var_desc': ['RBNN Version', 'Run Date', 'Input dataset', 'Response variable',
        'Maximum nodes per layer', 'Maximum # of layers',
        'Cont. Explanatory variables', 'Cat. Explanatory variables',
        'output code','Cont. block vars.','Cat. block vars.',
        'Max # reuses a dir','Act. fn choice'],'Value':['']*13,
        'pad':[' ']*13
})


# Set Column labels
RBNN_META.attrs['labels']={
    'Macro_var_desc':'Macro parameter',
    'Value':'Parameter value'
}

#===Global Initialization===
code_out=pd.DataFrame(columns=['Layer','Node','Hyperplane_num','New_var','code','DND_NB'])
code_stack = pd.DataFrame(); Fit_sum = pd.DataFrame(); Fit_tracker = pd.DataFrame()
Plot_stack = pd.DataFrame(); tracker = pd.DataFrame(); all_fit = pd.DataFrame()
plot_out = pd.DataFrame(); dnd_monthly_tot = pd.DataFrame(); stat = pd.DataFrame()
netsize = pd.DataFrame(); Fit_out = pd.DataFrame(); All_code = pd.DataFrame()


# ===============================================
# Main RBNN Function
# ===============================================

def RBNN(
        dsin:pd.DataFrame,
        resp_var:str,
        max_nodes=5, # Manually setting Nodes
        max_layers=10, # Manually setting Layers
        cont_expl_var:Optional[List[str]]=None,
        cat_expl_var:Optional[List[str]]=None,
        interact_level:int=1,
        max_dir_reuse:int=10,
        cont_blk_var:Optional[List[str]]=None,
        cat_blk_var:Optional[List[str]]=None,
        dsout:Optional[pd.DataFrame]=None,
        code_out :Optional[pd.DataFrame]=None,
        activation:int=0,
        suppress_meta:int=0):
    """
    Fit a Regression based Neural Network (RBNN) model and generates scoring code.

    This function trains a neural network on the input data and produces both model outputs
    and code for scoring new data
    """

    # Commented out
    # global RBNN_meta, rbnn_ttemp , rbnn_data, var_list
    # global code_stack, all_fit, primary_tracker, join_stack, Fit_sum, All_code ,scored_data ,RBNN_scorecode

    cont_expl_var=cont_expl_var or []
    cat_expl_var=cat_expl_var or []
    cat_blk_var=cat_blk_var or []
    cont_blk_var=cont_blk_var or []

    # Update RBNN_meta with parameter value
    global RBNN_META

    param_values = {
        'version': RBNN_VERSION,
        'date': _datetime_module.datetime.now().strftime("%d%b%Y").upper(),
        'dsin': 'DataFrame',
        'resp_var': resp_var,
        'max_nodes': str(max_nodes),
        'max_layers': str(max_layers),
        'Cont_expl_var' : ', '.join(cont_expl_var) if cont_expl_var else '',
        'Cat_expl_var' : ', '.join(cat_expl_var) if cat_expl_var else '',
        'Code_out' : 'code_out',
        'Cont_blk_var' : ', '.join(cont_blk_var) if cont_blk_var else '',
        'Cat_blk_var' : ', '.join(cat_blk_var) if cat_blk_var else '',
        'max_dir_reuse' : str(max_dir_reuse),
        'Activation' : str(activation)
    }

    for macro_var,full_value in param_values.items():
        value_str=str(full_value) if full_value is not None else ''
        RBNN_META.loc[RBNN_META["Macro_var"]==macro_var,"Value"]=value_str[:50].strip()

    if suppress_meta == 1:
        print("RBNN model information.See RBNN_meta.")
        print(RBNN_META[["pad","Macro_var_desc","Value"]].to_string(index=False))
        print()


    rbnn_ttemp = dsin.copy()

    # get all variable columns to check for missingness
    all_vars=[resp_var]+cont_expl_var+cat_expl_var+cont_blk_var+cat_blk_var
    all_vars=[v for v in all_vars if v and v in rbnn_ttemp.columns]

    # Filter out rows with missing values in any of the relevant columns
    if all_vars:
        rbnn_data=rbnn_ttemp.dropna(subset=all_vars).copy()
    else:
        rbnn_data=rbnn_ttemp.copy()

    print("output [rbnn_data]")
    n_obs=len(rbnn_data)

    if n_obs == 0:
        warnings.warn("No observation sfter missing values, Returning empty results")
        all_fit = pd.DataFrame()
        return rbnn_data, dsout, code_out, all_fit

    # Initialize output datasets if not provided
    if dsout is None:
        dsout = rbnn_data.copy()

    if code_out is None:
        # Initialize code_out DataFrame structure
        code_out = pd.DataFrame({
            'Layer': [0],
            'Node': [0],
            'Hyperplane_num': [0],
            'New_var': ['0' * 105],
            'Knot': [0.0],
            'Effect': ['0' * 105],
            'Parameter': ['0' * 105],
            'DF': [0],
            'Estimate': [0.0],
            'StandardizedEst': [0.0],
            'StdErr': [0.0],
            'tValue': [0.0],
            'Probt': [0.0],
            'code': [''],
            'index': [0]

        })

    # initialize all_fit Dataframe

    all_fit=pd.DataFrame({
        '_NAME_':['nValue1'],
        'Layer':[0],
        'Node':[0],
        'N':[0],
        'Intercept':[0.0],
        'Root MSE':[0.0],
        'Dependent Mean':[0.0],
        'R-Square':[0.0],
        'Adj R-Sq':[0.0],
        'AIC':[0.0],
        'AICC':[0.0],
        'SBC':[0.0]
        })

    if n_obs==0:
        warnings.warn("No observations after removing missing values. Returning empty results.")
        return rbnn_data, dsout,code_out,all_fit

    # Loop through layers and nodes, calling RBNNN for each

    print("Layer 1 Processing")

    # layer 1 loop
    for layer in range(1, 2):
        print(f" Layer {layer} Processing:")
        for node in range(1, max_nodes + 1):
            print(f" Layer {layer} Node{node} ")
            dsout, code_out, all_fit = RBNNN(
                dsin=rbnn_data,
                resp_var=resp_var,
                layer=layer,
                node=node,
                cont_expl_var=cont_expl_var.copy(),
                cat_expl_var=cat_expl_var.copy(),
                interact_level=interact_level,
                max_dir_reuse=max_dir_reuse,
                cont_blk_var=cont_blk_var.copy(),
                cat_blk_var=cat_blk_var.copy(),
                dsout=dsout,
                code_out=code_out,
                all_fit=all_fit,
                activation=activation)

    # Layer 2 to max_layers
    
    for layer in range(2,max_layers+1):
        print(f" Layer {layer} Processing:")
        for node in range(1,max_nodes+1):
            print(f" Layer {layer} Node{node} ")
            dsout,code_out,all_fit=RBNNN(
                dsin=rbnn_data,
                resp_var=resp_var,
                layer=layer,
                node=node,
                cont_expl_var=cont_expl_var.copy(),
                cat_expl_var=cat_expl_var.copy(),
                interact_level=interact_level,
                max_dir_reuse=max_dir_reuse,
                cont_blk_var=cont_blk_var.copy(),
                cat_blk_var=cat_blk_var.copy(),
                dsout=dsout,
                code_out=code_out,
                all_fit=all_fit,
                activation=activation)

    # Generate final score code
    code_out,dsout=RBNN_scorecode(
        dsin=rbnn_data,
        resp_var=resp_var,
        cont_blk_var=cont_blk_var,
        cat_blk_var=cat_blk_var,
        code_out=code_out,
        dsout=dsout)

    print("RBNN Complete ")
    print("RBNN data output")
    print(f"\nrbnn_data: {rbnn_data.head(5)}")
    # print(f"\ndsout: {dsout.head(5)}")
    # print(f"\ncode_out: {code_out.head(5)}")

    return rbnn_data, dsout, code_out,all_fit

def get_dummies_drop_last(
    df: pd.DataFrame,
    columns: List[str]=None
):
    df=df.copy()
    dfs_arr=[]
    cat_var_mapping={}
    cat_var_dropped_mapping={}
    if columns is None:
        columns=df.columns.tolist()

    for col in columns:
        if col not in df.columns:
            continue
        s=df[col]
        unique_vals=s.unique()
        unique_sorted=sorted(unique_vals)
        if np.issubdtype(s.dtype,np.number):
            drop_cat=max(unique_sorted)
        else:
            drop_cat=unique_sorted[-1]
        dummies=pd.get_dummies(s,prefix=col,prefix_sep="_").astype(float)
        drop_col_name=f"{col}_{drop_cat}"
        if drop_col_name in dummies.columns:
            dummies=dummies.drop(columns=[drop_col_name])
            dfs_arr.append(dummies)
            cat_var_mapping[col]=list(dummies.columns)
            cat_var_dropped_mapping[col]=drop_col_name
    if len(dfs_arr)>0:
        df_cat=pd.concat(dfs_arr,axis=1)
        return df_cat, cat_var_mapping, cat_var_dropped_mapping
    else:
        return None, {}, {}
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
def calc_sbc_vals(X,y,flag_class_var=False):
    if X.empty:
        return np.inf
    if X.shape[0] >= X.shape[1]:
        try:
            X2=sm.add_constant(X.copy(),has_constant='add')
            if flag_class_var:
                # X_pinv=scipy.linalg.pinv(X2,rtol=1e-5) ## modified0629
                X_pinv=scipy.linalg.pinv(X2,atol=1e-5,rtol=1e-5) ## modified0629
            else:
                X_pinv=scipy.linalg.pinv(X2,rtol=1e-7)
            beta = X_pinv @ y.values
            resid=y.values-X2 @ beta

            sse=float(resid @ resid)
            n_samples=X.shape[0]
            k=X.shape[1]
            
            ###modified0623
            sse = np.round(sse,6)

            sbc=n_samples*np.log(sse/(n_samples)) + (k+1) * np.log(n_samples)
            
            return sbc
        except:
            return np.inf
    else:
        return np.inf

def detect_redundant_new_dummies(df, base_vars,new_var,constant=1):
    from itertools import combinations
    X_base =df[base_vars]
    X_new=df[new_var]
    redundant_new_cols=set()

    target =np.ones(len(df)) * constant
    X_all=pd.concat([X_base,X_new],axis=1)

    for r in range(1, len(X_new.columns)+1):
        for combo_new in combinations(X_new.columns,r):
            new_sum=X_new[list(combo_new)].sum(axis=1).values
            residual=target-new_sum

            for col in X_base.columns:
                if np.array_equal(residual,X_base[col].values):
                    redundant_new_cols.update(combo_new)

            base_sum=X_base.sum(axis=1).values
            if np.array_equal(residual, base_sum):
                redundant_new_cols.update(combo_new)

    return redundant_new_cols


def stepwise_sbc(X,y, class_vars_mapping={}, verbose=True):

    available=[]
    class_vars=list(class_vars_mapping.keys())
    class_vars_encoded=[]
    for c in class_vars_mapping:
        class_vars_encoded=class_vars_encoded + class_vars_mapping[c]

    available =[c for c in X.columns if (c not in class_vars_encoded)] + class_vars
    selected=[]
    best_score=np.inf
    redundant=[]
    while True:
        changed=False
        best_eff=None
        best_redundant=[]

        selected_extend=[]
        for c in selected:
            if c in class_vars:
                selected_extend+=class_vars_mapping[c]
            else:
                selected_extend.append(c)
        selected_extend=[c for c in selected_extend if c not in redundant]

        for eff in available:
            if eff in selected:
                continue
            try:
                cols_0=selected_extend.copy()

                if eff in class_vars:
                    if len(selected_extend)>0:

                        cols_redundant=detect_redundant_new_dummies(X,selected_extend,class_vars_mapping[eff])
                        cols_extend=class_vars_mapping[eff]
                        cols_extend=[c for c in cols_extend if c not in cols_redundant]

                    else:
                        cols_redundant=[]
                        cols_extend=class_vars_mapping[eff]

                    cols_1=selected_extend + cols_extend

                else:
                    cols_1=selected_extend + [eff]
                    cols_redundant=[]

                bic0=calc_sbc_vals(X[cols_0],y)
                bic1=calc_sbc_vals(X[cols_1],y)

                if bic1+1e-11 < bic0 and bic1+1e-11 < best_score:
                    best_eff=eff
                    best_score=bic1
                    best_redundant=list(cols_redundant)
            except Exception as e:
                print(e)
                continue
        if best_eff is not None:
            selected.append(best_eff)
            redundant=redundant+best_redundant
            changed=True

        selected_extend=[]
        for c in selected:
            if c in class_vars:
                selected_extend+=class_vars_mapping[c]
            else:
                selected_extend.append(c)
        selected_extend=[c for c in selected_extend if c not in redundant]

        for eff in selected[:]:
            try:
                cols_0=selected_extend
                if eff in class_vars:
                    cols_1=[c for c in selected_extend if c not in class_vars_mapping[eff]]
                else:
                    cols_1 = [c for c in selected_extend if c not in [eff]]

                bic0=calc_sbc_vals(X[cols_0],y)
                bic1=calc_sbc_vals(X[cols_1],y)

                if bic1<bic0 and bic1<best_score:
                    best_score=bic1
                    selected.remove(eff)
                    changed=True
            except Exception as e:
                print(eff,e)
                continue
        if not changed:
            break

    final_selected=[]
    for c in selected:
        if c in class_vars:
            final_selected+=class_vars_mapping[c]
            final_selected=[c for c in final_selected if c not in redundant]
        else:
            final_selected.append(c)

    return final_selected, selected


def check_high_correlation(df, var_list, new_var):
    if new_var not in df.columns:
        return False
    valid_cols=[col for col in var_list if col in df.columns]
    if not valid_cols:
        return False
    target_cols=valid_cols + [new_var]
    corr_matrix=df[target_cols].corr()
    corr_series=corr_matrix[new_var].drop(new_var)
    abs_corr=corr_series.abs()
    max_corr=abs_corr.max()
    is_high_corr=(max_corr + 1e-6 >=1)
    return is_high_corr

###modified0623
def sas_rank_check(X, singular=1e-8):
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

### modified0623
def get_active_cols(X,cols):
    X2 = sm.add_constant(X[cols], has_constant='add')
    _, active_cols_idx = sas_rank_check(X2)
    active_cols = X2.columns[active_cols_idx]
    active_cols = [c for c in active_cols if c not in["const"] ]
    return active_cols
    
def stepwise_sbc_maxstep(X,y, class_vars_mapping={}, maxstep=100,included_vars=[],verbose=True):
    if len(included_vars)>0:
        bic_0=calc_sbc_vals(X[included_vars],y)
        best_score=bic_0
    else:
        best_score=np.inf
    available=[]
    class_vars=list(class_vars_mapping.keys())
    class_vars_encoded=[]

    for c in class_vars_mapping:
        class_vars_encoded=class_vars_encoded + class_vars_mapping[c]

    available=[c for c in X.columns if (c not in class_vars_encoded) and (c not in included_vars)] + class_vars
    selected =list(included_vars).copy()

    steps_used=0
    changed=True

    while changed and steps_used < maxstep:
        changed=False
        flag_forward=False
        flag_backward=False

        add_best=None
        add_best_score=best_score

        selected_extend=[]
        for c in selected:
            if c in class_vars:
                selected_extend+=class_vars_mapping[c]
            else:
                selected_extend.append(c)

        for eff in available:
            # modified0617
            flag_class_var=False

            if eff in selected:
                continue
            try:
                if eff in class_vars:
                    cols_1=selected_extend + class_vars_mapping[eff]
                    # modified0617
                    flag_class_var=True
                else:
                    cols_1=selected_extend + [eff]
                    # modified0617
                    # flag_class_var=True
                    # modified0629
                    flag_class_var=False
                
                ### modified0623
                cols_1 = get_active_cols(X,cols_1)
                
                # modified0617
                bic1=calc_sbc_vals(X[cols_1],y,flag_class_var)
                if bic1 < add_best_score:
                    add_best_score=bic1
                    add_best=eff
            except Exception as e:
                print(eff,e)
                continue

        if add_best is not None:
            selected.append(add_best)
            best_score=add_best_score
            changed=True
            flag_forward=True
            # print("forward added",add_best,best_score)
        if flag_forward:
            steps_used+=1

        if steps_used >=maxstep:
            break
        
        ### modified0629
        # removable=[var for var in selected if var not in list(included_vars)]
        # remove_best=None
        # remove_best_score=best_score
        # selected_extend=[]

        # selected_extend=selected_extend+list(included_vars)

        # for c in removable:
        #     if c in class_vars:
        #         selected_extend+=class_vars_mapping[c]
        #     else:
        #         selected_extend.append(c)
                
        
        # modified0525
        # for eff in selected[:]:
        #     try:
        #         if eff in class_vars:
        #             cols_1=[c for c in selected_extend if c not in class_vars_mapping[eff]]
        #         else:
        #             cols_1= [c for c in selected_extend if c not in [eff]]
                
        #         # ### modified0623
        #         cols_1 = get_active_cols(X,cols_1)
                
        #         bic1=calc_sbc_vals(X[cols_1],y)
                
        #         ### modified0623   1. from "<" to "<="  2. extra rule
        #         # if bic1< remove_best_score:
        #         if bic1<= remove_best_score and bic1>-np.inf:
        #             remove_best_score=bic1
        #             remove_best=eff
        #     except Exception as e:
        #         print(f" ERROR in stepwise_sbc_maxstep (backward) for feature '{eff}':")
        #         print(eff,e)
        #         continue

        # if remove_best is not None:
        #     selected.remove(remove_best)
        #     best_score=remove_best_score
        #     changed=True
        #     flag_backward=True
        
        #     print("backward removed",remove_best,best_score)
        # if flag_backward:
        #     steps_used+=1
        
        ### modified0629
        while True:
            
            removable=[var for var in selected if var not in list(included_vars)]
            remove_best=None
            remove_best_score=best_score
            selected_extend=[]

            selected_extend=selected_extend+list(included_vars)

            for c in removable:
                if c in class_vars:
                    selected_extend+=class_vars_mapping[c]
                else:
                    selected_extend.append(c)
                    
            for eff in selected[:]:
                try:
                    if eff in class_vars:
                        cols_1 = [c for c in selected_extend if c not in class_vars_mapping[eff]]
                    else:
                        cols_1 = [c for c in selected_extend if c not in [eff]]
                    cols_1 = get_active_cols(X,cols_1)
                    bic1=calc_sbc_vals(X[cols_1],y)
                    if bic1<= remove_best_score and bic1>-np.inf:
                        remove_best_score=bic1
                        remove_best=eff
                except Exception as e: 
                     print(f" ERROR in stepwise_sbc_maxstep (backward) for feature '{eff}':")
                     print(eff,e)
                     continue
            if remove_best is not None:
                selected.remove(remove_best)
                best_score=remove_best_score
                changed=True
                flag_backward=True
                steps_used+=1
                # print("backward removed",remove_best,best_score)
                continue
            
                
                
            break            
        ####################################################################
            
        if steps_used>=maxstep:
            break

        if not changed:
            break

    final_selected=[]
    for c in selected:
        if c in class_vars:
            final_selected+=class_vars_mapping[c]
        else:
            final_selected.append(c)
    
    ### modified0623
    final_selected = get_active_cols(X,final_selected)
    
    return final_selected,selected

def sas_pctldef5(values: np.ndarray, pct_points: np.ndarray)-> np.ndarray:
    x=np.asarray(values,dtype=float)
    x=x[~np.isnan(x)]

    if x.size == 0:
        return np.full(len(pct_points),np.nan,dtype=float)

    x.sort()
    n=x.size

    out=np.empty(len(pct_points), dtype=float)
    for i,t in enumerate(pct_points):
        p=float(t) /100.0
        np_val=n*p
        j=int(np.floor(np_val))
        g=np_val-j

        def x_sas(k:int) ->float:
            if k<=1:
                return x[0]
            if k>=n:
                return x[n-1]
            return x[k-1]
        if np.isclose(g,0.0):
            out[i]=0.5 * (x_sas(j) + x_sas(j+1))
        else:
            out[i]=x_sas(j+1)
    return out




def format_figures(number,sig_figs=11):
    d=Decimal(str(number))
    if d==0:
        return 0
    magnitude = d.adjusted()+1
    decimal_places=sig_figs-magnitude
    result=d.quantize(Decimal(10) ** -decimal_places,rounding=ROUND_HALF_UP)
    return float(result)

# RBNNN - Build a single neural network node
def RBNNN(
        dsin:pd.DataFrame,
        resp_var:str,
        layer:int,
        node:int,cont_expl_var:List[str],
        cat_expl_var:List[str],
        interact_level:int,
        max_dir_reuse:int,
        cont_blk_var:List[str],
        cat_blk_var:List[str],
        dsout:pd.DataFrame,
        code_out :pd.DataFrame,
        all_fit:pd.DataFrame,
        activation:int):
    """
    Implementation of the RBNN model.

    This function may provide additional features or experimental logic for neural network
    training and scoring.

    """

    cont_expl_var=list(cont_expl_var) if cont_expl_var else []
    cat_expl_var=list(cat_expl_var) if cat_expl_var else []
    cat_blk_var=list(cat_blk_var) if cat_blk_var else []
    cont_blk_var=list(cont_blk_var) if cont_blk_var else []

    # ==============================================================================
    # INITIALIZATION: If layer =1 and node=1 (first call)
    # ==============================================================================

    print(f" RBNNN L{layer} N{node} Start")

    if (layer + node) == 2:
        # Initialize code_out DataFrame
        code_out= pd.DataFrame({
            'Layer':[0],
            'Node' : [0],
            'Hyperplane_num' : [0],
            'New_var' : ['0'*73],
            'Knot' : [0.0],
            'Effect' : ['0'*73],
            'Parameter' : ['0'*73],
            'DF' : [0],
            'Estimate' : [0.0] ,
            'StandardizedEst' : [0.0],
            'StdErr' : [0.0],
            'tValue': [0.0],
            'Probt': [0.0],
            'index':[0],
            'code':['']
        })

        # Intilaize all_fit DataFrame
        all_fit=pd.DataFrame({
            '_NAME_':['nValue1'],
            'Layer':[0],
            'Node':[0],
            'N':[0],
            'Intercept':[0.0],
            'Root MSE':[0.0],
            'Dependent Mean':[0.0],
            'R-Square':[0.0],
            'Adj R-Sq':[0.0],
            'AIC':[0.0],
            'AICC':[0.0],
            'SBC':[0.0]
        })

        dsout=dsin.copy()

    # ==============================================================================
    # ELSE: Handle exit conditions and gather previous node variables
    # ==============================================================================

    else:
        # Get exit conditions from code_out (wherelayer != 9999)
        vars_df=code_out[code_out['Layer'] !=9999].copy()

        if len(vars_df)>0:
            # Get last row (grouped by layer, node - last.layer and last.node )
            vars_df=vars_df.sort_values(['Layer','Node'])
            last_row=vars_df.groupby(['Layer','Node']).last().reset_index().iloc[-1]

            exit_layer=last_row.get('index',0)
            last_code_layer=last_row['Layer']
            last_code_node=last_row['Node']
        else:
            exit_layer=0
            last_code_layer=0
            last_code_node=0
        
        ###modified0622
        # modified 1305
        # if (last_code_layer>0 and last_code_layer<layer and last_code_node==2 and exit_layer==-1):
        #     prev_HP=code_out[(code_out['Layer']==last_code_layer) &
        #                 (code_out['New_var'].str.startswith("HP",na=False)) & (code_out['DF']>0)]
        #     if len(prev_HP)==0:
        #         return dsout,code_out,all_fit
            
        ####modified0622
        if (last_code_layer>0 and last_code_layer<layer and last_code_node==2 and exit_layer==-1):
            return dsout,code_out,all_fit

        # Exit the layer when there is no improvement
        if node>1 and exit_layer==-1:
            return dsout,code_out, all_fit

    # Get node variables already created for current layer (blocking variables)
        if node>1:
            # Get HP variables from current layer
            current_layer_hp=code_out[
                (code_out['Layer']==layer) & (code_out['New_var'].str.startswith('HP',na=False))
            ]['New_var'].unique().tolist()

            # Add to blocking variables
            cont_blk_var=cont_blk_var+current_layer_hp

        # Get node variables from previous layers as explanatory variables (dense connection)
        if layer>1:
            pre_node_vars=code_out[
                (code_out['Layer']>0) & (code_out['Layer']< layer) & (code_out['New_var'].str.startswith('HP',na=False))
            ]['New_var'].unique().tolist()

            # Add to explanatory variables
            cont_expl_var=cont_expl_var+pre_node_vars

    # ==============================================================================
    # Get the next Hyperplane number
    # ==============================================================================
    hyperplane_num = code_out['Hyperplane_num'].max() + 1 if len(code_out) >0 else 1

    # ==============================================================================
    # Prepare data for modeling
    # ==============================================================================

    step = dsout.copy()
    print(f"\nRBNNN: dsout DataFrame")
    print(dsout.head(5))
    step['byvar']=1
    np.random.seed(98753)
    step['NNN_rand'] = np.random.random(len(step))
    # step.to_excel("step1.xlsx",index=False)
    num_blk_var=len(cont_blk_var)+len(cat_blk_var)

    interact_level_used=min(layer,interact_level)

    expl_var = f"PP{layer:05d}_{node:03d}"
    hp_var = f"HP{layer:05d}_{node:03d}"

    # ==============================================================================
    # DIRECTION FINDING: First GLMSELECT
    # find the best linear combination of explanatory variables
    # ==============================================================================

    # Commented out
    # Get all explanatory variables

    all_expl_var=list(dict.fromkeys([v for v in cont_expl_var + cat_expl_var if v and v in step.columns]))
    all_blk_var=list(dict.fromkeys([v for v in cont_blk_var + cat_blk_var if v and v in step.columns]))

    all_cat_var=list(dict.fromkeys([v for v in cat_expl_var + cat_blk_var if v and v in step.columns]))

    print(f"\n [RBNNN L{layer}N{node} Direction finding.]")
    print(f"Explanatory vars available: {len(all_expl_var)} - {all_expl_var[:5]}")
    print(f"Blocking vars availaible: {len(all_blk_var)} - {all_blk_var[:5]}")

    # Prepare training data for direction finding
    train_mask=step['NNN_rand'] < 1.2
    step_train=step[train_mask].copy()

    # Build feature matrix for direction finding
    direction_features=all_blk_var + all_expl_var
    direction_features=[f for f in direction_features if f in step_train.columns]

    print(f" Total direction features:{len(direction_features)}")
    print(f" Training data rows:{len(step_train)}")
    print(f" Response var:'{resp_var}' in columns: {resp_var in step_train.columns}")

    # Initialize PP scoring code variable
    pp_intercept=0.0
    pp_coefs={}
    pp_original_features=direction_features
    kk=0

    if len(direction_features) == 0 or resp_var not in step_train.columns:
        print(f" *** ISSUE #1: Setting {expl_var}=0 (no features or no response variables)")
        print(f" direction_features count:{len(direction_features)}")
        print(f" Response var in columns: {resp_var in step_train.columns}")
        step[expl_var]=0
        kk=0
    else:
        # Remove rows with missing values
        valid_cols=[resp_var] + direction_features
        step_train_clean=step_train[valid_cols].dropna()
        print(f" After dropna:{len(step_train_clean)} row (need >=10)")

        if len(step_train_clean) < 10:
            print(f" *** ISSUE #2: Setting {expl_var}=0 (insufficient training data: {len(step_train_clean)} rows)")
            step[expl_var]=0
            kk=0
        else:
            # Commented out
            # Encode categorical variables as dummies

            y_direction=step_train_clean[resp_var]

            X_direction_cat,class_vars_mapping,cat_var_dropped_mapping=get_dummies_drop_last(step_train_clean[direction_features],all_cat_var)
            X_direction=pd.concat([X_direction_cat,step_train_clean[direction_features]],axis=1)

            # X_direction.to_excel("X_direction.xlsx")
            # y_direction.to_excel("y_direction.xlsx")
            print(f" X_direction shape : {X_direction.shape}, y_direction shape: {y_direction.shape}")
            print(f" X_direction columns: {len(X_direction.columns)}")

            try:
                print("TRY 1")
                # modified0525
                if node>1:
                    current_layer_hp=code_out[
                        (code_out['Layer']==layer) &
                        (code_out['New_var'].str.startswith('HP',na=False))
                    ]['New_var'].unique().tolist()
                
                else:
                    current_layer_hp=[]

                # Use stepwise-like selection with sklearn
                selected_encoded_features,selected_features=stepwise_sbc_maxstep(X_direction,y_direction,class_vars_mapping,10000,current_layer_hp,verbose=True)
                if len(selected_features)>0:
                    X_selected=X_direction[selected_encoded_features]
                    final_model=LinearRegression()
                    final_model.fit(X_selected,y_direction)
                    
                    ###modified0629
                    n, k = X_selected.shape
                    resid = final_model.predict(X_selected) - y_direction
                    if n > k+1:
                        mse = np.sum(resid**2) / (n-k-1) 
                        X2 = X_selected.copy()
                        X2.insert(0,'const',1)
                        cov_matrix = mse * np.linalg.inv(X2.T @ X2)
                        se = np.sqrt(np.diag(cov_matrix[1:, 1:]))
                        t_value = final_model.coef_/ se
                        p_value = 2 * (1 - scipy.stats.t.cdf(abs(t_value), df=n-k-1))
                        p_value = np.where(p_value < 0.0001, "<.0001", p_value)
                        std_est = final_model.coef_*X_selected.std(ddof=0)/y_direction.std(ddof=0)
                     
                    else:
                        t_value = [np.nan]*k
                        p_value = [np.nan]*k
                        se = [np.nan]*k
                        std_est = [np.nan]*k
                        
                    dic_tval = dict(zip(selected_encoded_features, t_value))
                    dic_pval = dict(zip(selected_encoded_features, p_value))
                    dic_se = dict(zip(selected_encoded_features, se))
                    dic_stdest = dict(zip(selected_encoded_features, std_est))
                    pp_stats = {'tvalue':dic_tval, 'pvalue':dic_pval, 'stderr':dic_se, 'stdest':dic_stdest}
                    
                    #################################

                    # Store model coefficients for scoring code generation
                    pp_intercept=final_model.intercept_
                    pp_coefs=dict(zip(selected_encoded_features, final_model.coef_))
                    pp_original_features=selected_features
                    # print("pp_coefs",pp_coefs)
                    # Generate predictions as the direction variable
                    X_full_cat,_,_= get_dummies_drop_last(step[direction_features],all_cat_var)
                    X_full=pd.concat([X_full_cat,step[direction_features]],axis=1)
                    X_full=X_full[selected_encoded_features].fillna(0)

                    # modified0525
                    # step[expl_var]=final_model.predict(X_full)
                    X_full=X_full.copy()
                    X_full.loc[:,X_full.columns.isin(current_layer_hp)]=0

                    # modified0617

                    # step[expl_var]=final_model.predict(X_full)-final_model.intercept_

                    pp_coefs={k:float(f"{v:.5e}") for k,v in pp_coefs.items()}
                    step[expl_var]=X_full.mul(pp_coefs).sum(axis=1)
                    step[expl_var]=step[expl_var].apply(lambda x: format_figures(x,11))

                    selected_features=[f for f in selected_features if f not in current_layer_hp]
                    pp_original_features=[f for f in pp_original_features if f not in current_layer_hp]
                    pp_coefs={k:v for k,v in pp_coefs.items() if k not in current_layer_hp}

                    kk= len(selected_features)
                    print(f" SUCCESS: {expl_var} calculated with {kk} features")
                    print(f" Expl_var {expl_var} range :[{step[expl_var].min():.4f},{step[expl_var].max():.4f}], mean:{step[expl_var].mean():.4f}")
                else:

                    print(f" **** ISSUE #3: No features selected, setting {expl_var}=0")
                    step[expl_var]=0
                    kk=0

            # Commented out
            except Exception as e:
                print(f" *** ERROR #4: Direction fiding failed: {e} ")
                warnings.warn(f"Direction finding failed:{e}")
                step[expl_var]=0
                kk=0

    # ==============================================================================
    # ADD PP VARIABLE CODE to code_out
    # Generate actual scoring code for the PP direction variable
    # ==============================================================================
    # print("pp_riginal_features", pp_original_features) # Removed

    if kk>0 and len(pp_coefs)>0:

        pp_code_df=glmselect_score_code(
            selected_features=list(pp_coefs.keys()),
            coefs=pp_coefs,
            intercept=None, # modified0525
            stats=pp_stats, # modified0629
            est_name=expl_var,
            original_features=pp_original_features
        )
        pp_code_df['Layer']=layer
        pp_code_df['Node']=node
        pp_code_df['Hyperplane_num']=hyperplane_num

        code_out=pd.concat([code_out, pp_code_df], ignore_index=True)

    elif kk>0:
            pp_code_row=pd.DataFrame({
                'Layer':[layer],
                'Node':[node],
                'Hyperplane_num':[hyperplane_num],
                'New_var':[expl_var],
                'Knot':[0.0],
                'Effect':['Direction'],
                'Parameter':["Direction"],
                'DF':[kk],
                'Estimate':[0.0],
                'StandardizedEst':[0.0],
                'StdErr':[0.0],
                'tValue':[0.0],
                'Probt':[0.0],
                'index':[0],
                'code':['']
            })
            code_out=pd.concat([code_out,pp_code_row], ignore_index=True)
            print(f" ✔ Added PP metadata only (no coefficients availaible)")

    # ==============================================================================
    # KNOT GENERATION: Create 201 knots using percentiles (0 to 100 by 0.5)
    # ==============================================================================
    percentile_points=np.arange(0,100.5,0.5)

    print(f"[RBNNN L{layer}N{node}] KNOT Generation Check:]")
    print(f" {expl_var} notna count:{step[expl_var].notna().sum()}/{len(step)}")
    print(f" {expl_var} std:{step[expl_var].std():.10f}")
    print(f" {expl_var} min:{step[expl_var].min():.6f}, max:{step[expl_var].max():.6f}")

    if step[expl_var].notna().sum()>0 and step[expl_var].std()>0:
        print(f" Using percentiles for knots(std>0)")
        knots=sas_pctldef5(step[expl_var].dropna(),percentile_points)
        # modified0617
        knots=np.round(knots,9)
    else:
        print(f" Using Default zero knots, std={step[expl_var].std():.10f}")
        knots=np.zeros(201)

    print(f" [RBNNN L{layer}N{node}] PP values Check:")

    # ==============================================================================
    # RELU ACTIVATION: Create blade variables (minx  and maxx arrays)
    # minx[i]=min(0,PP-knot[i])
    # mixx[i]=max(0,PP-knot[i])
    # ==============================================================================

    pp_values=step[expl_var].values

    print(f"[RBNNN L{layer}N{node}] PP Value Check:]")
    print(f" {expl_var} non zero count:{(pp_values !=0).sum()}/{len(pp_values)}")
    print(f" Range:[ {pp_values.min():.6f}, {pp_values.max():.6f}")
    print(f" Mean: {pp_values.mean():.6f}, Std: {pp_values.std():.6f}")

    if (pp_values==0).all():
        print(f" **** Warning: all PP values are zero! check direction finding above . ****")

    # Create minx and maxx arrays
    minx_cols={}
    maxx_cols={}

    for i, knot in enumerate(knots):
        minx_cols[f'minx{i+1}']=np.minimum(0,pp_values-knot)
        maxx_cols[f'maxx{i+1}']=np.maximum(0,pp_values-knot)

    for col_name,col_values in minx_cols.items():
        step[col_name]=col_values
    for col_name,col_values in maxx_cols.items():
        step[col_name]=col_values

    step['misx']=0

    # ==============================================================================
    # SECOND GLMSELECT: Select knots via stepwise regression
    # Based on activation parameter:
    # 0 = use both minx and maxx
    # 1 = use only maxx (max(0,x))
    # -1 = use only minx (min(0,x))
    # ==============================================================================


    if activation ==0:
        relu_features=['misx']+[f"minx{i}" for i in range(1,202)]+[f"maxx{i}" for i in range(1,202)]
    elif activation==1:
        relu_features=['misx']+[f"maxx{i}" for i in range(1,202)]
    else:
        relu_features=['misx']+[f"minx{i}" for i in range(1,202)]

    model_blk_vars=[f for f in all_blk_var if f in step.columns]
    model_relu_features=[f for f in relu_features if f in step.columns]

    # Prepare data for second model
    valid_cols=[resp_var] + model_blk_vars+model_relu_features
    step_model = step[valid_cols].dropna()

    if len(step_model) < 10 or kk == 0:
        code_row=pd.DataFrame({
            'Layer':[layer],
            'Node':[node],
            'Hyperplane_num':[hyperplane_num],
            'New_var':[hp_var],
            'Knot':[0.0],
            'Effect':[''],
            'Parameter':[''],
            'DF':[0],
            'Estimate':[0.0],
            'StandardizedEst':[0.0],
            'StdErr':[0.0],
            'tValue':[0.0],
            'Probt':[1.0],
            'index':[-1],
            'code':[f'{hp_var} = 0;']
        })

        code_out=pd.concat([code_out,code_row], ignore_index=True)
        dsout[hp_var]=0
        return dsout, code_out,all_fit

    # Prepare features: ONLY select from RELU features
    X_relu=step_model[model_relu_features]
    X_blk=step_model[model_blk_vars] if len(model_blk_vars)>0 else pd.DataFrame()
    y_model=step_model[resp_var]

    print(f"\n [RELU Selection] Data diagnostics:")
    print(f" X_relu shape {X_relu.shape}")
    print(f" X_relu columns (first 10): {list(X_relu.columns)[:10]}")
    print(f" X_blk shape: {X_blk.shape if not X_blk.empty else 'empty'}")
    print(f" y_model shape: {y_model.shape}, non-null: {y_model.notna().sum()}")
    print(f" X_relu dtypes: {X_relu.dtypes.value_counts().to_dict()}")
    # Commented out

    try:
        # Stepwise features selection for RELU knots only
        maxstep=max_dir_reuse
        if not X_blk.empty:
            X_relu=pd.concat([X_blk,X_relu],axis=1)
        selected_relu_encoded_features,selected_relu_features=stepwise_sbc_maxstep(X_relu,y_model,{},maxstep,X_blk.columns,verbose=True)

        if len(selected_relu_features) >0 or len(X_blk.columns)>0:
            X_final=X_relu[selected_relu_features]
            final_model=LinearRegression()
            final_model.fit(X_final,y_model)
            coefs = dict(zip(selected_relu_features, final_model.coef_))
            intercept=final_model.intercept_

            print(f"\n Knot Model fitted:")
            print(f" Intercept:{intercept:.4e}")
            print(f" {len(coefs)} coefficients")

            coef_values=list(coefs.values())
            print(f" Coef range:[{min(coef_values):.4e}, {max(coef_values):.4e}]")
            print(f" Coef mean: {np.mean(coef_values):.4e}")
            zero_coefs=sum(1 for c in coef_values if abs(c)< 1e-10)
            if zero_coefs>0:
                print(f" Warning:{zero_coefs}/{len(coefs)} coefficients are essentially ZERO!")
                print(f" Top 3 features by |coefs|:")
                sorted_coefs=sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
                for feat, coef_val in sorted_coefs:
                    print(f" {feat}: {coef_val:.4e}")
        else:
            coefs={}
            intercept=0
            selected_relu_features=[]

    except Exception as e:
        warnings.warn(f"Knot selection failed:{e}")
        coefs={}
        intercept=0
        selected_knot_features=[]

    # modified0525

    selected_knot_features=[f for f in selected_relu_features if f.startswith('min') or f.startswith('max')]


    # =====================================================================
    # Generate fit statistics
    # =====================================================================

    n=len(step_model)
    k=len(selected_knot_features)+len(model_blk_vars)
    y_mean=y_model.mean() if n>0 else 0

    root_mse=0
    dependent_mean=y_mean
    r_square=0
    adj_r_sq=0
    aic=0
    aicc=0
    sbc=0

    if n>0 and k>0 and len(coefs)>0 and final_model is not None:
        try:
            # modified0527
            # if len(model_blk_vars)>0 and len(selected_relu_features)>0:
            #     X_final=pd.concat([X_blk,X_relu[selected_relu_features]],axis=1)
            # elif len(model_blk_vars)>0:
            #     X_final=X_blk
            # else:
            #     X_final=X_relu[selected_relu_features] if len(selected_relu_features)>0 else pd.DataFrame()

            # if len(X_final)>0:
            #     y_pred=final_model.predict(X_final)
            if len(selected_relu_features)>0:
                X_final=X_relu[selected_relu_features].copy()
                y_pred=final_model.predict(X_final)

                ss_res=np.sum((y_model-y_pred)**2)
                ss_tot=np.sum((y_model-y_mean)**2)

                if n > k:
                    root_mse=np.sqrt(ss_res/(n-k))

                if ss_tot>0:
                    r_square=1-ss_res/ss_tot
                
                if n > k+1 and ss_tot >0:
                    adj_r_sq=1-(1-r_square)*(n-1)/(n-k-1)

                p=k+1
                if ss_res>0 and n>0:
                    # modified0617
                    aic=n*np.log(ss_res/n)+2*p+n+2
                    if n>p+2:
                        aicc=n*np.log(ss_res/n)+n*(n+p)/(n-p-2)
                    sbc=n*np.log(ss_res/n)+p*np.log(n)
            
                ###modified0629
                resid = y_model-y_pred
                if n > k + 1:
                    mse = np.sum(resid**2) / (n - k - 1) 
                    X2 = X_final.copy()
                    X2.insert(0,'const',1)
                    cov_matrix = mse * np.linalg.inv(X2.T @ X2)
                    se = np.sqrt(np.diag(cov_matrix[1:, 1:]))
                    t_value = final_model.coef_/ se
                    p_value = 2 * (1 - scipy.stats.t.cdf(abs(t_value), df=n-k-1))
                    p_value = np.where(p_value < 0.0001, "<.0001", p_value)
                    std_est = final_model.coef_*X_final.std(ddof=0)/y_direction.std(ddof=0)
                else:
                    t_value = [np.nan]*k
                    p_value = [np.nan]*k
                    se = [np.nan]*k
                    std_est = [np.nan]*k
                    
                dic_tval = dict(zip(selected_relu_features, t_value))
                dic_pval = dict(zip(selected_relu_features, p_value))
                dic_se = dict(zip(selected_relu_features, se))
                dic_stdest = dict(zip(selected_relu_features, std_est))
                stats = {'tvalue':dic_tval, 'pvalue':dic_pval, 'stderr':dic_se, 'stdest':dic_stdest}
                
                ########################################################
        except Exception as fit_err:
            print(f" Warning: Could not calculate fit statistics: {fit_err}")


   
    
    fit_row=pd.DataFrame({
        '_NAME_':['nValue1'],
        'Layer':[layer],
        'Node':[node],
        'N':[n],
        'Intercept': [intercept],
        'Root MSE':[root_mse],
        'Dependent Mean':[dependent_mean],
        'R-Square':[r_square],
        'Adj R-Sq':[adj_r_sq],
        'AIC':[aic],
        'AICC':[aicc],
        'SBC':[sbc]
    })
    all_fit=pd.concat([all_fit[all_fit['Layer']>0], fit_row], ignore_index=True)





    code_rows=[]
    num_knts=len([f for f in selected_knot_features if f.startswith('min') or f.startswith('max')])

    print(f" \n[RBNN L{layer}N{node}] HP Generating:")
    print(f" Selected knot features:{len(selected_knot_features)}")
    print(f" Knot features (min/max):{num_knts}")
    if len(selected_knot_features)>0:
        print(f" Sample features: {selected_knot_features[:5]}")

    if num_knts==0:
        # No significant knots found
        code_row=pd.DataFrame({
            'Layer':[layer],
            'Node':[node],
            'Hyperplane_num':[hyperplane_num],
            'New_var':[hp_var],
            'Knot':[0.0],
            'Effect':[''],
            'Parameter':[''],
            'DF':[0],
            'Estimate':[0.0],
            'StandardizedEst':[0.0],
            'StdErr':[0.0],
            'tValue':[0.0],
            'Probt':[1.0],
            'index':[-1],
            'code':[f'{hp_var} = 0;']
        })

        code_out=pd.concat([code_out,code_row],ignore_index=True)
        dsout[hp_var]=0
        if expl_var not in dsout.columns:
            dsout[expl_var]=step[expl_var].values    # modified 1305
    else:
        # Build code for HP variable from selected knots
        hp_code_parts=[]
        idx=0
        code_rows=[]
        # modified0527
        for i,feature in enumerate(selected_knot_features):
            if feature.startswith('misx'):
                continue
            elif feature.startswith('minx') or feature.startswith('maxx'):
                direction=feature[:3]
                knot_idx=int(feature[4:])-1
                knot_value=knots[knot_idx] if knot_idx < len(knots) else 0
                estimate =coefs.get(feature,0)

                idx += 1
                # modified0617
                knot_value_round=np.round(knot_value,9)
                # modified0622
                # code_part = f"{estimate:.10e}*{direction}(0,{expl_var} - {knot_value_round})" 
                code_part = f"{estimate:.5e} * {direction}(0, {expl_var} - {knot_value_round})"
                if i==0:
                    # code_part=f"{hp_var} = " + code_part + "+"
                    # print("code_part",code_part)
                    if len(selected_knot_features)>1:
                        code_part=f"{hp_var} = " + code_part + "+"
                    else:
                        code_part=f"{hp_var} = " + code_part + ";"

                elif i==len(selected_knot_features)-1:
                    code_part=code_part + ";"
                else:
                    code_part=code_part + "+"

                    # hp_code_parts.append(code_part)
                
                code_row=pd.DataFrame({
                    'Layer':[layer],
                    'Node':[node],
                    'Hyperplane_num':[hyperplane_num],
                    'New_var':[hp_var],
                    'Knot':[knot_value],
                    'Effect':[feature],
                    'Parameter':[feature],
                    'DF':[1],
                    'Estimate':[estimate],
                    'StandardizedEst':[stats.get('stdest',{}).get(feature,np.nan)], ###modified0629
                    'StdErr':[stats.get('stderr',{}).get(feature,np.nan)], ###modified0629
                    'tValue':[stats.get('tvalue',{}).get(feature,np.nan)], ###modified0629
                    'Probt':[stats.get('pvalue',{}).get(feature,np.nan)], ###modified0629
                    'index':i,
                    'code':[code_part] # modified0527
                })
                code_rows.append(code_row)
            else:
                print(f" WARNING: skipping unknown feature type:{feature}")
                continue






























































        if len(code_rows)>0:
            df_code_rows=pd.concat(code_rows)
            code_out=pd.concat([code_out,df_code_rows],ignore_index=True)
        # ==============================================
        # Apply the code to generate HP variable in dsout
        # ==============================================

        hp_values=np.zeros(len(dsout))

        print(f" \n[RBNNN L{layer}N{node}] Calculating HP values:")
        print(f" PP_value stats: min={step[expl_var].min():.4f}, max={step[expl_var].max():.4f}, mean={step[expl_var].mean():.4f}")
        print(f" Processing {len(selected_knot_features)} selected RELU knot features")

        relu_count=sum(1 for f in selected_knot_features if f.startswith(('minx','maxx')))
        other_count=sum(1 for f in selected_knot_features if not f.startswith(('minx','maxx','misx')))

        if other_count>0:
            print(f" WARNING:{other_count} non-RELU features in selection (should be 0!)")
            other_features=[f for f in selected_knot_features if not f.startswith(('minx','maxx','misx'))]
            print(f" Non-RELU features:{other_features}")

        for feature in selected_knot_features:
            if feature.startswith('misx'):
                continue
            elif feature.startswith('minx') or feature.startswith('maxx'):
                direction=feature[:3]
                knot_idx=int(feature[4:])-1
                knot_value=knots[knot_idx] if knot_idx < len(knots) else 0
                estimate = coefs.get(feature,0)

                # modified0617
                estimate=float(f"{estimate:.5e}")
                knot_value=np.round(knot_value,9)

                if expl_var not in dsout.columns:
                    dsout[expl_var]=step[expl_var].values

                pp_vals=dsout[expl_var].values

                diff=pp_vals-knot_value
                if direction =='min':
                    activation_vals=np.minimum(0,diff)
                    non_zero_activations=(activation_vals<0).sum()
                else:
                    activation_vals=np.maximum(0,diff)
                    non_zero_activations=(activation_vals>0).sum()

                contribution=estimate * activation_vals
                hp_values+=contribution

                print(f"{feature}: knot={knot_value:.4f}, coef={estimate:.4f}, contribution range=[{contribution.min():.4f}, {contribution.max():.4f}]")
                print(f"{feature}: knot={knot_value:.4f}, coef={estimate:.4f} ")
                print(f" {non_zero_activations/len(activation_vals)} points activate (non-zero)")
                print(f" activation range=[{activation_vals.min():.4f},{activation_vals.max():.4f}]")
                print(f" contribution range=[{contribution.min():.4f},{contribution.max():.4f}]")

                if non_zero_activations==0:
                    print(f" Warning: this knot produce NO activations!")
                if abs(estimate)<1e-10:
                    print(f" Warning: coefficient is essentially ZERO")

        # modified0617
        hp_values[hp_values>=-1]=np.round(hp_values[hp_values>=-1],decimals=9)
        hp_values[hp_values < -1]=np.round(hp_values[hp_values<-1],decimals=8)

        dsout[hp_var]=hp_values
        print(f"\n {hp_var} FINAL RESULT:")
        print(f" Range=[{hp_values.min():.4f}, {hp_values.max():.4f}]")
        print(f" Mean: {hp_values.mean():.4f}, Std:{hp_values.std():.4f}")
        print(f" Non zero HP value: {(hp_values!=0).sum()}/{len(hp_values)}")
        print(f" Non-zero values: {(hp_values!=0).sum()/len(hp_values)} ({100*(hp_values !=0).sum()/len(hp_values):.1f}%)")


        if (hp_values==0).all():
            print(" PROBLEM: ALL HP values are ZERO")
            print(" Check if selected knots are activating (see warning above)")
            print(f" Check if coefficients are non-zero")

        if expl_var not in dsout.columns:
            dsout[expl_var]=step[expl_var].values

    # print("\n"+"="*60) # Removed
    # print(f"\n*****rbnnn_data*****:{all_fit}")

    # print(f"\n*****dsout*****:{dsout}")
    # print(f"\n*****code_out*******:{code_out}")
    # print(f"RBNNN complete")
    # print("\n"+"="*60)
    return dsout, code_out, all_fit

def backward_sbc(X,y,class_vars_mapping={},included_vars=[]):

    included_vars_encoded=included_vars.copy()
    if len(included_vars)>0:
        class_vars=list(class_vars_mapping.keys())
        class_vars_encoded=[]
        for c in class_vars_mapping:
            if c in included_vars:
                class_vars_encoded=class_vars_encoded+class_vars_mapping[c]
                included_vars_encoded=included_vars_encoded+class_vars_encoded
                included_vars_encoded=[var for var in included_vars_encoded if var!=c]

    # modified0617
    available=[]
    available=[c for c in X.columns if (c not in included_vars) and (c not in included_vars_encoded)]
    selected_candidates = included_vars_encoded + available

    if len(included_vars_encoded)>0:
        bic_0=calc_sbc_vals(X[included_vars_encoded],y)
        best_score=bic_0
    else:
        best_score=np.inf

    # available=[c for c in X.columns if (c not in included_vars) and (c not in included_vars_encoded)]
    # selected_candidates=included_vars_encoded + available

    changed=True
    remove_best=None
    remove_best_score=best_score

    while changed:
        changed=False
        for eff in available:
            try:
                cols_1=[c for c in selected_candidates if c not in [eff]]
                bic1=calc_sbc_vals(X[cols_1],y)
                if bic1<remove_best_score:
                    remove_best_score=bic1
                    remove_best=eff
            except:
                continue
        if remove_best is not None and remove_best_score < best_score:
            selected_candidates.remove(remove_best)
            best_score=remove_best_score
            changed=True

    final_selected=selected_candidates.copy()

    selected=included_vars + [c for c in final_selected if c not in included_vars_encoded]

    return final_selected, selected

def RBNN_scorecode(
        dsin : pd.DataFrame,
        resp_var:str ,
        cont_blk_var:List[str],
        cat_blk_var:List[str],
        code_out :pd.DataFrame,
        dsout:pd.DataFrame):

    cont_blk_var=list(cont_blk_var) if cont_blk_var else []
    cat_blk_var=list(cat_blk_var) if cat_blk_var else []

    valid_code=code_out[code_out['DF']>0] if 'DF' in code_out.columns else code_out

    print(f"    [RBNN_scorecard] valid_code rows (DF>0): {len(valid_code)}")
    print(f"    [RBNN_scorecard] code_out total rows: {len(code_out)}")

    if len(valid_code)==0:
        print(f" \n *** EARLY EXIT 1: No HP variable with DF>0. Creating default NN_score=0 ***")
        print(f" code_out.shape {code_out.shape}")
        if len(code_out)>0:
            print(f" code_out.DF unique values:{code_out['DF'].unique() if 'DF' in code_out.columns else 'NO DF COLUMN'}")

        parms_f=pd.DataFrame({
            'Layer':9999,
            'Node':0,
            'Hyperplane_num':0,
            'Effect':'Intercept',
            'Parameter':'Intercept',
            'Estimate':0.0,
            'DF':0,
            'New_var':'NN_score',
            'code':'NN_score=0;',
            'Alteryx_code':'0;',
            'Knot':0.0,
            'StandardizedEst':0.0,
            'StdErr':0.0,
            'tValue':0.0,
            'Probt':0.0,
            'index':0,
        })
        code_out=pd.concat([code_out, parms_f], ignore_index=True)
        dsout['NN_score']=0

        print(f" [RBNN_scorecard] Created default NN_score=0 code (Layer 9999)")
        return code_out, dsout

    if valid_code['Layer'].max()<=0:
        print(f" \n *** EARLY EXIT 2:Max layer <=0. Creating default NN_score=0 ***")
        print(f" valid_code['Layer'] max {valid_code['Layer'].max()}")
        print(f" valid_code['Layer'] unique  {valid_code['Layer'].unique()}")

        parms_f=pd.DataFrame({
            'Layer':9999,
            'Node':0,
            'Hyperplane_num':0,
            'Effect':'Intercept',
            'Parameter':'Intercept',
            'Estimate':0.0,
            'DF':0,
            'New_var':'NN_score',
            'code':'NN_score=0;',
            'Alteryx_code':'0;',
            'Knot':0.0,
            'StandardizedEst':0.0,
            'StdErr':0.0,
            'tValue':0.0,
            'Probt':0.0,
            'index':0,
        })
        code_out=pd.concat([code_out, parms_f], ignore_index=True)
        dsout['NN_score']=0
        return code_out, dsout

    final_layer=int(valid_code['Layer'].max())



    # ======================================================================
    # Get final layer HP variables
    # ======================================================================

    final_hp_prefix=f'HP{final_layer:05d}'

    # Get distinct HP variables from final layer
    final_nodes=code_out[
        (code_out['New_var'].str.startswith(final_hp_prefix,na=False)) &
        (code_out['DF']>0)
    ]['New_var'].unique().tolist()

    # modified0527
    code_out=code_out[code_out['DF']>0]

    print(f"[RBNN_scorecard] Final layer {final_layer}, HP prefix:{final_hp_prefix}")
    print(f"[RBNN_scorecard] Final nodes found (DF>0): {len(final_nodes)}")
    if len(final_nodes)>0:
        print(f" Final nodes: {final_nodes}")

    if len(final_nodes)==0:
        print(f" \n *** EARLY EXIT 3: No valid code (DF>0). Creating default NN_score=0 ***")
        print(f" checking code_out for final layer {final_layer}:")
        final_layer_rows=code_out[code_out['Layer']==final_layer]
        print(f" Row in final layer: {len(final_layer_rows)}")
        if len(final_layer_rows)>0:
            print(f" New_var values:{final_layer_rows['New_var'].unique()}")
            print(f" DF values: {final_layer_rows['DF'].unique() if 'DF' in final_layer_rows.columns else 'NO DF'} ")


        parms_f=pd.DataFrame({
            'Layer':9999,
            'Node':0,
            'Hyperplane_num':0,
            'New_var':'NN_score',
            'Knot':0.0,
            'Effect':'Intercept',
            'Parameter':'Intercept',
            'DF':0,
            'Estimate':0.0,
            'StandardizedEst':0.0,
            'StdErr':0.0,
            'tValue':0.0,
            'Probt':0.0,
            'index':0,
            'code':'NN_score=0;',
            'Alteryx_code':'0;'
        })
        code_out=pd.concat([code_out, parms_f], ignore_index=True)
        dsout['NN_score']=0
        return code_out, dsout

    num_blk_var=len(cont_blk_var)+len(cat_blk_var)

    # ======================================================================
    # Run final GLMSELECT with backward selection
    # ======================================================================

    all_blk_var=[v for v in cont_blk_var + cat_blk_var if v and v in dsout.columns]
    all_cat_blk_var=[v for v in cat_blk_var if v and v in dsout.columns]
    all_cont_blk_var=[v for v in cont_blk_var if v and v in dsout.columns]

    final_nodes_in_data=[v for v in final_nodes if v in dsout.columns]


    print(f"\n [HP variable in dataset]")
    print(f" final node expected:{len(final_nodes)}")
    print(f" final node in dsout:{len(final_nodes_in_data)}")
    if len(final_nodes)!=len(final_nodes_in_data):
        missing_hp=[v for v in final_nodes if v not in dsout.columns]
        print(f" *** MISSING HP variable:{missing_hp}***")
    else:
        print(f" All HP variables present in dsout")
        for hp_var in final_nodes_in_data[:3]:
            hp_vals=dsout[hp_var].values
            non_zero=(hp_vals!=0).sum()
            print(f" {hp_var}:{non_zero}/{len(hp_vals)} non-zero ({100*non_zero/len(hp_vals):.1f}%)")

    print(f"[NN_score Calculation Setup]")
    print(f"  Blocking vars: {len(all_blk_var)}")
    print(f" Final nodes (HP vars): {len(final_nodes_in_data)}-{final_nodes_in_data[:5] if len(final_nodes_in_data) >0 else 'NONE'}")
    print(f" Response var '{resp_var}' in dsout: {resp_var in dsout.columns}")

    if resp_var not in dsout.columns:
        print(f"\n*** EARLY EXIT 4: Missing response variable ***")
        dsout['NN_score']=0
        return code_out,dsout

    # Prepare data (including blocking variable vars + HP vars)
    model_features=all_blk_var + final_nodes_in_data
    valid_cols=[resp_var] + model_features
    step_model=dsout[valid_cols].dropna()

    if len(step_model)<10:
        print(f"\n*** EARLY EXIT 5: Insufficient data after dropna")
        dsout['NN_score']=0
        return code_out, dsout

    y_model=step_model[resp_var]

    # ======================================================================
    # Seperate blocking vars from HP vars
    # ======================================================================

    X_blk_cat, class_vars_mapping, cat_var_dropped_mapping = get_dummies_drop_last(step_model,all_cat_blk_var)
    if X_blk_cat is not None:
        X_model=pd.concat([X_blk_cat,step_model[model_features]],axis=1)
    else:
        X_model=step_model[model_features]
    try:

        selected_encoded_vars,selected_vars=backward_sbc(X_model,y_model,class_vars_mapping,all_blk_var)

        if len(selected_encoded_vars)>0:
            X_final=X_model[selected_encoded_vars]

        else:
            print(f"\n*** EARLY EXIT 6: No features after selection ***")
            dsout["NN_score"]=0
            return code_out, dsout

        # Commented out

        selected_features=X_final.columns.tolist()

        print(f"\n [Final Model Features]")
        # print(f" Blocking features (forced in): {len(X_blk.columns) if len(X_blk.columns)>0 else 0}")
        # print(f" HP features (selected): {len(selected_hp_features)}")
        print(f" Total features in final model: {len(selected_features)}")

        final_model=LinearRegression()
        final_model.fit(X_final,y_model)

        intercept=final_model.intercept_
        coefs=dict(zip(selected_features,final_model.coef_))
        
        ###modified0629
        n, k = X_final.shape
        resid = final_model.predict(X_final) - y_model
        if n > k+1:
            mse = np.sum(resid**2) / (n - k-1) 
            X2 = X_final.copy()
            X2.insert(0,'const',1)
            cov_matrix = mse * np.linalg.inv(X2.T @ X2)
            se = np.sqrt(np.diag(cov_matrix[1:, 1:]))
            t_value = final_model.coef_/ se
            p_value = 2 * (1 - scipy.stats.t.cdf(abs(t_value), df=n-k-1))
            p_value = np.where(p_value < 0.0001, "<.0001", p_value)
            std_est = final_model.coef_*X_final.std(ddof=0)/y_model.std(ddof=0)
        
        else:
            t_value = [np.nan]*k
            p_value = [np.nan]*k
            se = [np.nan]*k
            std_est = [np.nan]*k
        
        dic_tval = dict(zip(selected_features, t_value))
        dic_pval = dict(zip(selected_features, p_value))
        dic_se = dict(zip(selected_features, se))
        dic_stdest = dict(zip(selected_features, std_est))
        pp_stats = {'tvalue':dic_tval, 'pvalue':dic_pval, 'stderr':dic_se, 'stdest':dic_stdest}
        ########################
        
        print(f"[ Final Model coefficients]")
        print(f" Intercept: {intercept:.6e}")
        print(f" Coefficients (top 5 by abs):")


        sorted_coefs=sorted(coefs.items(),key=lambda x: abs(x[1]), reverse=True)[:5]
        for feat, coef_val in sorted_coefs:
            print(f" {feat}:{coef_val:.6e}")
        zero_coefs=sum(1 for c in coefs.values() if abs(c) < 1e-10)
        if zero_coefs>0:
            print(f" WARNING {zero_coefs}/{len(coefs)} coefficients are essentially zero")

    except Exception as e:
        print(f"\n *** EARLY EXIT 7: final model fitting failed: {e} ***")
        # traceback.print_exc(file=sys.stdout)
        # sys.stdout.flush()

        warnings.warn(f"Final model fitting failed: {e}")
        dsout['NN_score']=0
        return code_out, dsout

    # ======================================================================
    # Generate score code using glmselect_score_code logic
    # ======================================================================

    print(f" [RBNN scorecode] Generated score code for {len(selected_features)} features...")
    print(f" [RBNN scorecode] Selected features: {selected_features[:10]}....")
    ### modified0629
    # parms_f= glmselect_score_code(selected_features,coefs,intercept,'NN_score',  model_features) 
    ### modified0629
    parms_f= glmselect_score_code(selected_features,coefs,intercept, pp_stats, 'NN_score',  model_features)

    if len(parms_f)>0:
        sample_code= ' '.join(parms_f['code'].head(5).tolist())
        print(f" [RBNN scorecode] Sample code (first 5 rows): {sample_code[:300]}...")

    parms_f['Layer']=9999
    parms_f['Node']=0
    parms_f['Hyperplane_num']=0

    code_out=pd.concat([code_out[code_out['Layer']>0],parms_f],ignore_index=True)



    # Apply score code to generate NN_score on dsout
    # ======================================================================

    print(f"\n [ Applying NN_score Calculation]")
    print(f" Starting with intercept: {intercept:.6e}")
    print(f" Processing {len(selected_features)} features")

    nn_score=np.full(len(dsout),intercept)

    features_applied=0
    features_missing=[]

    for feature in selected_features:
        if feature in dsout.columns:
            coef=coefs.get(feature,0)
            contribution=coef*dsout[feature].fillna(0).values
            nn_score+=contribution
            features_applied+=1
            if features_applied<=3:
                print(f" Feature {feature}: coef={coef:.6e}, contribution range=[{contribution.min():.6e},{contribution.max():.6e}]")
        elif feature in X_final.columns:
            for orig_col in all_blk_var:
                if feature.startswith(orig_col + '_'):
                    dummy_value=feature[len(orig_col)+1:]
                    if orig_col in dsout.columns:
                        coef=coefs.get(feature,0)
                        contribution=coef*(dsout[orig_col].astype(str)==dummy_value).astype(float).values
                        nn_score+=contribution
                        features_applied+=1
                        if features_applied<=3:
                            print(f" Dummy {feature}: coef={coef:.6e}, contribution range=[{contribution.min():.6e},{contribution.max():.6e}]")
                    break
        else:
            features_missing.append(feature)






    print(f"[NN_score Final Statistics]")
    print(f" NN_score min: {nn_score.min():.6e}")
    print(f" NN_score max: {nn_score.max():.6e}")
    print(f" NN_score mean: {nn_score.mean():.6e}")
    print(f" NN_score std: {nn_score.std():.6e}")

    all_zero=(nn_score==0).all()
    all_equal_intercept=np.allclose(nn_score,intercept)

    if all_zero:
        print(f" ** ALL NN_SCORE values are zero! **")
        print(f" This mean either")
        print(f" 1. Intercept is 0 AND all coefficients are 0")
        print(f" 2. OR all HP features values in dsout are 0")
        print(f" 3. OR HP features are missing from dsout")
        if abs(intercept)<1e-10:
            print(f" CONFIRMED: Intercept is essentially ZERO ({intercept:.10e})")
        if all(abs(c) < 1e-10 for c in coefs.values()):
            print(f" CONFIRMED: All coefficients are essentially ZERO")
    elif all_equal_intercept and features_applied==0:
        print(f" NN_score equals intercept everywhere (no features contribution)")
        print(f" This means: no HP variables were selected OR all HP coefficients are zero")

    dsout['NN_score']=nn_score

    print(f"\n RBNN_scorecode OUTPUT for NN_score {dsout['NN_score']}")
    if 'NN_score' not in dsout.columns:
        # print(f" [RBNN scorecode]: WARNING: NN_score column missing, setting to 0")
        dsout['NN_score']=0


    # dsout.to_csv("dsout_with_NN_score_V.csv",index=False)
    # code_out.to_csv('code_out_with_NN_score_V.csv',index=False)
    # print(f"code_out value: {code_out}") # Removed
    # print(f"dsout detail: {dsout.describe()}") # Removed
    # print(f"RBNNN Score_code")
    return code_out,dsout


def glmselect_score_code(
    selected_features:List[str],
    coefs:Dict[str,float],
    intercept:float,
    stats: Dict[str,Dict], ###modified0629
    est_name:str,
    original_features: List[str]=None) -> pd.DataFrame:
    """
    Applies GLMSELECT-style scoring code to a DataFrame.

    This function executes code generated by GLMSELECT process to compute predictions or
    variable transformations on the provided DataFrame.
    """

    code_rows=[]
    num_parms=len(selected_features)+1
    original_features=original_features or []

    # add intercept row
    # modified0525
    if intercept is not None:
        end_symbol= '+' if len(selected_features) > 0 else ';'
        code_rows.append({
            'Effect': 'Intercept',
            'Parameter': 'Intercept',
            'Estimate':intercept,
            'DF':1,
            'New_var': est_name,
            'code':f"{est_name}={intercept:.5e}{end_symbol}", # modified0617
            'Alteryx_code':f"{intercept:.5e}{end_symbol}", # modified0617
            'Knot':0.0,
            'StandardizedEst':0.0,
            'StdErr':0.0,
            'tValue':0.0,
            'Probt':0.0,
            'index':0
        })


    for i, feature in enumerate(selected_features):
        is_last=(i==len(selected_features)-1)
        end_symbol=';' if is_last else '+'
        coef =coefs.get(feature,0)
        ### modified0629
        t_value = stats.get('tvalue',{}).get(feature,np.nan)
        p_value = stats.get('pvalue',{}).get(feature,np.nan)
        std_err = stats.get('stderr',{}).get(feature,np.nan)
        std_est = stats.get('stdest',{}).get(feature,np.nan)
        #################################
        
        is_dummy=False
        orig_col=None
        dummy_value=None

        for orig in original_features:
            if feature.startswith(orig + '_') and feature not in original_features:
                is_dummy=True
                orig_col=orig
                dummy_value=feature[len(orig)+1:]
                break
        if is_dummy and orig_col and dummy_value:
            try:
                dummy_value=int(dummy_value)
                effect=f"({orig_col}=={dummy_value})"
            except:
                effect=f"({orig_col}=='{dummy_value}')"

            code_expr=f"{coef:.5e} * {effect}{end_symbol}" # modified0617
        else:
            effect=feature.replace('*',' ')
            code_expr=f"{coef:.5e} * {effect}{end_symbol}" # modified0617

        # modified0525
        if (i==0) and (intercept is None):
            code_expr=f"{est_name} = " + code_expr

        code_rows.append({
            # Commented Out
            # 'Effect': effect if not is_dummy else f"{orig_col}_{dummy_value}",
            'Effect': effect if not is_dummy else f"{orig_col}",
            'Parameter': feature,
            'Estimate': coef,
            'DF':1,
            'New_var': est_name,
            #    'code':f"{coef:.10e} * {effect}{end_symbol}",
            'code': code_expr,
            'Alteryx_code':f"{coef:.5e} * [{feature}]{end_symbol}", # modified0617
            'Knot': np.nan, #modified0629
            'StandardizedEst':std_est, #modified0629
            'StdErr':std_err, #modified0629
            'tValue':t_value, #modified0629
            'Probt':p_value, #modified0629
            # 'index':i+1 # modified0525
            'index': i if intercept is None else i + 1
        })
    # print(f"\n glmselect_score_code code_rows:{code_rows}")
    return pd.DataFrame(code_rows)



def fix_cat(
        parm_df: pd.DataFrame,
        var: str,
        var_type: str):

    parm_df = parm_df.copy()

    for idx, row in parm_df.iterrows():
        effect = row.get('Effect', '')
        code = row.get('code', '')
        alteryx_code = row.get('Alteryx_code', '')
        var_value = row.get(var, None)

        if pd.isna(var_value):
            continue
        if effect == var:
            if var_type == 'Num':
                t_sub = f"({var}={var_value})"
                code = code.replace(var, t_sub)
                a_sub = f"IF [{var}]={var_value} THEN 1 ELSE 0 ENDIF"
                alteryx_code = alteryx_code.replace(var, a_sub)
            else:
                t_sub = f"({var}='{var_value}')"
                code = code.replace(var, t_sub)
                a_sub = f"IF [{var}]='{var_value}' THEN 1 ELSE 0 ENDIF"
                alteryx_code = alteryx_code.replace(f"[{var}]", a_sub)

        elif var in str(effect):
            if var_type == 'Num':
                t_sub = f'({var}={var_value})'
                code = code.replace(f"{var}", f"{t_sub}")
                a_sub = f"IF [{var}]={var_value} THEN 1 ELSE 0 ENDIF"
                alteryx_code = alteryx_code.replace(var, a_sub)
            else:
                t_sub = f"({var}='{var_value}')"
                code = code.replace(f"{var}", f"{t_sub}")
                a_sub = f"IF [{var}]='{var_value}' THEN 1 ELSE 0 ENDIF"
                alteryx_code = alteryx_code.replace(f"[{var}]", a_sub)
        parm_df.at[idx, 'code'] = code
        parm_df.at[idx, 'Alteryx_code'] = alteryx_code
    return parm_df


def Alteryx_code_out(
    all_code_in: pd.DataFrame,
    code_index: Optional[str] = None
) -> pd.DataFrame:
    keep_cols = ['Layer', 'Node', 'New_var', 'Alteryx_code']
    if code_index and code_index in all_code_in.columns:
        keep_cols = [code_index] + keep_cols

    keep_cols = [c for c in keep_cols if c in all_code_in.columns]

    if 'Alteryx_code' not in all_code_in.columns:
        return pd.DataFrame()

    aco_temp = all_code_in[keep_cols].copy()

    sort_cols = []
    if code_index and code_index in aco_temp.columns:
        sort_cols.append(code_index)
    sort_cols.extend(['Layer', 'Node'])
    aco_temp = aco_temp.sort_values(sort_cols).reset_index(drop=True)

    order_index = []
    current_order = 0
    prev_var = None
    prev_group = None

    for idx, row in aco_temp.iterrows():
        current_var = row.get('New_var', '')

        if code_index and code_index in aco_temp.columns:
            current_group = row[code_index]
            if prev_group is not None and current_group != prev_group:
                current_order = 1
                prev_var = current_var
            elif prev_var is None:
                current_order = 1
                prev_var = current_var
            elif current_var != prev_var:
                current_order += 1
                prev_var = current_var
            prev_group = current_group
        else:

            if prev_var is None:
                current_order = 1
                prev_var = current_var
            elif current_var != prev_var:
                current_order += 1
                prev_var = current_var

        order_index.append(current_order)

    aco_temp['order_index'] = order_index

    group_cols = ['order_index']
    if code_index and code_index in aco_temp.columns:
        group_cols = [code_index] + group_cols

    def concat_alteryx(group):
        all_code = ' '.join(group['Alteryx_code'].fillna('').astype(str).str.strip())
        result = {
            'Layer': group['Layer'].iloc[-1],
            'Node': group['Node'].iloc[-1],
            'New_var': group['New_var'].iloc[-1],
            'all_alteryx_code': all_code.strip()
        }
        if code_index and code_index in group.columns:
            result[code_index] = group[code_index].iloc[0]
        return pd.Series(result)

    alteryx_code_out = aco_temp.groupby(group_cols, sort=False).apply(
        concat_alteryx, include_groups=False
    ).reset_index(drop=True)

    final_cols = []

    if code_index and code_index in alteryx_code_out.columns:
        final_cols.append(code_index)
    final_cols.extend(['Layer', 'Node', 'New_var', 'all_alteryx_code'])
    final_cols = [c for c in final_cols if c in alteryx_code_out.columns]

    return alteryx_code_out[final_cols]


def _apply_score_code(df: pd.DataFrame, code_str: str) -> pd.DataFrame:
    """
    Applies generated scoring code to a DataFrame.

    This function executes model-generated code to compute predictions or derived variables
    on the provided DataFrame.
    """
    df = df.copy()
    print(f"[_apply_score_code] Starting with {len(df)} rows, {len(df.columns)} columns")

    # code_str=code_str.replace('\r\n',' ').replace('\n',' ').replace('\r',' ')
    # code_str=re.sub(r'\s+',' ',code_str)

    statements = [s.strip() for s in code_str.split(';') if s.strip()]
    print(f"[_apply_score_code] Found {len(statements)} statements to execute")

    # print(f"&&&&&&&& Normalize {statements}") # Removed

    valid_statements = []

    for stmt in statements:
        if not stmt or "=" not in stmt:
            continue
        if any(marker in stmt.lower() for marker in ['direction model','<-from','<from','placeholder']):
            print(f"[_apply_score_code] SKIPPING placeholder:{stmt[:80]}")
            continue
        valid_statements.append(stmt)

    print(f"[_apply_score_code] Valid statements after filtering : {len(valid_statements)}", flush=True)
    print(f"[_apply_score_code] DataFrame has : {len(df.columns)} columns. First 20: {list(df.columns)[:20]}", flush=True)

    executed_count = 0
    failed_count = 0

    for stmt_idx, stmt in enumerate(valid_statements):
        if "=" not in stmt:
            continue

        parts = stmt.split('=', 1)
        if len(parts) != 2:
            continue
        

        var_name = parts[0].strip()
        expression = parts[1].strip()

        if not var_name or not var_name.replace('_','').replace('0','').replace('1','').replace('2','').replace('3','').replace('4','').replace('5','').replace('6','').replace('7','').replace('8','').replace('9','').isalpha():
            print(f"[_apply_score_code] Skipping invalid variable name:'{var_name[:50]}'")
            failed_count += 1
            continue

        if var_name[0].isdigit() or var_name[0] in ['-','+','*','/','(',')']:
            print(f"[_apply_score_code] Skipping invalid variable name:(starts with {var_name[0]}): '{var_name[:50]}'")
            failed_count += 1
            continue

        try:
            py_expr = expression
            py_expr = re.sub(r'\bmin\s*\(\s*0\s*,', 'np.minimum(0,', py_expr)
            py_expr = re.sub(r'\bmax\s*\(\s*0\s*,', 'np.maximum(0,', py_expr)

            condition_pattern = r'\(([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)\s*["\']([^"\']+)["\']\)'
            conditions_found = 0

            def replace_condition(match):
                nonlocal conditions_found
                col_name = match.group(1)
                operator = match.group(2)
                value = match.group(3)
                if col_name in df.columns:
                    conditions_found += 1
                    return f"(df['{col_name}'].astype(str) {operator} '{value}').astype(float)"
                else:
                    return match.group(0)

            py_expr = re.sub(condition_pattern, replace_condition, py_expr)

            numeric_condition_pattern = r'\(([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)\s*(\d+)\)' # modified 1205
            numeric_conditions_found = 0




            def replace_numeric_condition(match):
                nonlocal numeric_conditions_found
                col_name = match.group(1)
                operator = match.group(2)
                value = match.group(3)
                if col_name in df.columns:
                    numeric_conditions_found += 1
                    return f"(df['{col_name}'].values {operator} {value}).astype(float)"
                else:
                    return match.group(0)

            py_expr = re.sub(numeric_condition_pattern, replace_numeric_condition, py_expr)

            if (conditions_found > 0 or numeric_conditions_found > 0) and stmt_idx < 5:
                print(f" [_apply_score_code] Statement #{stmt_idx+1} has {conditions_found} string, {numeric_conditions_found} numeric conditional(s)")

            tokens = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', py_expr)

            exclude = {'np','minimum','maximum','exp','log','abs','sqrt','sin','cos','df','astype','float','str'}

            # Modified
            # tokens_to_replace=[]
            # for col in df.columns:
            #     if re.search(r'(?<![A-Za-z0-9_])' + re.escape(col) + r'(?![A-Za-z0-9_])',py_expr):
            #         tokens_to_replace.append(col)

            # print(f"\n ************ DEBUG columns found in expr: {tokens_to_replace[:15]}")
            # tokens_to_replace.sort(key=len,reverse=True)

            # for token in tokens_to_replace:
            #     if f"df['{token}']" not in py_expr:
            #         pattern=r'(?<![A-Za-z0-9_])' + re.escape(token) + r'(?![A-Za-z0-9_])'
            #         py_expr=re.sub(pattern,f"df['{token}'].values",py_expr)

            for token in set(tokens):
                if token in exclude:
                    continue
                if token in df.columns:
                    if f"df['{token}']" not in py_expr:
                        py_expr = re.sub(rf'\b{token}\b', f"df['{token}'].values", py_expr)
            eval_globals = {'np': np}
            eval_locals = {'df': df}
            result = eval(py_expr, eval_globals, eval_locals)
            df[var_name] = result

            executed_count += 1
            # print(f" converted:{py_expr}")
            if stmt_idx < 3 or stmt_idx >= len(valid_statements)-3:
                
                result_summary = f"min={np.min(result):.4f}, max={np.max(result):.4f}" if hasattr(result, '__len__') else f"val={result}"
                print(f" [_apply_score_code] Executed #{stmt_idx+1}:{var_name} = ... ({result_summary})")

        except Exception as e:
            print(f" [_apply_score_code] Failed #{stmt_idx+1}:{var_name}")
            print(f" Original: {expression[:100]}")
            print(f" converted:{py_expr[:100]}")
            print(f" Error: {type(e).__name__}:{e}")

            df[var_name] = 0
            failed_count += 1

    print(f" [_apply_score_code] Summary:{executed_count} executed,{failed_count} failed")
    print(f" [_apply_score_code] NN_score in columns:{'NN_score' in df.columns}")

    return df

def stack_output(
        index_var: str,
        index_value: int,
        code_out: pd.DataFrame,
        dsin: pd.DataFrame,
        tracker: pd.DataFrame,
        code_stack: Optional[pd.DataFrame] = None,
        all_fit: Optional[pd.DataFrame] = None,
        fit_tracker: Optional[pd.DataFrame] = None,
        plot_stack: Optional[pd.DataFrame] = None,
        fit_sum: Optional[pd.DataFrame] = None
    ) -> Dict[str, pd.DataFrame]:

    from datetime import datetime

    if code_out is None:
        code_out = pd.DataFrame({
            'Layer': [],
            'Node': [],
            'Hyperplane_num': [],
            'New_var': [''],
            'Knot': [0.0],
            'Effect': [''],
            'Parameter': [''],
            'DF': [0],
            'Estimate': [0.0],
            'StandardizedEst': [0.0],
            'StdErr': [0.0],
            'tValue': [0.0],
            'Probt': [0.0],
            'index': [0],
            'code': ['']
        })
    elif not isinstance(code_out, pd.DataFrame):
        raise TypeError(f"code_out must be a DataFrame or None, got {type(code_out)}")

    if not isinstance(dsin, pd.DataFrame):
        raise TypeError(f"dsin must be a DataFrame , got {type(dsin)}")
    if not isinstance(tracker, pd.DataFrame):
        raise TypeError(f"tracker must be a DataFrame , got {type(tracker)}")
    
    if code_stack is None:
        code_stack = pd.DataFrame()
    if fit_tracker is None:
        fit_tracker = pd.DataFrame()
    if plot_stack is None:
        plot_stack = pd.DataFrame()
    if fit_sum is None:
        fit_sum = pd.DataFrame()
    if all_fit is None:
        all_fit = pd.DataFrame({
            '_NAME_': ['nValue1'], # Modify by Avanish
            'Layer': [0],
            'Node': [0],
            'N': [0],
            'Intercept': [0.0],
            'Root MSE': [0.0],
            'Dependent Mean': [0.0],
            'R-Square': [0.0],
            'Adj R-Sq': [0.0],
            'AIC': [0.0],
            'AICC': [0.0],
            'SBC': [0.0]
        })

    if isinstance(code_stack, list):
        code_stack = pd.DataFrame(code_stack) if len(code_stack) > 0 else pd.DataFrame()
    if isinstance(fit_tracker, list):
        fit_tracker = pd.DataFrame(fit_tracker) if len(fit_tracker) > 0 else pd.DataFrame()
    if isinstance(plot_stack, list):
        plot_stack = pd.DataFrame(plot_stack) if len(plot_stack) > 0 else pd.DataFrame()
    if isinstance(fit_sum, list):
        fit_sum = pd.DataFrame(fit_sum) if len(fit_sum) > 0 else pd.DataFrame()
    if isinstance(all_fit, list):
        all_fit = pd.DataFrame(all_fit) if len(all_fit) > 0 else pd.DataFrame({
            '_NAME_': ['nValue1'],
            'Layer': [0],
            'Node': [0],
            'N': [0],
            'Intercept': [0.0],
            'Root MSE': [0.0],
            'Dependent Mean': [0.0],
            'R-Square': [0.0],
            'Adj R-Sq': [0.0],
            'AIC': [0.0],
            'AICC': [0.0],
            'SBC': [0.0]
        })

    code_out = code_out.copy()
    code_out[index_var] = index_value

    if index_var in tracker.columns:
        tracker_dtype = tracker[index_var].dtype
        code_out[index_var] = code_out[index_var].astype(tracker_dtype)
        code_out = code_out.merge(tracker, on=index_var, how='left')

    code_out_valid = code_out[code_out[index_var] != -1].copy()

    if not isinstance(code_stack, pd.DataFrame):
        code_stack = pd.DataFrame(code_stack) if isinstance(code_stack, list) and len(code_stack) > 0 else pd.DataFrame()
    if not isinstance(code_out_valid, pd.DataFrame):
        code_out_valid = pd.DataFrame(code_out_valid) if isinstance(code_out_valid, list) and len(code_out_valid) > 0 else pd.DataFrame()

    code_stack = pd.concat([code_stack, code_out_valid], ignore_index=True)

    all_fit = all_fit.copy()
    all_fit[index_var] = index_value

    if index_var in tracker.columns:
        all_fit[index_var] = all_fit[index_var].astype(tracker_dtype)
        all_fit = all_fit.merge(tracker, on=index_var, how='left')

    all_fit_valid = all_fit[all_fit[index_var] != -1].copy()

    if not isinstance(fit_tracker, pd.DataFrame):
        fit_tracker = pd.DataFrame(fit_tracker) if isinstance(fit_tracker, list) and len(fit_tracker) > 0 else pd.DataFrame()
    if not isinstance(all_fit_valid, pd.DataFrame):
        all_fit_valid = pd.DataFrame(all_fit_valid) if isinstance(all_fit_valid, list) and len(all_fit_valid) > 0 else pd.DataFrame()

    fit_tracker = pd.concat([fit_tracker, all_fit_valid], ignore_index=True)

    print(f" [stack_output] Extracting score code from code_out (shape:{code_out.shape})")

    # Debug
    if 'code' in code_out.columns:
        print(f"[stack_output] code_out has 'code' column. len={len(code_out)}")
        for idx, row in code_out.head(5).iterrows():
            code_val = str(row.get('code','N/A'))
            layer_val = row.get('Layer','?')
            effect_val = row.get('Effect','?')
            truncated = code_val[:80]+'...' if len(code_val)>80 else code_val
            print(f" row{idx}:Layer={layer_val}, Effect={effect_val}, code='{truncated}' (len={len(code_val)})")
    else:
        print(f" [stack_output] ERROR: 'code' column not found in code_out")
        print(f" [stack_output] Available columns: {code_out.columns.tolist()}")

    scr_code1_df = code_out[(code_out[index_var]==index_value) & (code_out['Layer']==1)]
    scr_code2_df = code_out[(code_out[index_var]==index_value) & (code_out['Layer']>1)]

    print(f" [stack_output] Layer 1 code rows: {len(scr_code1_df)}, Layer>1 code row: {len(scr_code2_df)}")

    scr_code1_list = scr_code1_df['code'].dropna().astype(str).tolist() if 'code' in scr_code1_df.columns else []
    scr_code2_list = scr_code2_df['code'].dropna().astype(str).tolist() if 'code' in scr_code2_df.columns else []



    scr_code1_list = [c for c in scr_code1_list if c.strip()]
    scr_code2_list = [c for c in scr_code2_list if c.strip()]

    print(f" [DEBUG2]  type(scr_code1_list): {type(scr_code1_list)}")
    print(f" [DEBUG2]  scr_code1_list first 3: {scr_code1_list[:3]}")
    print(f" [DEBUG2]  scr_code1_df shape : {scr_code1_df.shape}")
    print(f" [DEBUG2]  'code' in scr_code1_df.columns: {'code' in scr_code1_df.columns}")

    scr_code1 = ' '.join(scr_code1_list)
    scr_code2 = ' '.join(scr_code2_list)

    print(f" [DEBUG] scr_code1 first 300 chars: {scr_code1[:300]!r}")
    # print(f" [DEBUG] scr_code1 first 300 chars: {scr_code1}")
    print(f" [DEBUG] scr_code2 first 300 chars: {scr_code2[:300]!r}")
    # print(f" [DEBUG] scr_code2 first 300 chars: {scr_code2}")
    
    print(f" [stack_output] Non-empty code pieces: Layer 1= {len(scr_code1)} chars, Layer >=1={len(scr_code2)} chars")

    plot_out = dsin.copy()
    # print(f"PLOT_OUT as DSIN in STACK OUTPUT {plot_out.head(5)}")

    if index_var in tracker.columns and index_var in plot_out.columns:
        if plot_out[index_var].dtype != tracker[index_var].dtype:
            plot_out[index_var] = plot_out[index_var].astype(tracker[index_var].dtype)
        plot_out = plot_out.merge(tracker, on=index_var, how='left')

    all_scr_code = scr_code1 + ' ' + scr_code2

    if all_scr_code.strip():
        import re

        rename_map = {}
        for col in plot_out.columns:
            # if re.match(r'^(HP|PP)\d+_\d+$',col): # modified
            if re.match(r'^[HP]*PP0*\d+_0*\d+$',col):
                match = re.search(r'PP0*(\d+)_0*(\d+)$',col) #Added by Avanish
                # prefix=col[:2]
                # rest=col[2:]
                # parts=rest.split('_')
                # if len(parts)==2:
                #     layer=parts[0].lstrip('0') or '0'
                #     node=parts[1].lstrip('0') or '0'
                #     new_name=f"{prefix}{layer}_{node}"
                #     rename_map[col]=new_name
                #     print(f"\n [stack output] Column rename: {col}--{new_name}")
                if match:
                    layer = match.group(1)
                    node = match.group(2)
                    new_name = f"PP{layer}_{node}"
                    rename_map[col] = new_name
                    print(f"\n [Stack_Output] column rename: {col}--{new_name}")

        if rename_map:
            plot_out = plot_out.rename(columns=rename_map)


        normalized_code = all_scr_code


        # print(f"\n ##### DEBUG CODE BEFORE NORMALIZATION") # Removed
        # print(f"\n {all_scr_code[:300]}")

        # var_pattern=r'(HP|PP)\d+_\d+' # modified Avanish
        var_pattern=r'\b[HP]*PP0*(\d+)_0*(\d+)\b'

        def normalize_var(match):
            # full_match=match.group(0) # Modified Avanish
            # prefix=match.group(1)
            # rest=full_match[2:]
            # parts=rest.split('_')
            # layer=parts[0].lstrip('0') or '0'
            # node=parts[1].lstrip('0') or '0'
            layer = match.group(1).lstrip('0') or '0'
            node = match.group(2).lstrip('0') or '0'

            # return f"{prefix}{layer}_{node}"
            return f"PP{layer}_{node}"

            # test_matches=re.findall(var_pattern,all_scr_code)
            # print(f"\n DEBUG var_pattern matches (prefix only): {test_matches[:10]}")
            # full_matches=list(re.finditer(var_pattern,all_scr_code))[:5]
            # print(f" DEBUG full matches:{full_matches}")

        normalized_code = re.sub(var_pattern, normalize_var, normalized_code)

        # print(f"\n ##### DEBUG CODE AFTER NORMALIZATION") # removed
        # print(f"\n {normalized_code[:300]}")

        # plot_out.to_csv("plot_out_before.csv",index=False) # Removed

        plot_out = _apply_score_code(plot_out, normalized_code)

        # plot_out.to_csv("plot_out_after.csv",index=False) # Removed

        print(f" PLOT_OUT AFTER APPLY SCORE CODE : {plot_out.head(5)}")

        print("NN_score in plot_out:","NN_score" in plot_out.columns)
        print("plot_out cols: ", [c for c in plot_out.columns if c in ['NN_score','Pred_Prct','logit_resid']])


        rbnn_vars_created = [c for c in plot_out.columns if c.startswith(('PP','HP','NN_'))]



        if 'NN_score' in plot_out.columns:
            nn_stats = plot_out['NN_score'].describe()
            if nn_stats['max'] == 0 and nn_stats['min'] == 0:
                print(f" [WARNING] : All NN_score values are ZERO! ")
        else:
            print(f" NN_score not found after applying code!")
    else:
        print(f" WARNING: No score code generated!")

    if 'tran_dt' in plot_out.columns:
        plot_out['year'] = pd.to_datetime(plot_out['tran_dt']).dt.year
        plot_out['month'] = pd.to_datetime(plot_out['tran_dt']).dt.month

    if 'NN_score' in plot_out.columns:
        plot_out['Pred_Prct'] = np.where(
            plot_out['NN_score'] >= -12.5,
            1/(1+np.exp(-plot_out['NN_score'])), 0
        )

        plot_out['Log_Pred_Prct'] = np.where(
            plot_out['NN_score'] >= -12.5,
            np.log(plot_out['Pred_Prct'].clip(lower=1e-15)), -15
        )
        plot_out['NN_score'] = np.where(
            (plot_out['NN_score'] < -12.5) &
            (plot_out['NN_score'].notna()), -15, plot_out['NN_score']
        )
    else:
        print(f" [NN_score not found in plot_out! Cannot create Pred_Prct.")

    if 'logit' in plot_out.columns and 'NN_score' in plot_out.columns:
        plot_out['logit_resid'] = plot_out['NN_score'] - plot_out['logit']
        plot_out['logit_APE'] = np.abs(plot_out['logit_resid'])/plot_out['logit'].replace(0, np.nan)

    # print(f"\n Plot_out columns :{plot_out.columns.tolist()}")




    if 'Daily_vol' in plot_out.columns and 'PercentVol' in plot_out.columns and 'Pred_Prct' in plot_out.columns:
        plot_out['Prct_resid'] = np.where(
            plot_out['Daily_vol'] > 0,
            plot_out['Pred_Prct'] - plot_out['PercentVol'],
            np.where(plot_out['logit'].notna() if 'logit' in plot_out.columns else True,
                plot_out['Pred_Prct'], np.nan
            )
        )
        plot_out['Abs_Prct_resid'] = np.abs(plot_out['Prct_resid'])

    # print(f"\n Plot_out columns AFTER TRAIN:{plot_out[plot_out['train']==0]}")

    sort_cols = []
    if 'DND_NB' in plot_out.columns:
        sort_cols.append('DND_NB')
    if 'year' in plot_out.columns:
        sort_cols.append('year')
    if 'month' in plot_out.columns:
        sort_cols.append('month')
    if sort_cols:
        plot_out = plot_out.sort_values(sort_cols).reset_index(drop=True)

    if all(c in plot_out.columns for c in ['DND_NB', 'year', 'month', 'Pred_Prct']):
        monthly_tot = plot_out.groupby(['DND_NB', 'year', 'month'])['Pred_Prct'].transform('sum')
        plot_out['Pred_Prct'] = np.where(
            monthly_tot > 0,
            plot_out['Pred_Prct'] / monthly_tot,
            plot_out['Pred_Prct']
        )

        if 'Daily_vol' in plot_out.columns and 'PercentVol' in plot_out.columns:
            plot_out['Prct_resid'] = np.where(
                plot_out['Daily_vol'] > 0,
                plot_out['Pred_Prct'] - plot_out['PercentVol'],
                np.where(plot_out['logit'].notna() if 'logit' in plot_out.columns else True,
                    plot_out['Pred_Prct'], np.nan
                )
            )
            plot_out['Abs_Prct_resid'] = np.abs(plot_out['Prct_resid'])
    stat_dfs = []
    if 'train' in plot_out.columns and 'Abs_Prct_resid' in plot_out.columns:
        for train_val in [0,1]:
            subset = plot_out[plot_out['train']==train_val] #modified 1405
            if 'Abs_Prct_resid' in subset.columns:
                valid_subset = subset[subset['Abs_Prct_resid'].notna()]
                n_count = len(valid_subset)
            else:
                n_count = len(subset)
            if len(subset) > 0:
                stat_row = {
                    index_var: index_value,
                    'train': train_val,
                    'n': n_count,
                    'Prct_MAE': subset['Abs_Prct_resid'].mean() if 'Abs_Prct_resid' in subset.columns else np.nan,
                    'Abs_Prct_p90': subset['Abs_Prct_resid'].quantile(0.90) if 'Abs_Prct_resid' in subset.columns else np.nan,
                    'Abs_Prct_p95': subset['Abs_Prct_resid'].quantile(0.95) if 'Abs_Prct_resid' in subset.columns else np.nan,
                    'Abs_Prct_p99': subset['Abs_Prct_resid'].quantile(0.99) if 'Abs_Prct_resid' in subset.columns else np.nan,
                }
                if 'logit_APE' in subset.columns:
                    stat_row['Logit_MAPE'] = subset['logit_APE'].mean()
                if 'PercentVol' in subset.columns:
                    # num_mo=subset['PercentVol'].count()
                    num_mo = (subset['PercentVol']!=0).sum()
                    stat_row['WMAPE'] = subset[subset['PercentVol']!=0]['Abs_Prct_resid'].sum()/num_mo if num_mo > 0 else np.nan
                stat_dfs.append(stat_row)

    stat = pd.DataFrame(stat_dfs) if stat_dfs else pd.DataFrame()

    code_out_valid = code_out[code_out['Layer']!=9999]
    # print(f"\n ****************code_out_valid {code_out_valid.head(2)}") # Removed
    # print(f"\n ************stat {stat.head(2)}") # shape(2,9)
    if len(code_out_valid) > 0:
        netsize = pd.DataFrame({
            index_var: [index_value],
            'layers': [code_out_valid['Layer'].max()],
            'max_num_nodes': [code_out_valid['Node'].max()],
            'num_presum_parms': [code_out_valid['DF'].sum() if 'DF' in code_out_valid.columns else 0]
        })
    else:
        netsize = pd.DataFrame({index_var: [index_value], 'layers':[0],'max_num_nodes':[0],'num_presum_parms':[0]})

    fit_out = tracker[tracker[index_var]==index_value].copy() if index_var in tracker.columns else pd.DataFrame({index_var:[index_value]})

    # print(f"\n ****************netsize  {netsize.head(2)}") # Removed
    # print(f"\n ****************fit_out BEFORE MERGE  {fit_out.shape}") # Empty

    fit_out = fit_out.merge(netsize,on=index_var,how='left')

    # print(f"\n ****************fit_out BEFORE AFTER  {fit_out.shape}") # Empty # Removed
    if len(stat) >0:
        stat_train = stat[stat['train']==1].drop(columns=['train']).copy()
        stat_train.columns = [c if c==index_var else f'{c}_train' for c in stat_train.columns]
        if len(stat_train)>0:
            fit_out = fit_out.merge(stat_train,on=index_var,how='left')

        stat_val = stat[stat['train']==0].drop(columns=['train']).copy()
        stat_val.columns = [c if c==index_var else f'{c}_val' for c in stat_val.columns]
        # print(f"################ stat_val {stat_val.head(5)}") # Removed
        if len(stat_val)>0:
            fit_out = fit_out.merge(stat_val,on=index_var,how='left')

    plot_out_valid = plot_out[plot_out[index_var]!=-1] if index_var in plot_out.columns else plot_out
    # print(f"######################## plot_out_valid {plot_out_valid.columns.tolist()}") # Removed
    # print(f"######################## fit_out {fit_out.head(5)}") # Removed

    essential_cols = []
    base_cols=[index_var, 'queue','tran_dt','start_date','Daily_vol','Monthly_vol','PercentVol',
            'logit','train','extra','year','month','DOW','SS_CAT','Neha_holiday']
    for col in base_cols:
        if col in plot_out_valid.columns:
            essential_cols.append(col)

    output_cols=['NN_score','Pred_Prct','Log_Pred_Prct','logit_resid','logit_APE','Prct_resid','Abs_Prct_resid']
    for col in output_cols:
        if col in plot_out_valid.columns:
            essential_cols.append(col)

    essential_cols=list(dict.fromkeys(essential_cols))

    # print(f" [stack_output] Selecting {len(essential_cols)} essential columns for plot_stack (out of {len(plot_out_valid.columns)} total)")
    plot_out_filtered = plot_out_valid[essential_cols].copy() if essential_cols else plot_out_valid.copy()

    if not isinstance(plot_stack, pd.DataFrame):
        plot_stack = pd.DataFrame(plot_stack) if isinstance(plot_stack, list) and len(plot_stack) > 0 else pd.DataFrame()

    plot_stack = pd.concat([plot_stack, plot_out_filtered], ignore_index=True)

    fit_out_valid = fit_out[fit_out[index_var]!=-1] if index_var in fit_out.columns else fit_out

    if not isinstance(fit_sum, pd.DataFrame):
        fit_sum = pd.DataFrame(fit_sum) if isinstance(fit_sum, list) and len(fit_sum) > 0 else pd.DataFrame()
    if not isinstance(fit_out_valid, pd.DataFrame):
        fit_out_valid = pd.DataFrame(fit_out_valid) if isinstance(fit_out_valid, list) and len(fit_out_valid) > 0 else pd.DataFrame()

    fit_sum = pd.concat([fit_sum, fit_out_valid], ignore_index=True)
    # print(f" fit_out_valid STACK **************** {fit_out_valid.head(5)}") # Empty # Removed
    # print(f" FIT_SUM STACK **************** {fit_sum.head(5)}") # Empty # Removed

    return {
        'code_out': code_out,
        'code_stack': code_stack,
        'all_fit': all_fit,
        'fit_tracker': fit_tracker,
        'plot_out': plot_out,
        'plot_stack': plot_stack,
        'fit_out': fit_out,
        'fit_sum': fit_sum
    }