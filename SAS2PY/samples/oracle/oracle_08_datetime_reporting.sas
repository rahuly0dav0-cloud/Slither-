/*======================================================================
  SAS ORACLE #08  --  dummy data + ground truth for sample 08
  (date/time logic & reporting)

  Self-contained: inlines demo.raw_members, runs the SAME pipeline as
  samples/sas/08_datetime_reporting.sas, and exports the key outputs.

  Set OUTDIR first:  %let outdir = /tmp/sas_oracle/08;
======================================================================*/
%let outdir = /tmp/sas_oracle/08;
%let asof = '31DEC2025'd;

libname demo (work);

proc format;
    value ageband
        low -< 25 = '18-24'
        25  -< 35 = '25-34'
        35  -< 50 = '35-49'
        50  - high = '50+';
run;

data demo.raw_members;
    infile datalines dsd truncover;
    input member_id date_of_birth :date9. join_date :date9. last_active_date :date9. region :$10.;
    format date_of_birth join_date last_active_date date9.;
    datalines;
1,15MAR1990,10JAN2023,01DEC2025,NORTH
2,02JUL2001,15JUN2024,15AUG2025,SOUTH
3,20NOV1980,01MAR2020,,EAST
4,11JAN1975,20SEP2025,10DEC2025,WEST
5,30SEP1999,05FEB2025,,NORTH
6,05MAY1968,12DEC2021,20NOV2025,SOUTH
7,17FEB1995,01JAN2025,01JAN2025,EAST
;
run;

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

proc freq data=demo.members noprint;
    tables region * status / out=demo.region_status_freq;
run;

proc means data=demo.members noprint;
    class status;
    var tenure_months age;
    output out=demo.status_means
        mean(tenure_months)=avg_tenure
        mean(age)=avg_age
        n(member_id)=n_members;
run;

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

%macro dump(ds); proc export data=demo.&ds outfile="&outdir/&ds..csv" dbms=csv replace; run; %mend;
%dump(members);
%dump(region_status_freq);
%dump(status_means);
%dump(monthly_cumulative);
