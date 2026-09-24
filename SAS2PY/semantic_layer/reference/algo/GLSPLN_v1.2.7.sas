***********************************************************************
Generalized Linear Spline.sas  (GLSPLN)
***********************************************************************

A SAS macro for creating continuous linear splines using stepwise
selection in proc GLMSelect while adjusting for blocking variables.

Developed by Dr. Basil Coutant.

change log
1.1.1    Copied from version 1.20120905b. Should mirror LLSPLN.
1.1.2    Ajustments for missings and for non-positive variables.
1.1.3    Added separate plot macro.
1.1.4    Improved handling of missing values
reverse GLSPLN + additional changes specific to DND models
1.2.1    Forward/ standard RELU, allsig now long instead of wide,
         moving plotting functionality to a separate macro
         (not yet functional) add the last knot feature
1.2.2    Optional forward/backward/both and initialize
1.2.3    Variable number of knots
1.2.4    Bound trend macro
1.2.5    Lasso selection rather than BIC
1.2.6    lasso with no blocking variables
1.2.7    lasso selection wo block vars - LS coesf
***********************************************************************

***********************************************************************

***********************************************************************;

%let GLSPLN_version=1.2.7;
%let GLSPLN_last_update=1/28/25;

data GLSPLN_help;
input Help $char80.;
Label help='GLSPLN Help Documentation';
cards;

************************************************************************
%GLSPLN(dsin, resp_var, expl_var, n=1, allsig=allsig, cont_blk_var= ,
        cat_blk_var= , MAXSTEP = 10, Num_knot = 100, Last_knot= , name=,
        initialize = 0, activation=0)

%add_UT_vars(dsin, dsout, allsig, expl_var, n=1)

%bnd_trend(nn, varr, allsigg, min_trend, max_trend, trend_restrctn_strt)
************************************************************************

*****************
REQUIRED INPUT
*****************
dsin = the input dataset
       (You may use statements such as keep and where with this dataset.)
       (It reads from this data - it does not write to it.)

resp_var = the target or response variable.

expl_var = a continuous variable to model resp_var with

n = an index for the output - must be a number

*****************
OPTIONAL INPUT
*****************

allsig = An output dataset with the code for the spline info including the
         code for adding the transformation to another dataset.

allplotdat = The data used in the "bin" plots.  (to be used to plot macro)

Cont_blk_var = continuous (linear) variables to block on.

Cat_blk_var = categorical variables to block on.

levels = the number of bins to use in the bin plot.  (to be moved to plot)

MAXSTEP = The maximum number of stepwise steps used in creating the spline.
          The number of knots will be at most this value, but could be less.

Last_knot = the largest value for a continuous knot.  If used the code,
            includes step functions to model changes larger than this value

Num_knot = The number of knots to use. It is recommended that there be at
           least 5 obs per knot.  Values are limited to 25, 50 100, 200, 250

slentry = The probability criteria for adding a knot into the model. (See
          Proc Logistic for documentation.) (not used, BIC/SBC)

slstay = The probability criteria for keeping knots in the model. (See Proc
         Logistic for documentation.)        (not used, BIC/SBC)

name = The name for the transformed variable in the output.  (The default is
       the old variable name with "_ut" appended to the end.)

initialize = an indicator to initialize the output.  1 triggers the
             initialization any value other than 1 causes the output to be appended to
             the previous output.  The code will yield errors if things haven't been
             initialized.

Activation = indicators to switch activation functions.
             -1 uses min(0,x), 1 uses max(0,x), and 0 uses both types

Notes:

==>  The code is NOT idiot proof! Review the log for errors.    <==
==>  Make sure that the output is reasonable.  Odd things happen!  <==
;
run;

%macro GLSPLNhelp(x);

%if &x. = 1 %then %do;
    %let nobs=12;
%end;
%else %if &x. = 2 %then %do;
    %let nobs=max;
%end;
%else %do;
    %let nobs=max;
%end;

