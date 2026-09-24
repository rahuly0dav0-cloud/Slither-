/*======================================================================
  SAS ORACLE #03  --  ground-truth generator for sample 03
  (end-to-end: data prep -> merge -> means -> GLMSELECT lasso + stepwise)

  WHAT THIS DOES
  --------------
  1. Recreates the two raw input tables INLINE, so this program is fully
     self-contained and runnable as-is.
  2. Runs the EXACT same pipeline as
     SAS2PY/samples/sas/03_end_to_end_glmselect.sas
  3. Exports every input, intermediate, and final table to CSV.

  IMPORTANT -- DETERMINISM
  ------------------------
  The lasso step now uses DETERMINISTIC block folds (cvmethod=block(5))
  and the stepwise step is criterion-based (select=sl), so both
  lasso_output and stepwise_output are reproducible run-to-run. Note that
  SAS's LASSO path may still differ algorithmically from scikit-learn, so
  compare on prediction correlation / tolerance rather than expecting an
  exact cell match. The always-exact QC targets remain the deterministic
  tables: model_population, activity_prep, model_data, and model_summary.

  BEFORE RUNNING
  --------------
  Set OUTDIR to a folder that already exists on the SAS machine.
    * Unix/Linux : %let outdir = /tmp/sas_oracle/03;
    * Windows    : %let outdir = C:\temp\sas_oracle\03;
  (Create the folder first; SAS will not create it for you.)
======================================================================*/

%let outdir = /tmp/sas_oracle/03;

libname demo (work);

/*----------------------------------------------------------------------
  RAW INPUT #1 : demo.raw_customers  (1,000 synthetic rows, seeded)
    Generated with a fixed seed so the run is reproducible. churn_flag is
    driven by a few real predictors (credit_score, income, num_products,
    balance) plus noise, so the LASSO has genuine signal to select rather
    than collapsing to the intercept-only (null) model.
    A little missingness is injected to still exercise the pipeline's
    default / missing-value logic:
      - missing credit_score  -> if missing then 650
      - missing num_products  -> if missing then 0
      - missing balance/income-> coalesce / missing handling
      - missing churn_flag    -> target = . -> dropped by  if target ne .
----------------------------------------------------------------------*/
data demo.raw_customers;
    call streaminit(20250915);
    length state $10;
    format date_of_birth customer_since date9.;
    array _st[5] $10 _temporary_ ('NY' 'CA' 'TX' 'WA' 'FL');
    do customer_id = 1 to 1000;
        _age = 25 + floor(rand('uniform') * 45);                 /* 25..69 */
        date_of_birth  = intnx('year',  '31DEC2025'd, -_age,    'same');
        _tenure = floor(rand('uniform') * 240);                  /* 0..239 months */
        customer_since = intnx('month', '31DEC2025'd, -_tenure, 'same');
        annual_income = round(max(0, 40000 + 30000 * rand('normal')));
        credit_score  = round(min(850, max(500, 650 + 60 * rand('normal'))));
        num_products  = 1 + floor(rand('uniform') * 6);          /* 1..6 */
        balance       = round(max(0, 15000 + 12000 * rand('normal')));
        state = _st[1 + floor(rand('uniform') * 5)];

        /* true churn propensity: a few real drivers + noise */
        _lin = 0.50
             - 0.006    * (credit_score  - 650)
             - 0.000012 * (annual_income - 40000)
             + 0.30     * (num_products  - 3)
             - 0.000015 * (balance       - 15000)
             + 0.40     * rand('normal');
        churn_flag = (_lin > 0);

        /* modest missingness to keep the default/missing logic exercised */
        if rand('uniform') < 0.03 then credit_score  = .;
        if rand('uniform') < 0.03 then num_products  = .;
        if rand('uniform') < 0.03 then balance       = .;
        if rand('uniform') < 0.03 then annual_income = .;
        if rand('uniform') < 0.02 then churn_flag    = .;        /* -> target=. -> dropped */

        output;
    end;
    keep customer_id date_of_birth annual_income customer_since
         credit_score num_products balance churn_flag state;
run;

