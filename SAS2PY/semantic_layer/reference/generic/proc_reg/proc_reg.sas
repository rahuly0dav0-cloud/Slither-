proc sort data=work.c_2;
    by org_id org_name lob_desc Bad_Interval;
run;

proc reg noprint data=work.c_2 outest=PARAMETERS_NONLIN_2;
    by org_id org_name lob_desc Bad_Interval;
    model WaitTime = x1 x2 x3 x4 x5 x6 x7
        / selection=none;
run;