/*options LINESIZE=86 center ;*/
proc print data=GLSPLN_help(obs=&nobs.) noobs label ;run;
/*options LINESIZE=200 nocenter ;*/
%mend;

***********************************************************************
Versions:
%GLSPLNhelp(1);    ***********************************************
%GLSPLNhelp(2);    ***********************************************
**********************************************************************;

/*options LINESIZE=200 nocenter ;*/

data About_GLSPLN;
label pad='00'x description='00'x value='00'x;
input pad $char3. description $char12. value $50.;
cards;
GLSPLN        The GLSPLN macro package
              Generalized Linear Spline
Version
Last update
Author      Dr. Basil Coutant (Basil.W.Coutant@Chase.com)

UserGroup   Send an email to Basil.W.Coutant@Chase.com to be
            put on the update distribution list.

Notes:
    1)  Verify any use of the last knot feature!

    2)  See notes that the end for running this on
        multiple variables.

    3)  The activation parameter switches the
        activation functions.
        -1 uses min(0,x), 1 uses max(0,x), and
         0 uses both types

Help:   %GLSPLNhelp(x) x = 1 a for restricted version.
;
run;

data About_GLSPLN;
set About_GLSPLN;
if Description='Version' then value="&GLSPLN_version.";
if Description='Last update' then value="&GLSPLN_last_update.";
run;

proc print data=About_GLSPLN noobs label ; run;

proc datasets lib=work;
delete About_GLSPLN;
quit;

run;

%GLSPLNhelp(1);

data GLSPLN_meta;
format pad $1. Macro_var_desc $char20. Macro_var $20. Value $50.;
/*label Macro_var_desc='00'x Value='00'x pad='00'x;*/
label Macro_var_desc='Macro parameter' Value='Parameter value' pad='00'x;
input Macro_var Macro_var_desc $char20.;Value='1';Pad=' ';
cards;
version     GLSPLN Version
date        Run Date
dsin        Data set
resp_var    Response variable
expl_var    Explanatory variable
n           Output index
Allsig      Spline code output
Cont_blk_var Cont. block vars.
Cat_blk_var Cat. block vars.
MAXSTEP     Max number of knots
Num_knot    Number of knots used
Last_knot   Max value for a bend
Name        Spline var. name
Initialize  Init. trigger
Activation  Act. fn choice

;
run;

%global step tnum;
%let tnum = &model_id.;
%let step = 1;
%global tracker;

%macro GLSPLN(dsin, resp_var, expl_var, n, allsig=allsig, cont_blk_var= , cat_blk_var= ,
             MAXSTEP=8, Num_knot = 100, Last_knot=, name=, Initialize=0, activation=0);

ods exclude all;* all other excludes are commented out except for a corresponding statement at the end;

%if 1 = &Initialize. %then %do;

    data GLSPLN_meta;
    set GLSPLN_meta;
    format full_value $500.;
    if Macro_var='version' then full_value="&GLSPLN_version.";
    else if Macro_var='date' then full_value=put(today(),date9.);
    else if Macro_var='dsin' then full_value="&dsin.";
    else if Macro_var='resp_var' then full_value="&resp_var.";
    else if Macro_var='expl_var' then full_value="&expl_var.";
    else if Macro_var='n' then full_value="&n.";
    else if Macro_var='Allsig' then full_value="&Allsig.";
    /* else if Macro_var='Allplotdat' then full_value="&Allplotdat."; */
    else if Macro_var='Cont_blk_var' then full_value="&Cont_blk_var.";
    else if Macro_var='Cat_blk_var' then full_value="&Cat_blk_var.";
    /* else if Macro_var='Levels' then full_value="&Levels."; */
    else if Macro_var='MAXSTEP' then full_value="&MAXSTEP.";
    else if Macro_var='Num_knot' then full_value="&Num_knot.";
    else if Macro_var='Last_knot' then full_value="&Last_knot.";
    /* else if Macro_var='Slentry' then full_value="&Slentry."; */
    /* else if Macro_var='Slstay' then full_value = "&Slstay."; */
    else if Macro_var='Name' then full_value="&Name.";
    else if Macro_var='Initialize' then full_value="&Initialize.";
    else if Macro_var='Activation' then full_value="&Activation.";
    Value=trim(left(substr(full_value,1,50)));
    run;

    title "   GLSPLN model information. See GLSPLN_meta.";
    title2 "(Display limited to 50 characters.)";

    Proc print data=GLSPLN_meta( keep=pad Macro_var_desc value
        where=(Macro_var_desc ne 'Explanatory variable')) noobs label;run;
    title ; title2 ;