/*----------------------------------------------------------------------
  RAW INPUT #2 : demo.raw_activity  (seeded)
    Activity for customers 1..980 (ids 981..1000 have no activity and are
    dropped by the merge  if a and b), plus a few activity-only ids
    1001..1015 that have no master row (also dropped by the merge).
----------------------------------------------------------------------*/
data demo.raw_activity;
    call streaminit(778899);
    do customer_id = 1 to 980;
        login_count       = floor(rand('uniform') * 100);
        transaction_count = floor(rand('uniform') * 60);
        support_calls     = floor(rand('uniform') * 7);
        spend_m1 = round(max(0, 500 + 400 * rand('normal')));
        spend_m2 = round(max(0, 500 + 400 * rand('normal')));
        spend_m3 = round(max(0, 500 + 400 * rand('normal')));
        spend_m4 = round(max(0, 500 + 400 * rand('normal')));
        spend_m5 = round(max(0, 500 + 400 * rand('normal')));
        spend_m6 = round(max(0, 500 + 400 * rand('normal')));
        output;
    end;
    do customer_id = 1001 to 1015;                 /* no master row -> dropped */
        login_count = 10; transaction_count = 5; support_calls = 1;
        spend_m1 = 100; spend_m2 = 100; spend_m3 = 100;
        spend_m4 = 100; spend_m5 = 100; spend_m6 = 100;
        output;
    end;
    keep customer_id login_count transaction_count support_calls
         spend_m1 spend_m2 spend_m3 spend_m4 spend_m5 spend_m6;
run;

/*======================================================================
  PIPELINE  --  identical to sample 03
======================================================================*/
data demo.model_population;
    set demo.raw_customers;
    if missing(customer_id) then delete;
    age = intck('year', date_of_birth, '31DEC2025'd);
    income = coalesce(annual_income, 0);
    tenure_months = max(0, intck('month', customer_since, '31DEC2025'd));
    if missing(credit_score) then credit_score = 650;
    if missing(num_products) then num_products = 0;
    if missing(balance) then balance = 0;
    log_income = log(max(income, 1));
    log_balance = log(max(balance, 1));
    if churn_flag in (0,1) then target = churn_flag;
    else target = .;
    keep customer_id target age income tenure_months credit_score num_products balance log_income log_balance state;
run;

data demo.activity_prep;
    set demo.raw_activity;
    if missing(customer_id) then delete;
    total_activity = sum(login_count, transaction_count, support_calls);
    avg_monthly_spend = mean(of spend_m1-spend_m6);
    active_months = sum((spend_m1 > 0),(spend_m2 > 0),(spend_m3 > 0),(spend_m4 > 0),(spend_m5 > 0),(spend_m6 > 0));
    keep customer_id total_activity avg_monthly_spend active_months;
run;

proc sort data=demo.model_population;
    by customer_id;
run;

proc sort data=demo.activity_prep;
    by customer_id;
run;

data demo.model_data;
    merge demo.model_population(in=a) demo.activity_prep(in=b);
    by customer_id;
    if a and b;
    if missing(total_activity) then total_activity = 0;
    if missing(avg_monthly_spend) then avg_monthly_spend = 0;
    if missing(active_months) then active_months = 0;
    high_activity = (total_activity >= 20);
    high_spend = (avg_monthly_spend >= 1000);
    interaction_income_age = income * age;
    if target ne .;
run;

proc means data=demo.model_data n mean std min p25 median p75 max noprint;
    var target age income tenure_months credit_score num_products balance total_activity avg_monthly_spend active_months;
    output out=demo.model_summary;
run;

proc glmselect data=demo.model_data plots=none;
    model target = age income tenure_months credit_score num_products balance log_income log_balance total_activity avg_monthly_spend active_months high_activity high_spend interaction_income_age
        / selection=lasso choose=cv cvmethod=block(5);
    output out=demo.lasso_output p=predicted_lasso r=residual_lasso;
run;

proc glmselect data=demo.model_data plots=none;
    model target = age income tenure_months credit_score num_products balance log_income log_balance total_activity avg_monthly_spend active_months high_activity high_spend interaction_income_age
        / selection=stepwise select=sl slentry=0.05 slstay=0.05;
    output out=demo.stepwise_output p=predicted_stepwise r=residual_stepwise;
run;

/*======================================================================
  EXPORT  --  one CSV per table (these are the QC baselines)
======================================================================*/
%macro dump(ds);
    proc export data=demo.&ds
        outfile="&outdir/&ds..csv"
        dbms=csv replace;
    run;
%mend dump;

%dump(raw_customers);
%dump(raw_activity);
%dump(model_population);
%dump(activity_prep);
%dump(model_data);
%dump(model_summary);
%dump(lasso_output);
%dump(stepwise_output);

%put NOTE: Oracle #03 CSVs written to &outdir;
