/*======================================================================
  SAS ORACLE #02  --  ground-truth generator for sample 02
  (complex data engineering: prep -> merge -> means -> customer level)

  WHAT THIS DOES
  --------------
  1. Recreates the two raw input tables INLINE, so this program is fully
     self-contained and runnable as-is.
  2. Runs the EXACT same pipeline as
     SAS2PY/samples/sas/02_data_engineering_complex.sas
  3. Exports every input, intermediate, and final table to CSV.

  The CSVs are the QC ground-truth baselines: run this in SAS, then send
  the CSVs back so the Python conversion can be compared against them.

  NOTE ON A FAITHFUL SAS QUIRK (not a bug):
    In customer_prep, income_band is first assigned 'HIGH' (4 chars), so
    its SAS length is $4. When the merge sets income_band = 'UNKNOWN' for
    an account with no matching customer, SAS truncates it to 'UNK'. The
    ground truth reflects this on purpose -- a faithful Python conversion
    must reproduce the same truncation.

  BEFORE RUNNING
  --------------
  Set OUTDIR to a per-sample folder that already exists on the SAS machine.
  Use a SEPARATE folder per oracle -- all three write a raw_customers.csv
  with different columns, so they must not share one directory.
    * Unix/Linux : %let outdir = /tmp/sas_oracle/02;
    * Windows    : %let outdir = C:\temp\sas_oracle\02;
======================================================================*/

%let outdir = /tmp/sas_oracle/02;

libname demo (work);

/*----------------------------------------------------------------------
  RAW INPUT #1 : demo.raw_accounts
    - row with empty account_id     -> exercises  if missing(account_id) delete
    - row with empty current_balance-> exercises  coalesce(current_balance, 0)
    - row with empty credit_limit   -> exercises  divide(balance, 0) = missing
    - account for customer 99        -> exercises the merge cust=0 branch
----------------------------------------------------------------------*/
data demo.raw_accounts;
    infile datalines dsd truncover;
    length account_status $10;
    input customer_id account_id current_balance credit_limit account_status $ open_date :date9.;
    format open_date date9.;
datalines;
1,1001,9500,10000,ACTIVE,15JAN2020
1,1002,3000,5000,ACTIVE,10FEB2021
2,1003,50000,100000,INACTIVE,05MAR2019
3,1004,,8000,ACTIVE,20JUN2022
4,1005,5000,,ACTIVE,01JUL2023
99,1006,2000,4000,ACTIVE,12DEC2023
2,,1500,3000,ACTIVE,03MAR2020
;
run;

/*----------------------------------------------------------------------
  RAW INPUT #2 : demo.raw_customers
    - row with empty customer_id  -> exercises  if missing(customer_id) delete
    - row with empty annual_income-> exercises  coalesce(annual_income, 0)
----------------------------------------------------------------------*/
data demo.raw_customers;
    infile datalines dsd truncover;
    length state $10;
    input customer_id date_of_birth :date9. annual_income state $;
    format date_of_birth date9.;
datalines;
1,15JAN1980,200000,NY
2,03MAR1975,80000,CA
3,22JUL2010,40000,TX
4,09NOV1995,,WA
,01JAN1970,50000,OH
;
run;

/*======================================================================
  PIPELINE  --  identical to sample 02
======================================================================*/
data demo.accounts_prep;
    set demo.raw_accounts;
    if missing(account_id) then delete;
    balance = coalesce(current_balance, 0);
    credit_limit = coalesce(credit_limit, 0);
    utilization = divide(balance, credit_limit);
    if missing(utilization) then utilization = 0;
    if utilization >= 0.90 then risk_band = 'HIGH';
    else if utilization >= 0.60 then risk_band = 'MEDIUM';
    else risk_band = 'LOW';
    active_flag = (account_status = 'ACTIVE');
    keep customer_id account_id balance credit_limit utilization risk_band active_flag open_date;
run;

data demo.customer_prep;
    set demo.raw_customers;
    if missing(customer_id) then delete;
    age = intck('year', date_of_birth, '31DEC2025'd);
    if age < 18 then age_band = 'UNDER18';
    else if age < 30 then age_band = '18_29';
    else if age < 50 then age_band = '30_49';
    else age_band = '50_PLUS';
    income = coalesce(annual_income, 0);
    if income >= 150000 then income_band = 'HIGH';
    else if income >= 75000 then income_band = 'MEDIUM';
    else income_band = 'LOW';
    keep customer_id age age_band income income_band state;
run;

proc sort data=demo.accounts_prep;
    by customer_id;
run;

proc sort data=demo.customer_prep;
    by customer_id;
run;

data demo.account_customer;
    merge demo.accounts_prep(in=acct) demo.customer_prep(in=cust);
    by customer_id;
    if acct;
    if cust = 0 then do;
        age = .;
        age_band = 'UNKNOWN';
        income = 0;
        income_band = 'UNKNOWN';
        state = 'UNKNOWN';
    end;
    debt_to_income = divide(balance, income);
    if missing(debt_to_income) then debt_to_income = 0;
    if debt_to_income >= 0.50 then dti_flag = 1;
    else dti_flag = 0;
run;

proc means data=demo.account_customer nway noprint;
    class customer_id age_band income_band;
    var balance credit_limit utilization;
    output out=demo.customer_exposure
        n=account_count
        sum(balance)=total_balance
        sum(credit_limit)=total_credit_limit
        mean(utilization)=avg_utilization;
run;

data demo.customer_level;
    set demo.customer_exposure;
    available_credit = total_credit_limit - total_balance;
    if available_credit < 0 then over_limit_flag = 1;
    else over_limit_flag = 0;
    if avg_utilization >= 0.90 then utilization_flag = 1;
    else utilization_flag = 0;
    drop _TYPE_ _FREQ_;
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

%dump(raw_accounts);
%dump(raw_customers);
%dump(accounts_prep);
%dump(customer_prep);
%dump(account_customer);
%dump(customer_exposure);
%dump(customer_level);

%put NOTE: Oracle #02 CSVs written to &outdir;