# -------------------Below for Conversion Test ---------------#

data ttracker;
format test 8. step 8. call $350.;
test = &tnum.;
step = &step.;
call = "GLSPLN(&dsin.)";
run;

data out.tracker&tnum.;
    set out.tracker&tnum. ttracker;
run;

data _null_;
    locstep = &step.;
    sstep = &step. + 1;
    call symput('step', strip(sstep));
    call symput('locstep', strip(locstep));
run;

data out.step_&locstep._meta_in&tnum.;
    set GLSPLN_meta;
run;

data out.step_&locstep._data_in&tnum.;
    set &dsin.;
run;

# -------------------Above for Conversion Test ---------------#


proc datasets lib=work;
delete allsig association parms test_t xvalue temp ttemp min max parm2 knot knt knt1 beta blkvarnames respvarnames;
quit;
run;
%end;
%else %do;
proc datasets lib=work;
delete association parms test_t xvalue temp ttemp min max parm2 knot knt knt1 beta blkvarnames respvarnames;
quit;
run;
%end;

title1 ;title2 ;
title1 HEIGHT=1.5 "Modeling: &resp_var. with &expl_var." ;
title2 HEIGHT=1.5 "Data: &dsin." ;

/* Create main working dataset for the macro. */

data ttemp;
set &dsin. ;
byvar=1;
keep &expl_var. &resp_var. &cont_blk_var. &cat_blk_var. byvar ;
run;

/* Restrict Num_knot to allowed values        */
/* Set the corresponding value for knot_step*/

Data _null_;
initial=&Num_knot.;
if initial <= 49 then do; * If you try to set it to 50, then you need to use 51;
    call symput("Num_knot",strip(26));
    call symput("Knot_step",strip(4));
end;
else if initial <= 99 then do;
    call symput("Num_knot",strip(51));
    call symput("Knot_step",strip(2));
end;
else if initial <= 199 then do;
    call symput("Num_knot",strip(101));
    call symput("Knot_step",strip(1));
end;
else if initial <= 249 then do;
    call symput("Num_knot",strip(201));
    call symput("Knot_step",strip(0.5));
end;
else do;
    call symput("Num_knot",strip(251));
    call symput("Knot_step",strip(0.4));
end;
run;

/* Initialize last_knot if it is missing. */

proc sql noprint;
select 2*max(abs(&expl_var.)+1)
into :last_knt_default
from ttemp;
quit;

data _null_;
l_knot=strip("&last_knot.");
if missing(l_knot) then do;
    call symput("Last_knot",strip(&last_knt_default.));
end;
run;

/* Previous versions used -x (with flip = -1) if x < 0. */
/* The macro variable flip = 1 indicates that we are using */
/* the raw variable. */
%let flip = 1;

***********************************************************************
/* Count the number of block variables. */;

proc contents data=ttemp(keep = &resp_var. &cont_blk_var. &cat_blk_var. )
    out=blkvarnames(keep = name type) noprint ;
run;

data _null_;
    dsid=open("blkvarnames");
    nvalue2=attrn(dsid,"nobs")-1;
    call symput("num_blk_var",trim(left(nvalue2)));
    done=close(dsid);
run;
%put num_blk_var = &num_blk_var.;

***********************************************************************
/* Count the number of explanatory variables. */;

proc contents data=ttemp(keep = &resp_var. &expl_var. )
    out=respvarnames(keep = name type) noprint ;
run;

