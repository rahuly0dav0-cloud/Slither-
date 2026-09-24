/*======================================================================
  SAS ORACLE #07  --  dummy data for sample 07
  (large ~1000-line feature pipeline)

  Reproducing all ~60 feature tables of the large sample as ground truth
  is impractical, so this oracle focuses on what the sample actually needs
  to run: it DETERMINISTICALLY generates the single wide input table
  demo.raw_accounts (500 rows, 20 numeric columns) and exports it to CSV,
  plus a representative baseline (base_clean + segment_summary) for a QC
  smoke check.

  Feed raw_accounts.csv to the converter as the input for
  samples/sas/07_large_feature_pipeline.sas.

  Set OUTDIR first:  %let outdir = /tmp/sas_oracle/07;
======================================================================*/
%let outdir = /tmp/sas_oracle/07;
%let n_rows = 500;

libname demo (work);

/* ---- deterministic synthetic input (no random seed drift) ------------- */
data demo.raw_accounts;
    do account_id = 1 to &n_rows;
        income           = 20000 + mod(account_id * 137, 200000);
        balance          = mod(account_id * 91, 40000);
        credit_score     = 580 + mod(account_id * 7, 270);
        age              = 18 + mod(account_id * 3, 60);
        tenure_months    = mod(account_id * 5, 120);
        num_products     = mod(account_id, 6);
        num_logins       = mod(account_id * 2, 300);
        num_calls        = mod(account_id, 8);
        num_complaints   = mod(account_id, 4);
        days_since_active= mod(account_id * 11, 365);
        utilization      = mod(account_id * 13, 100) / 100;
        late_payments    = mod(account_id, 5);
        avg_txn_amt      = 20 + mod(account_id * 17, 4000);
        max_txn_amt      = avg_txn_amt + mod(account_id * 19, 8000);
        min_txn_amt      = mod(account_id, 50);
        num_txns         = mod(account_id * 3, 400);
        savings_balance  = mod(account_id * 23, 80000);
        loan_balance     = mod(account_id * 29, 100000);
        interest_rate    = 0.03 + mod(account_id, 15) / 100;
        discount_rate    = 0.01 + mod(account_id, 8) / 100;
        /* sprinkle a few missings to exercise the clean step */
        if mod(account_id, 50) = 0 then income = .;
        if mod(account_id, 60) = 0 then credit_score = .;
        output;
    end;
run;

/* ---- representative baseline slice ------------------------------------ */
data demo.base_clean;
    set demo.raw_accounts;
    if missing(account_id) then delete;
    array all income balance credit_score age tenure_months num_products
              num_logins num_calls num_complaints days_since_active utilization
              late_payments avg_txn_amt max_txn_amt min_txn_amt num_txns
              savings_balance loan_balance interest_rate discount_rate;
    do over all;
        if missing(all) then all = 0;
    end;
    length segment $10;
    if credit_score >= 750 then segment = 'PRIME';
    else if credit_score >= 640 then segment = 'NEAR';
    else segment = 'SUB';
run;

proc means data=demo.base_clean noprint;
    class segment;
    var income balance credit_score utilization num_txns;
    output out=demo.segment_summary
        mean(income)=avg_income
        mean(balance)=avg_balance
        mean(credit_score)=avg_score
        mean(utilization)=avg_util
        n(account_id)=n_accounts;
run;

%macro dump(ds); proc export data=demo.&ds outfile="&outdir/&ds..csv" dbms=csv replace; run; %mend;
%dump(raw_accounts);
%dump(base_clean);
%dump(segment_summary);
