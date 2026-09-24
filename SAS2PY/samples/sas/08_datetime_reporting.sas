/* SAMPLE 08 - DATE/TIME LOGIC & REPORTING
   Edge cases for the converter:
     - INTNX / INTCK date arithmetic, date literals, YObs formats
     - PROC FREQ (crosstab), PROC MEANS (class), PROC TABULATE
     - a user PROC FORMAT applied to a computed age band
     - running month-over-month totals with RETAIN + BY
*/
libname demo "/prototype/data";

%let asof = '31DEC2025'd;

proc format;
    value ageband
        low -< 25 = '18-24'
        25  -< 35 = '25-34'
        35  -< 50 = '35-49'
        50  - high = '50+';
run;

/* clean + derive date-based features ----------------------------------- */
data demo.members;
    set demo.raw_members;
    if missing(member_id) then delete;
    tenure_months = intck('month', join_date, &asof);
    if tenure_months < 0 then tenure_months = 0;
    next_renewal  = intnx('year', join_date, tenure_months >= 12, 'same');
    age = intck('year', date_of_birth, &asof);
    age_band = put(age, ageband.);
    length status $8;
    if last_active_date = . then status = 'DORMANT';
    else if intck('month', last_active_date, &asof) <= 3 then status = 'ACTIVE';
    else status = 'LAPSED';
    keep member_id region age age_band tenure_months status join_date last_active_date;
run;

/* crosstab: status by region ------------------------------------------- */
proc freq data=demo.members noprint;
    tables region * status / out=demo.region_status_freq;
run;

/* class means: tenure + age by status ---------------------------------- */
proc means data=demo.members noprint;
    class status;
    var tenure_months age;
    output out=demo.status_means
        mean(tenure_months)=avg_tenure
        mean(age)=avg_age
        n(member_id)=n_members;
run;

/* monthly signups with a running cumulative total ---------------------- */
data demo.signups;
    set demo.members;
    signup_month = intnx('month', join_date, 0, 'begin');
    format signup_month yymmn6.;
    keep member_id signup_month;
run;

proc sort data=demo.signups; by signup_month; run;

proc means data=demo.signups noprint;
    by signup_month;
    output out=demo.monthly_counts n(member_id)=n_signups;
run;

data demo.monthly_cumulative;
    set demo.monthly_counts;
    retain cumulative_signups 0;
    drop _type_ _freq_;
    cumulative_signups = cumulative_signups + n_signups;
run;

/* tabulate report ------------------------------------------------------ */
proc tabulate data=demo.members out=demo.age_status_table;
    class age_band status;
    table age_band all, status*n all*n;
run;