data _null_;
    dsid=open("respvarnames");
    nvalue2=attrn(dsid,"nobs")-1;
    call symput("num_resp_var",trim(left(nvalue2)));
    done=close(dsid);
run;
%put num_resp_var = &num_resp_var.;

***********************************************************************

/* Current version uses 200 knots in the range */;

proc univariate data=ttemp(keep= &expl_var.) noprint;
    var &expl_var.;
    output out=knots pctlpre=kn pctlpts=0 to 100 by &Knot_step.;
run;

proc transpose data=knots out=kk;run;

data kk;
set kk;
id='kn' || strip(_n_);
run;

proc transpose data=kk out=knots(drop=_name_);
var col1;
id id;
run;

/* Add byvar = 1 to knots for subsequent merge */
data knots;
set knots;
byvar=1;
run;

proc sql noprint;
select
    max(&expl_var.), min(&expl_var.)
into :max_val, :min_val
from
    &dsin.
;
quit;

/* Define the blade variables (cx[i]) with in temp. */
/* cx[1] is an indicator missingness.              */
/* For i > 1, cx[i] is the usual RELU function     */
/* unless the last knot condition applies          */
/* in which case it is a step function.            */
/* In either case cx[i] is zero for missing x.     */
/* The merge causes the the single row of knots to */
/* be appended to all rows of ttemp.               */

data ttemp;
merge ttemp knots;
by byvar;

array kn[&Num_knot.] ;
array minx[&Num_knot.];
array maxx[&Num_knot.];

misx = missing(&expl_var.);
do i=1 to &Num_knot.;
    if missing(&expl_var.)            then minx[i]=0;
    else if kn[i] <= &last_knot.       then minx[i]= min(0, &expl_var. - kn[i]) ;
    else                               minx[i]= (&expl_var. > kn[i]) ;
end;

do i=1 to &Num_knot.;
    if missing(&expl_var.)            then maxx[i]=0;
    else if kn[i] <= &last_knot.       then maxx[i]= max(0, &expl_var. - kn[i]) ; /*<- changes slope;*/
    else                               maxx[i]= (&expl_var. > kn[i]) ;           /*<- changes intercept;*/
end;

keep &expl_var. &resp_var. &cont_blk_var. &cat_blk_var. misx minx1-minx&Num_knot. maxx1-maxx&Num_knot. byvar;
run;

run;

/* Main model fitting. All block variables      */
/* are forced into the model (even if           */
/* insignificant). Stepwise selection is of     */
/* the cx variables. Only parameter estimates   */
/* for the knots are saved.                     */

data _null_;
/* if &Activation. = 0 then
   mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx minx1 - minx&Num_knot. maxx1 - maxx&Num_knot. /selection=GROUPLASSO include = &num_blk_var. MAXSTEP=&MAXSTEP.";
else if &Activation. = 1 then
   mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx maxx1 - maxx&Num_knot. /selection=GROUPLASSO include = &num_blk_var. MAXSTEP=&MAXSTEP.";
else
   mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx minx1 - minx&Num_knot. /selection=GROUPLASSO include = &num_blk_var. MAXSTEP=&MAXSTEP."; */

/* if &Activation. = 0 then */
/* mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx minx1 - minx&Num_knot. maxx1 - maxx&Num_knot. /selection=GROUPLASSO(steps=10 rho=0.99) include = &num_blk_var. "; */
/* else if &Activation. = 1 then */
/* mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx maxx1 - maxx&Num_knot. /selection=GROUPLASSO(steps=10 rho=0.99) include = &num_blk_var. "; */
/* else */
/* mod_stmnt="model &resp_var. = &cat_blk_var. &cont_blk_var. misx minx1 - minx&Num_knot. /selection=GROUPLASSO(steps=10 rho=0.99) include = &num_blk_var. "; */

if &Activation. = 0 then
   mod_stmnt="model &resp_var. = misx minx1 - minx&Num_knot. maxx1 - maxx&Num_knot. /selection=lasso(screen=sasvi LSCOEFFS) MAXSTEP=&MAXSTEP.";
