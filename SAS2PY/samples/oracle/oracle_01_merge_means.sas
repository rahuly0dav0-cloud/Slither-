/*======================================================================
  SAS ORACLE #01  --  ground-truth generator for sample 01
  (data engineering: clean -> sort -> merge -> means -> finalize)

  WHAT THIS DOES
  --------------
  1. Recreates the two raw input tables INLINE (no external data needed),
     so this program is fully self-contained and runnable as-is.
  2. Runs the EXACT same pipeline as
     SAS2PY/samples/sas/01_data_engineering_merge_means.sas
  3. Exports every input, intermediate, and final table to CSV.

  The CSV files it writes are the QC ground-truth baselines: run this in
  SAS, then send the CSVs back so the Python conversion can be compared
  against them with run_dataset_qc.

  BEFORE RUNNING
  --------------
  Set OUTDIR to a per-sample folder that already exists on the SAS machine.
  Use a SEPARATE folder per oracle -- all three write a raw_customers.csv
  with different columns, so they must not share one directory.
    * Unix/Linux : %let outdir = /tmp/sas_oracle/01;
    * Windows    : %let outdir = C:\temp\sas_oracle\01;
  (Create the folder first; SAS will not create it for you.)
======================================================================*/

%let outdir = /tmp/sas_oracle/01;

/* Alias the sample's "demo" library to WORK so no disk path is required. */
libname demo (work);

/*----------------------------------------------------------------------
  RAW INPUT #1 : demo.raw_customers
  DSD + TRUNCOVER let empty fields represent missing values:
    - row 3 has an empty state   -> exercises  if missing(state)
    - row 4 has an empty income  -> exercises  coalesce(income, 0)
    - last row has empty id      -> exercises  if missing(customer_id) delete
----------------------------------------------------------------------*/
data demo.raw_customers;
    infile datalines dsd truncover;
    length state $10;   /* wide enough to hold 'UNKNOWN' without truncation */
    input customer_id date_of_birth :date9. income state $;
    format date_of_birth date9.;
datalines;
1,15JAN1980,120000,NY
2,03MAR1975,65000,CA
3,22JUL1990,30000,
4,09NOV1985,,TX
5,30DEC2000,50000,WA
6,01JAN1995,99999,FL
7,05MAY1988,250000,IL
,01JAN1970,40000,OH
;
run;

/*----------------------------------------------------------------------
  RAW INPUT #2 : demo.raw_transactions
    - one row dated 2024        -> exercises the pre-2025 delete
    - one row with empty amount -> exercises sum(amount, fee) with missing
    - customer 8 has no master  -> exercises the merge  if a and b
----------------------------------------------------------------------*/
data demo.raw_transactions;
    infile datalines dsd truncover;
    input customer_id transaction_date :date9. amount fee;
    format transaction_date date9.;
datalines;
1,10FEB2025,5000,50
1,15MAR2025,200,10
2,20FEB2025,3000,25
2,05DEC2024,1000,10
3,01MAR2025,,5
5,18APR2025,6000,100
6,22JUN2025,150,5
7,30JAN2025,12000,200
8,10FEB2025,500,5
;
run;

/*======================================================================
  PIPELINE  --  identical to sample 01
======================================================================*/
data demo.customer_master;
    set demo.raw_customers;
    length customer_segment $12;
    if missing(customer_id) then delete;
    customer_age = intck('year', date_of_birth, '31DEC2025'd);
    annual_income = coalesce(income, 0);
    if annual_income >= 100000 then customer_segment = 'PREMIUM';
    else if annual_income >= 50000 then customer_segment = 'STANDARD';
    else customer_segment = 'BASIC';
    if missing(state) then state = 'UNKNOWN';
    keep customer_id state date_of_birth customer_age annual_income customer_segment;
run;

data demo.transaction_clean;
    set demo.raw_transactions;
    transaction_amount = sum(amount, fee);
    if missing(transaction_amount) then transaction_amount = 0;
    if transaction_date < '01JAN2025'd then delete;
    month = month(transaction_date);
    year = year(transaction_date);
    keep customer_id transaction_date transaction_amount month year;
run;

proc sort data=demo.customer_master;
    by customer_id;
run;

proc sort data=demo.transaction_clean;
    by customer_id;
run;

data demo.customer_transactions;
    merge demo.customer_master(in=a) demo.transaction_clean(in=b);
    by customer_id;
    if a and b;
    high_value_txn = (transaction_amount >= 5000);
run;

proc means data=demo.customer_transactions nway noprint;
    class customer_id customer_segment;
    var transaction_amount;
    output out=demo.customer_summary
        n=transaction_count
        sum=total_transaction_amount
        mean=avg_transaction_amount
        min=min_transaction_amount
        max=max_transaction_amount;
run;

data demo.customer_summary_final;
    set demo.customer_summary;
    if transaction_count > 0 then avg_transaction_amount = total_transaction_amount / transaction_count;
    if total_transaction_amount >= 25000 then activity_flag = 'HIGH';
    else if total_transaction_amount >= 10000 then activity_flag = 'MEDIUM';
    else activity_flag = 'LOW';
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

%dump(raw_customers);
%dump(raw_transactions);
%dump(customer_master);
%dump(transaction_clean);
%dump(customer_transactions);
%dump(customer_summary);
%dump(customer_summary_final);

%put NOTE: Oracle CSVs written to &outdir;
