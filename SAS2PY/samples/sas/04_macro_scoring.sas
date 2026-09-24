/* SAMPLE 04 - MACRO-DRIVEN RISK SCORING
   Edge cases for the converter:
     - a %MACRO is DEFINED and then INVOKED in the middle of the pipeline
     - macro parameters, %LET macro variables, %IF/%THEN/%ELSE, %DO loops
     - CALL SYMPUTX pushes a value from a DATA step back into a macro var
     - the macro is called twice with different arguments
*/
libname demo "/prototype/data";

%let score_year   = 2025;
%let premium_cut  = 720;      /* credit score threshold for the top tier   */
%let n_bands      = 5;        /* number of risk bands to build             */

/* ---- step 1: clean the raw applicants (runs BEFORE any macro) ---------- */
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

/* ---- the macro is defined HERE, between two data steps ----------------- */
%macro score_tier(inds=, outds=, min_score=);
    /* derive an average score so the macro can print a data-driven note */
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
        /* band the debt ratio into &n_bands buckets */
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

/* ---- step 2: call the macro twice, with different cutoffs -------------- */
%score_tier(inds=demo.applicants_clean, outds=demo.scored_premium, min_score=&premium_cut);
%score_tier(inds=demo.applicants_clean, outds=demo.scored_standard, min_score=660);

/* ---- step 3: post-macro aggregation ----------------------------------- */
proc sort data=demo.scored_standard;
    by region;
run;

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