else if &Activation. = 1 then
   mod_stmnt="model &resp_var. = misx maxx1 - maxx&Num_knot. /selection=lasso(screen=sasvi LSCOEFFS) MAXSTEP=&MAXSTEP.";
else
   mod_stmnt="model &resp_var. = misx minx1 - minx&Num_knot. /selection=lasso(screen=sasvi LSCOEFFS) MAXSTEP=&MAXSTEP.";

call symput('mod_stmnt',mod_stmnt);
run;

%put &mod_stmnt.;

ods trace off;
ods output FitStatistics=association;
ods output ParameterEstimates=parms;
proc glmselect data=ttemp ; * outest=parms;
class byvar &cat_blk_var. /param=glm;
&mod_stmnt.;
run;

data knot;
set parms;
where ('misx' = substr(parameter,1,4)) or ('minx' = substr(parameter,1,4)) or ('maxx' = substr(parameter,1,4));
run;

data _null_;
set parms;
where 'Intercept' = parameter;
call symput('Intercept',trim(left(estimate)));
run;

data _null_;
dsid=open("knot");
nvalue2=attrn(dsid,"nobs");
call symput('num_knts', trim(left(nvalue2)));
done=close(dsid);
run;

data knot;
set knot;
byvar=1;
dir=substr(parameter,1,3);
if 'mis' = dir then index=0;
else index=substr(parameter,5);
run;

data knot;
merge knot knots;
by byvar;
array kn[&Num_knot.];
if index > 0 then &expl_var._kt=kn[index];
else if index = 0 then &expl_var._kt = 0;
else index=-1;

drop kn1-kn&Num_knot.;
run;

proc sort data=knot;
by index;
run;

data code;
set knot;
format variable $32. tvariable $32. code $200. line $100.;

variable ="&expl_var." ;
tvariable ="&name.";
n=&n.;
knot=&expl_var._kt;
beta=estimate;
spline_ind=((&expl_var._kt <= &last_knot.) and (index > 0)) * (2*(dir='max') - 1 );
num_knts=&num_knts.;
flip_var=variable;

if missing(tvariable) or length(tvariable) < 1 then
    tvariable = "&expl_var." || '_ut';
call symput('tvariable',tvariable);

/* case: missing indicator only */
if &num_knts. = 1 and _n_ = 1 and index = 0 then
    code = left(trim(tvariable)) || ' = ' || strip(estimate) ||
           ' * missing(' || left(trim(variable)) || ');';
/* case: knots with missing indicator */
else if _n_ = 1 and index = 0 then
    code = "If missing(&expl_var.) then " || left(trim(tvariable)) ||
           " = " || strip(put(estimate,e12.)) || "; else " ||
           left(trim(tvariable)) || " = " ;

/* case: knots without missing indicator */
else if _n_ = 1 and index > 0 then
    line = "If missing(&expl_var.) then " || left(trim(tvariable)) ||
           " = 0; else " || left(trim(tvariable)) || " = " ;
else line = ' ';

if _n_ >= &num_knts then end=' ; ';
else end = ' + ';

If index > 0 and &expl_var._kt <= &last_knot. then
    code = strip(line) || strip(put(estimate,e12.)) || "*" || trim(dir) ||
           "(0, " || trim(flip_var) || " - " || strip(&expl_var._kt) || ")" || end;

If index > 0 and &expl_var._kt > &last_knot. then
    code = strip(line) || strip(put(estimate,e12.)) || "*(" ||
           trim(flip_var) || " > " || strip(&expl_var._kt) || ")" || end;

If index < 0 then code=trim(tvariable) || " = 0; " ;

keep n variable tvariable code StdErr tValue Probt byvar spline_ind num_knts knot beta;
run;

proc transpose data=association out=fitstat(drop=_name_);
var nvalue1;
id label1;
run;

data fitstat;
set fitstat;
byvar=1;
run;

data knt1;
merge code fitstat;
by byvar;
drop byvar;
run;

