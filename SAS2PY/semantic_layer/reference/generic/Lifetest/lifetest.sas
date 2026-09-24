proc import datafile="/cloud/pv008_069/wfpds/contractors/Sahil/SURVIVAL_DATA_1_sample.csv"
    out=work.SURVIVAL_DATA_1_sample
    dbms=csv
    replace;
    GUESSINGROWS=max;
    getnames=yes;
run;

ods graphics on;

proc lifetest noprint data=WORK.SURVIVAL_DATA_1_sample
    outsurv=survtest_1a_sample
    outtest=survtest_1b
    plots=(c s ls lls h p)
    notable
    method=LT
    NINTERVAL=110;
    time WaitTime*ABANDON(0);
    strata org_name org_id;
    freq Records;
run;