/*======================================================================
  SAS ORACLE #06  --  dummy data + ground truth for sample 06
  (PROC TRANSPOSE / ARRAY / RETAIN / BY-group)

  Self-contained: inlines demo.raw_monthly_spend and demo.raw_transactions,
  runs the SAME pipeline as samples/sas/06_transpose_arrays_retain.sas,
  and exports the final profile.

  Set OUTDIR first:  %let outdir = /tmp/sas_oracle/06;
======================================================================*/
%let outdir = /tmp/sas_oracle/06;

libname demo (work);

proc format;
    value spendband
        low   -<  100 = 'LOW'
        100   -<  500 = 'MEDIUM'
        500   - high  = 'HIGH';
run;

/* long monthly spend: a few customers, some months missing --------------- */
data demo.raw_monthly_spend;
    infile datalines dsd truncover;
    input customer_id month_no spend_amount;
    datalines;
1,1,120
1,2,80
1,4,300
2,1,50
2,2,60
2,3,70
3,6,900
3,7,50
;
run;

data demo.raw_transactions;
    infile datalines dsd truncover;
    input customer_id transaction_date :date9. amount;
    format transaction_date date9.;
    datalines;
1,05JAN2025,120
1,10JAN2025,-40
1,20FEB2025,300
2,03JAN2025,50
2,15JAN2025,60
2,01MAR2025,70
3,10JUN2025,900
3,15JUL2025,50
;
run;

proc sort data=demo.raw_monthly_spend; by customer_id month_no; run;

proc transpose data=demo.raw_monthly_spend out=demo.spend_wide(drop=_name_) prefix=spend_m;
    by customer_id;
    id month_no;
    var spend_amount;
run;

data demo.spend_features;
    set demo.spend_wide;
    array m {12} spend_m1-spend_m12;
    total_spend = 0; active_months = 0;
    do i = 1 to 12;
        if missing(m{i}) then m{i} = 0;
        total_spend = total_spend + m{i};
        if m{i} > 0 then active_months = active_months + 1;
    end;
    avg_spend = divide(total_spend, max(active_months, 1));
    spend_band = put(avg_spend, spendband.);
    drop i;
run;

proc sort data=demo.raw_transactions; by customer_id transaction_date; run;

data demo.txn_running;
    set demo.raw_transactions;
    by customer_id;
    retain running_total txn_seq;
    if first.customer_id then do; running_total = 0; txn_seq = 0; end;
    txn_seq + 1;
    running_total = running_total + amount;
    if last.customer_id then final_flag = 1; else final_flag = 0;
run;

data demo.customer_balance;
    set demo.txn_running;
    by customer_id;
    if last.customer_id;
    keep customer_id txn_seq running_total;
    rename running_total = closing_balance txn_seq = n_transactions;
run;

proc sort data=demo.spend_features; by customer_id; run;
proc sort data=demo.customer_balance; by customer_id; run;

data demo.customer_profile;
    merge demo.spend_features(in=a) demo.customer_balance(in=b);
    by customer_id;
    if a;
    if missing(closing_balance) then closing_balance = 0;
    if missing(n_transactions) then n_transactions = 0;
run;

%macro dump(ds); proc export data=demo.&ds outfile="&outdir/&ds..csv" dbms=csv replace; run; %mend;
%dump(spend_features);
%dump(customer_balance);
%dump(customer_profile);