proc sql noprint;
select code
into : code separated by ' '
from code;
quit;

************************************************************
* start of plot section (removed)
************************************************************;

************************************************************;

%if &Initialize. = 1 %then %do;

    data &allsig.;
    n=.;
    variable='12345678901234567890123456789012';
    tvariable='12345678901234567890123456789012';
    run;

    %end;

data &allsig.;
set &allsig. knt1;
where ^missing(n);
run;

/*-------- Below for Conversion test--------*/

data dsout;
    set &allsig.;
run;

data out.step_&locstep._meta_out&tnum.;
    set GLSPLN_meta;
run;

data out.step_&locstep._data_out&tnum.;
    set dsout;
run;

/*-------- Above for Conversion test--------*/

proc datasets lib=work;
delete association parms test_t xvalue temp min max
       code parm2 knt knt1 beta blkvarnames
       name respvarnames kk ;
quit;
run;

/*ttemp  knot  knots*/
title1 ; title2 ;
ods exclude none;
%mend;

/* Modified for this use case only */
%macro add_UT_vars(dsin, dsout, allsig, expl_var, n);
%global scr_code;

/*-------- Below for Conversion test--------*/

data ttracker;
    format test 8. step 8. call $350.;
    test = &tnum.;
    step = &step.;
    call = "add_UT_vars(&dsin., &dsout., &expl_var.)";
run;

data out.tracker&tnum.;
    set out.tracker&tnum. ttracker;
run;

data _null_;
    locstep = &step.;
    sstep = &step. + 1;
    call symput('step', strip(sstep));
    call symput('locstep2', strip(locstep));
run;

data out.step_&locstep2._explv_in&tnum.;
    expl_var = &expl_var.;
run;

data out.step_&locstep2._data_in&tnum.;
    set &dsin.;
run;

data out.step_&locstep2._allsig_in&tnum.;
    set &allsig.;
run;

/*-------- Above for Conversion test--------*/

proc sql noprint;
select code
into : scr_code separated by ' '
from &allsig.
where upcase(variable) = upcase("&expl_var.") and n=&n.;
quit;

data &dsout.;
set &dsin. ;
&scr_code. ;
run;

/*-------- Below for Conversion test--------*/

data out.step_&locstep2._data_out&tnum.;
    set &dsout.;
run;

/*-------- Above for Conversion test--------*/

%mend;

/*
 bnd_trend
 Input parameters:
   nn               the index (usually DND for us),
   varr             the untransformed variable name (the raw date / time variable for us),
   allsig           the name of the allsig dataset (defaults to &allsig in GLSPLN),
   min_trend        the minimum trend per time step of varr,
   max_trend        the maximum trend per time step of varr,
   trend_restrctn_strt
                    the value of varr where the trend bound is supposed to start
                    (This should generally be the end of the training data. There is no check on
                     this value to make sure that the value makes sense.)
*/

%macro bnd_trend(nn, varr, allsigg, min_trend, max_trend, trend_restrctn_strt);


/*-------- Below for Conversion test--------*/

data ttracker;
    format test 8. step 8. call $350.;
    test = &tnum.;
    step = &step.;
    call = "bnd_trend(&allsigg., )";
run;

data out.tracker&tnum.;
    set out.tracker&tnum. ttracker;
run;

data _null_;
    locstep = &step.;
    sstep = &step. + 1;
    call symput('step', strip(sstep));
    call symput('locstep3', strip(locstep));
run;

data out.step_&locstep3._meta_in&tnum.;
    Nn = &Nn.;
    Varr = &Varr.;
    trend_restrctn_strt = &trend_restrctn_strt.;
run;

data out.step_&locstep3._data_in&tnum.;
    set &allsigg.;
run;

/*-------- Above for Conversion test--------*/

/* Error catching step - this should generally be over written in the next step */
/* If it is not overwritten, then it will get dropped in the last step */
data code_temp;
n=&nn.;
variable="&varr.";
tvariable="&varr." || '_ut';
raw_pred_forward_trend = .;
spline_ind=0;
run;

