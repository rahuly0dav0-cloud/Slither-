/* SAMPLE 06 - TRANSPOSE / ARRAYS / RETAIN / BY-GROUP
   Edge cases for the converter:
     - PROC TRANSPOSE from long -> wide (monthly spend to spend_m1..spend_m12)
     - ARRAY over the transposed columns with a DO loop
     - RETAIN + FIRST./LAST. for a running (cumulative) total per customer
     - PROC FORMAT + a user format applied in a later step
*/
libname demo "/prototype/data";

proc format;
    value spendband
        low   -<  100 = 'LOW'
        100   -<  500 = 'MEDIUM'
        500   - high  = 'HIGH';
run;

/* long -> wide: one row per customer, one column per month ------------- */
proc sort data=demo.raw_monthly_spend;
    by customer_id month_no;
run;

proc transpose data=demo.raw_monthly_spend
               out=demo.spend_wide(drop=_name_)
               prefix=spend_m;
    by customer_id;
    id month_no;
    var spend_amount;
run;

/* array pass: clean missings, total, average, count of active months --- */
data demo.spend_features;
    set demo.spend_wide;
    array m {12} spend_m1-spend_m12;
    total_spend = 0;
    active_months = 0;
    do i = 1 to 12;
        if missing(m{i}) then m{i} = 0;
        total_spend = total_spend + m{i};
        if m{i} > 0 then active_months = active_months + 1;
    end;
    avg_spend = divide(total_spend, max(active_months, 1));
    spend_band = put(avg_spend, spendband.);
    drop i;
run;

/* by-group running total using RETAIN + FIRST./LAST. ------------------- */
proc sort data=demo.raw_transactions;
    by customer_id transaction_date;
run;

data demo.txn_running;
    set demo.raw_transactions;
    by customer_id;
    retain running_total txn_seq;
    if first.customer_id then do;
        running_total = 0;
        txn_seq = 0;
    end;
    txn_seq + 1;
    running_total = running_total + amount;
    if last.customer_id then final_flag = 1;
    else final_flag = 0;
run;

/* keep just the closing balance row per customer ----------------------- */
data demo.customer_balance;
    set demo.txn_running;
    by customer_id;
    if last.customer_id;
    keep customer_id txn_seq running_total;
    rename running_total = closing_balance txn_seq = n_transactions;
run;

/* join the two feature sets ------------------------------------------- */
proc sort data=demo.spend_features; by customer_id; run;
proc sort data=demo.customer_balance; by customer_id; run;

data demo.customer_profile;
    merge demo.spend_features(in=a) demo.customer_balance(in=b);
    by customer_id;
    if a;
    if missing(closing_balance) then closing_balance = 0;
    if missing(n_transactions) then n_transactions = 0;
run;
