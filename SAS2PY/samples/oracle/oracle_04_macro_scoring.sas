/*======================================================================
  SAS ORACLE #04  --  dummy data + ground truth for sample 04
  (macro-driven risk scoring)

  Self-contained: inlines demo.raw_applicants, runs the SAME macro
  pipeline as samples/sas/04_macro_scoring.sas, and exports the key
  tables to CSV. No external data or libraries needed.

  Set OUTDIR to an existing per-sample folder before running:
    * Unix : %let outdir = /tmp/sas_oracle/04;
    * Win  : %let outdir = C:\temp\sas_oracle\04;
======================================================================*/
%let outdir = /tmp/sas_oracle/04;
%let score_year  = 2025;
%let premium_cut = 720;
%let n_bands     = 5;

libname demo (work);

/* ---- dummy raw input -------------------------------------------------- */
data demo.raw_applicants;
    infile datalines dsd truncover;
    input applicant_id date_of_birth :date9. income total_debt credit_score region :$10.;
    format date_of_birth date9.;
    datalines;
1,15MAR1990,82000,12000,745,NORTH
2,02JUL1985,54000,30000,690,SOUTH
3,20NOV1998,38000,5000,660,EAST
4,11JAN1978,,45000,710,WEST
5,30SEP2001,29000,2000,,NORTH
6,05MAY1969,120000,60000,780,SOUTH
7,17FEB1995,47000,15000,632,
8,,50000,10000,700,EAST
;
run;

/* ---- same pipeline as the sample -------------------------------------- */
data demo.applicants_clean;
    set demo.raw_applicants;
    if missing(applicant_id) then delete;
    length region $10;
    age = intck('year', date_of_birth, "31DEC&score_year"d);
    if age < 18 then delete;
    annual_income = coalesce(income, 0);
    debt_ratio    = divide(total_debt, max(annual_income, 1));
    if missing(credit_score) then credit_score = 640;
    if missing(region) then region = 'UNKNOWN';
    keep applicant_id region age annual_income debt_ratio credit_score;
run;

%macro score_tier(inds=, outds=, min_score=);
    proc means data=&inds noprint;
        var credit_score;
        output out=_score_stats mean=_avg_score;
    run;
    data _null_;
        set _score_stats;
        call symputx('avg_score', put(_avg_score, 6.1));
    run;
    %put NOTE: &inds average credit score = &avg_score (cutoff &min_score);
    data &outds;
        set &inds;
        length risk_tier $8;
        band = min(&n_bands, 1 + floor(debt_ratio * &n_bands));
        if band < 1 then band = 1;
        %if &min_score >= &premium_cut %then %do;
            if credit_score >= &min_score then risk_tier = 'PREMIUM';
            else risk_tier = 'REVIEW';
        %end;
        %else %do;
            if credit_score >= &min_score then risk_tier = 'STANDARD';
            else risk_tier = 'DECLINE';
        %end;
        approved = (risk_tier in ('PREMIUM','STANDARD'));
    run;
%mend score_tier;

%score_tier(inds=demo.applicants_clean, outds=demo.scored_premium, min_score=&premium_cut);
%score_tier(inds=demo.applicants_clean, outds=demo.scored_standard, min_score=660);

proc sort data=demo.scored_standard; by region; run;

proc means data=demo.scored_standard noprint;
    by region;
    var annual_income debt_ratio credit_score approved;
    output out=demo.region_summary
        mean(annual_income)=avg_income
        mean(debt_ratio)=avg_debt_ratio
        mean(credit_score)=avg_score
        sum(approved)=n_approved;
run;

data demo.region_summary_final;
    set demo.region_summary;
    drop _type_ _freq_;
    approval_rate = divide(n_approved, max(_freq_, 1));
run;

/* ---- export CSV baselines -------------------------------------------- */
%macro dump(ds); proc export data=demo.&ds outfile="&outdir/&ds..csv" dbms=csv replace; run; %mend;
%dump(raw_applicants);
%dump(applicants_clean);
%dump(scored_standard);
%dump(region_summary_final);