/* Actual */
proc sql noprint;
create table code_temp as
select
    n,
    variable,
    tvariable,
    sum(beta) as raw_pred_forward_trend
from &allsigg.
where n = &nn.
  and upcase(variable) = upcase("&varr.")
  and spline_ind = 1
group by 1, 2, 3
;
quit;

order by 1, 2, 3;
quit;

data code_temp;
set code_temp;
format code $200.;
if ^missing(raw_pred_forward_trend) and raw_pred_forward_trend - &max_trend. > 1e-12 then do;
    beta=&max_trend. - raw_pred_forward_trend;
    knot=&trend_restrctn_strt.;
    code = trim(tvariable) || ' = ' || trim(tvariable) || ' + ' ||
           strip(put(beta,e12.)) || '*max(0, ' || trim(variable) ||
           ' - ' || strip(&trend_restrctn_strt.) || ');';
    spline_ind=1;
end;
if ^missing(raw_pred_forward_trend) and raw_pred_forward_trend - &min_trend. < -1e-12 then do;
    beta=&min_trend. - raw_pred_forward_trend;
    knot=&trend_restrctn_strt.;
    code = trim(tvariable) || ' = ' || trim(tvariable) || ' + ' ||
           strip(put(beta,e12.)) || '*max(0, ' || trim(variable) ||
           ' - ' || strip(&trend_restrctn_strt.) || ');';
    spline_ind=1;
end;
run;

data &allsigg.;
set &allsigg. code_temp(where=(spline_ind=1));
by n variable;
run;

/*-------- Below for Conversion test--------*/

data out.step_&locstep3._meta_out&tnum.;
    Nn = &Nn.;
    Varr = &Varr.;
    trend_restrctn_strt = &trend_restrctn_strt.;
run;

data out.step_&locstep3._data_out&tnum.;
    set &allsigg.;
run;

/*-------- Above for Conversion test--------*/

%mend ;

%macro shft_min(dsin, allsig, expl_var);

proc sql noprint;
select
    min(&expl_var._ut)
into :min_val
from
    &dsin.
;
quit;

quit;

%put min = &min_val. ;

data &allsig.;
set &allsig.;
format code2 $150.;
if trim(upcase(variable)) = trim(upcase("&expl_var."))
then code2 = "&expl_var._ut = &expl_var._ut - &min_val. + 1;";
run;

data &dsin.;
set &dsin.;
&expl_var._ut = &expl_var._ut - &min_val. + 0;
run;

%mend;

%macro GLSPLN_plots(plot_dat, allsig, resp_var, var, out_folder);

proc sql noprint;
select
    code,
    tvariable
into
    :var_trans,
    :tvar separated by ' '
from &allsig.
where upcase(trim("&var.")) = upcase(trim(variable));
quit;

data tt_plot;
set &plot_dat.(where=(upcase("&var.")=upcase(variable) and ^missing(xrank)));
label resp_mean="Response mean"
      bin_mean="Bin mean"
      &tvar.="&var. transform";
&var.=bin_mean;
&var_trans.;
run;

proc sql noprint;
select
    (sum(resp_mean) - sum(&tvar.))/count(&tvar.)
into :shift separated by ' '
from tt_plot;
quit;

data tt_plot;
set tt_plot;
&tvar. = &tvar. + &shift.;
run;

filename grafout "&out_folder.";

goptions reset=all
         gsfname=grafout
         device=GIF
         gsfmode=replace;

title1 HEIGHT=1.75 "Linear spline transform for &var.";

legend1 position=(top center inside)
        mode=share;

axis1 label=("&resp_var.");

symbol1 c=blue i=none value=plus;
symbol2 c=red  i=join value=X;

proc gplot data=tt_plot;
plot resp_mean * bin_mean
     &tvar.     * bin_mean
     / overlay vaxis=axis1 legend=legend1 name='GLSPN';
run;
quit;

title1; title2;

proc datasets lib=work nolist;
delete tt_plot;
quit;
run;

%mend;

