***********************************************************************
Regression based neural networks  (RBNN)
RBNN v1_0_6

A SAS macro for creating neural networks using an interactive
regression base algorithm.


Developed by Dr. Basil Coutant.

change log
Beta1       An initial release.  This does not allow for categorical
            variable input, nor does it allow/account for missingsness.
Beta3       Added exit conditions.
beta4       Local version for daily models
Beta5       Adds categorical explanatory variables and interactions
Beta6       Adds Alteryx output
1.0.1       Includes NNN loop
1.0.2       Moved meta data to outer loop & fixed 3-way interactions
1.0.3       Changed interactions to start on layer 2 & fixed missing issue.
1.0.4       Fixed mixed length issue and mixed variable reference
1.0.5       Fixed error for dsin w where/drop conditions and forced sum to 1
1.0.6       Fixed blk passing blk variable to final model

***********************************************************************;
*                           
*       Critical notes
*
*    4-way interactions will often fail because of a truncated effect
*
*    Current stack_output is tuned to & assumes daily pattern models
*    See end notes for additional assumptions.
*
***********************************************************************

Run;

%let RBNN_version=1.0.6;
%let RBNN_last_update=2/8/21;*9/16/20;

data RBNN_help;
input Help $char80.;
Label help='RBNN Help Documentation';
cards;

******************************************************************************;
*%RBNN(dsin, resp_var, max_nodes=5, max_layers=5, Cat_expl_var =,
              Cont_expl_var =, interact_level = 1, max_dir_reuse = 8, cont_blk_var =,
              cat_blk_var =, dsout = ttemp_out, code_out = All_code, Activation=0,
              Suppress_meta=0)

%Alteryx_code_out(all_code_in, alteryx_code_out, code_index=)


*******************
  REQUIRED INPUT
*******************

    dsin = the input dataset
        (You may use statements such as keep and where with this dataset.)
        (It reads from this data - it does not write to it.)

    resp_var = the target or response variable.

    Layer = the current layer (must start with 1 and increment)

    Node = the current node (must start with 1 and increment)

    Cont_expl_var = a list of continuous explanatory variables
        It is recommended that these be listed with each node and layer.
        Currently the code includes all previous hidden layers.


*******************
  OPTIONAL INPUT
*******************

    Cont_blk_var = continuous (linear) variables to block on.
        Note:  Previous nodes from the current layer are always included.

    Cat_blk_var = categorical variables to block on. (feature not available)

    levels = the number of bins to use in the bin plot.  (to be moved to plot)


max_dir_reuse = The maximum number of time to reuse a direction.
                The number of knots will be at most this value, but could be less.

Activation = indicators to switch activation functions.
             -1 uses min(0,x), 1 uses max(0,x), and 0 uses both types


Notes:

    ==>  The code is NOT idiot proof!  Review the log for errors.        <==
    ==>  Make sure that the output is reasonable.  Odd things happen!   <==
;
run;


%macro RBNNhelp(x);

%if &x. = 1 %then %do;
    %let nobs=11;
%end;
%else %if &x. = 2 %then %do;
    %let nobs=max;
%end;
%else %do;
    %let nobs=max;
%end;

options nocenter ;
proc print data=RBNN_help(obs=&nobs.) noobs label ;run;
options center ;
%mend;

***************************************************************************************;

Versions:
%RBNNhelp(1); **********************************************************************************
%RBNNhelp(2); **********************************************************************************;

***************************************************************************************;

data About_RBNN;
label pad='00'x description='00'x value='00'x;
input pad $char3. description $char12. value $50.;
cards;
   RBNN       The RBNN macro package

             Regression based neural networks

   Version
   Last update
   Author      Dr. Basil Coutant (Basil.W.Coutant@Chase.com)
   UserGroup   Send an email to Basil.W.Coutant@Chase.com to be
               put on the update distribution list.

Notes:         1)    Three way interactions should work but need 
                    to verify that "effect" is not truncated.

             2)    Only uses obs with no missings to train on.

             3)    The activation parameter switches the 
                   activation functions.
                   -1 uses min(0,x), 1 uses max(0,x), and 
                   0 uses both types

          Help:    %RBNNHelp(x) x = 1 for a restricted version.
;
run;

data About_RBNN;
set About_RBNN;
if Description='Version' then value="&RBNN_version.";
if Description='Last update' then value="&RBNN_last_update.";
run;

proc print data=About_RBNN noobs label ; run;

ods exclude all;
proc datasets lib=work;
delete About_RBNN;
quit;
run;
ods exclude none;


%RBNNhelp(1);

data RBNN_meta;
format pad $1. Macro_var_desc $char24. Macro_var $24. Value $50.;
*label Macro_var_desc='00'x Value='00'x pad='00'x;
label Macro_var_desc='Macro parameter' Value='Parameter value' pad='00'x;
input Macro_var Macro_var_desc $char24.;Value='1';Pad=' ';
cards;
version RBNN Version
date Run Date
dsin Data set
resp_var Response variable
max_nodes Maximum nodes per layer
max_layers Maximum # of layers
Cont_expl_var Cont. Explanatory variables
Cat_expl_var Cat. Explanatory variables
Code_out output code
Cont_blk_var Cont. block vars.
Cat_blk_var Cat. block vars.
max_dir_reuse Max # reuses a dir
Activation Act. fn choice
;
run;

/*  
RBNN(dsin ,  resp_var, layer, node, Cont_expl_var = ,  Cat_expl_var = , interact_level = 1, max_dir_reuse = 8, 
cont_blk_var = , cat_blk_var = , dsout = ttemp_out, code_out = All_code, Activation=0

%RBNN(dsin , resp_var, max_layer, max_node, Cat_expl_var = , Cont_expl_var = 
, interact_level = 1, max_dir_reuse = 8, cont_blk_var = , cat_blk_var = , 
dsout = ttemp_out, code_out = All_code, Activation=0)

*/
%macro RBNN(dsin1 ,  resp_var, max_nodes=5, max_layers=5, Cont_expl_var = ,  Cat_expl_var = , interact_level = 1, max_dir_reuse = 8, 
cont_blk_var = , cat_blk_var = , dsout = ttemp_out, code_out = All_code, Activation=0, Suppress_meta=0);

data RBNN_meta;
set RBNN_meta;
format full_value $500.;
if Macro_var='version' then full_value="&RBNN_version.";
else if Macro_var='date' then full_value=put(today(),date9.);
else if Macro_var='dsin' then full_value="&dsin1.";
else if Macro_var='resp_var' then full_value="&resp_var.";
else if Macro_var='max_nodes' then full_value="&max_nodes.";
else if Macro_var='max_layers' then full_value="&max_layers.";
else if Macro_var='Cont_expl_var' then full_value="&Cont_expl_var.";
else if Macro_var='Cat_expl_var' then full_value="&Cat_expl_var.";
else if Macro_var='Code_out' then full_value="&Code_out.";
else if Macro_var='Cont_blk_var' then full_value ="&Cont_blk_var.";
else if Macro_var='Cat_blk_var' then full_value ="&Cat_blk_var.";
else if Macro_var='max_dir_reuse' then full_value="&max_dir_reuse.";

else if Macro_var='Activation' then full_value="&Activation.";
Value=trim(left(substr(full_value,1,50)));
run;


%if &Suppress_meta. = 1 %then %do;
     title   " RBNN model information. See RBNN_meta.";
     title2  "  (Display limited to 50 characters.)";
     Proc print data=RBNN_meta( keep=pad Macro_var_desc value ) noobs label;run;
     title ; title2 ;

%end;

data rbnn_ttemp;
set &dsin1.;
run;

proc contents data=rbnn_ttemp(keep=&resp_var. &Cont_expl_var. &Cat_expl_var. &Cont_blk_var. &Cat_blk_var.) out=tvars noprint ;
run;

proc sql noprint;
select name
   into : var_mis separated by ') and ^missing('
   from tvars;
quit;

data rbnn_data;
set rbnn_ttemp(where=(^missing(&var_mis.)));
run;

/*---Wayne Added below----*/
proc sql noprint;
select count(*) into :n_obs from rbnn_data
;
quit;

%if &n_obs. ne 0 %then %do;
/*-----------------------------*/

/* lag063-lag091 */
data _null_;
do layer = 1 to 1;
	do node= 1 to &max_nodes.;
		call execute ('%nrstr(%RBNNN( ' || "rbnn_data, &resp_var., " || strip(layer) || ', ' || strip(node)
			|| ',' || "Cont_expl_var = &Cont_expl_var., Cat_expl_var = &Cat_expl_var., interact_level = &interact_level.,
			max_dir_reuse = &max_dir_reuse., cont_blk_var = &cont_blk_var. , cat_blk_var = &cat_blk_var. ,
			dsout = &dsout. , code_out = &code_out., Activation = &Activation." || '))');
	end;
end;

do layer = 2 to &max_layers.;
	do node= 1 to &max_nodes.;
		call execute ('%nrstr(%RBNNN( ' || "rbnn_data, &resp_var., " || strip(layer) || ', ' || strip(node)
			|| ',' || "Cont_expl_var = &Cont_expl_var., Cat_expl_var = &Cat_expl_var., interact_level = &interact_level.,
			max_dir_reuse = &max_dir_reuse., cont_blk_var = &cont_blk_var. , cat_blk_var = &cat_blk_var. ,
			dsout = &dsout. , code_out = &code_out., Activation = &Activation." || '))');
	end;
end;
run;

%RBNN_scorecode(rbnn_data , &resp_var., cat_blk_var = &cat_blk_var., cont_blk_var = &cont_blk_var. , code_out = &code_out.);

/*---Wayne Added below----*/
%end;
/*----------------------*/

%mend;

%macro stack_output(index_var, index_value, code_out, dsin) ;*  assumes a logit response and adds a sum to 1 constraint;

data &code_out.;
set &code_out.;
&index_var.=&index_value.;
run;

data &code_out.;
merge tracker &code_out.;
by &index_var.;
run;

data code_stack;
set code_stack &code_out.;
where &index_var. ne -1;
run;

data all_fit;
set all_fit;
&index_var.=&index_value.;
run;

data all_fit;
merge tracker all_fit;
by &index_var.;
run;

data Fit_tracker;
set Fit_tracker all_fit;
where &index_var. ne -1;
run;

proc sql noprint;
select code
into : scr_code1 separated by ' '
from &code_out.
where &index_var.=&index_value. and layer = 1;
quit;

proc sql noprint;
select code
into : scr_code2 separated by ' '
from &code_out.
where &index_var.=&index_value. and layer > 1;
quit;

data plot_out;
merge &dsin. tracker;
by &index_var.;
&scr_code1;
&scr_code2;
year=year(tran_dt);
month=month(tran_dt);

if NN_Score >= -12.5 then do; 
    Pred_Prct = 1/(1 + exp(-1*NN_score));
    Log_Pred_Prct = log(Pred_Prct);

    end;
else if ^missing(NN_Score) then do;NN_Score=-15; Pred_Prct = 0; Log_Pred_Prct=-15;end;

logit_resid = NN_score - logit;
logit_APE = abs(logit_resid/logit);

if Daily_Vol > 0 then Prct_resid = Pred_Prct - PercentVol;
else if ^missing(logit) then Prct_resid = Pred_Prct ;

Abs_Prct_resid = abs(Prct_resid);

keep &index_var. DND_NB   level Run_date Run_time Start_dt year month   DOW PercentVol logit tran_dt NN_score Pred_Prct Log_Pred_Prct train Daily_Vol Monthly_vol  Abs_Prct_resid logit_APE;
run;

proc sort data=plot_out;
by DND_NB year month;
run;

/************************************************************************************************
*   This step calculated the raw sum for the month that                                        *
*   is used to adjust the raw output from the NN to a                                          *
*   percentage that sums to 1.                                                                 *
************************************************************************************************/

proc sql noprint;
create table dnd_monthly_tot as
select
  DND_nb,
  Year,
  Month,
  sum(Pred_prct) as prct_tot
from plot_out
group by 1, 2, 3
order by 1, 2, 3;
quit;

data plot_out;
merge plot_out dmd_monthly_tot;
by DND_NB Year Month;
if prct_tot > 0 then Pred_prct = Pred_prct/prct_tot;  *<-    This step adjusts the raw NN output to a percent that sums to 1;

if Daily_Vol > 0 then Prct_resid = Pred_Prct - PercentVol;
else if ^missing(logit) then Prct_resid = Pred_Prct ;

Abs_Prct_resid = abs(Prct_resid);
drop prct_tot;
run;

proc univariate data=plot_out noprint;
by &index_var.;
class train;
var Abs_Prct_resid logit_APE PercentVol;
output out=stat n=n mean=Prct_MAE Logit_MAPE p90=Abs_Prct_p90 p95=Abs_Prct_p95 p99=Abs_Prct_p99 sum=WMAPE drop1 num_mo;
run;

data stat;
set stat;
WMAPE=WMAPE/num_mo;
drop drop1 num_mo;
run;

proc sql noprint;
create table netsize as
select
&index_var.,
max(layer) as layers,
max(node) as max_num_nodes,
sum(df) as num_presum_parms
from all_code
where layer ne 9999
group by 1;
quit;


data fit_out;
merge tracker netsize stat(where=(train=1) rename=(Logit_MAPE=Logit_MAPE_Train Prct_MAE=Prct_MAE_Train n=n_Train WMAPE=WMAPE_Train
    Abs_Prct_p90=Abs_Prct_p90_Train Abs_Prct_p95=Abs_Prct_p95_Train Abs_Prct_p99=Abs_Prct_p99_Train ) )
       stat(where=(train=0) rename=(Logit_MAPE=Logit_MAPE_Val Prct_MAE=Prct_MAE_Val n=n_Val WMAPE=WMAPE_Val
    Abs_Prct_p90=Abs_Prct_p90_Val Abs_Prct_p95=Abs_Prct_p95_Val Abs_Prct_p99=Abs_Prct_p99_Val) );
by &index_var.;
drop train;
run;

/*proc append base=Plot_stack data=plot_out force;run;*/
data Plot_stack;
set Plot_stack plot_out;
where &index_var. ne -1;
run;

data Fit_sum;
set Fit_sum fit_out;
where &index_var. ne -1;
run;

%mend;

%macro RBNNN(dsin , resp_var, layer, node, Cont_expl_var = ,  Cat_expl_var = , interact_level = 1, max_dir_reuse = 8,
cont_blk_var = , cat_blk_var = , dsout = ttemp_out, code_out = All_code, Activation=0);

/* Initialization if node and layer = 1*/
/* Should be rewritten to explicitly check both conditions and reject invalid values */
%if (%eval(&layer. + &node.) = 2) %then %do;

data &code_out.;
    Layer=0;Node=0;Hyperplane_num=0;
    New_var = put(0,z32.) || put(0,z32.) || put(0,z32.) || put(0,z9.);
    Knot=0;
    Effect=put(0,z32.) || put(0,z32.) || put(0,z32.) || put(0,z9.);
    Parameter=put(0,z32.) || put(0,z32.) || put(0,z32.) || put(0,z9.);
    DF=0;
    Estimate=0;
    StandardizedEst=0;*/
    StdErr=0;
    tValue=0;
    Probt=0;
run;

data all_fit;
    Layer=0;Node=0;
run;

data &dsout.;
    set &dsin.;
run;

ods exclude all;
proc datasets lib=work;
delete  allsig association parms  test_t xvalue temp ttemp min max parm2  knot knt knt1 beta blkvarnames respvarnames;
quit;
run;
ods exclude none;

%end;

/*  grab all previous node variables  */
/*  Need to delete the current intercept here. If code_out tracks the intercept.*/
%else %do;
    data vars;
    set &code_out.(where=(layer ne 9999)); *  9999 reserved for the final intercept;
    by layer node;
    if last.layer and last.node;* 6/23 check  was last.node only;
    call symput("exit_layer",strip(index));
    call symput("Last_code_layer",strip(layer));
    call symput("Last_code_node",strip(node));
    run;

/*  Exit the process if the only thing a layer does is summarize.  */
   %if %eval((&Last_code_layer. > 0) and (&Last_code_layer. < &layer.) and (&Last_code_node. = 2) and (&exit_layer. = -1)) %then %return;

/*   Exit the layer when there is no improvement.  */
%if %eval((&node. > 1) and (&exit_layer. = -1)) %then %return;

/*  proc print data=vars(keep=layer node effect) noobs;run;*/

/*   node variables already created for the current layer (blocking variables)  */
%if %eval(&node. > 1) %then %do;
proc sql noprint;
select distinct
    New_var
into : node_vars separated by ' '
from &code_out.
where layer=&layer. and index(New_var,'HP') = 1;
quit;

%put Current value of node_vars is &node_vars..;

data _null_;
all_cont_block_var = "&cont_blk_var." || ' ' || "&node_vars." ;
call symput('cont_blk_var', all_cont_block_var);
run;
%end;


/*   This grabs all the node variables from previous layers to used as possible */
/*   explanatory variables.  */

/*  Is this what TensorFlow calls dense?  */
%if %eval(&layer. > 1) %then %do;
proc sql noprint;
select distinct
    New_var
into : Pre_Node_vars separated by ' '
from &code_out.
where 0 < layer and layer < &layer. and index(New_var,'HP') = 1;
quit;

data _null_;
all_cont_exp_var = "&Cont_expl_var." || ' ' || "&Pre_Node_vars." ;
call symput('Cont_expl_var', all_cont_exp_var);
run;
%end;

%end;

/* The Hyperplane number tracks the number of variables being created. */
proc sql noprint;
select max(Hyperplane_num) + 1
into :Hyperplane_num
from &code_out.;
quit;


/*%let nn=1;*/
/*%let Layer=1;%let Node=1;*/
/*%let resp_var=Z;*/
/*%let Cont_blk_var= ; */
/*%let cat_blk_var = ;*/
/*%let Cont_expl_var = x y;*/

data step;
set &dsout.;
byvar=1;
NNN_rand=ranuni(98753);
run;

/* Need to track the number of blocking variables and they are counted here*/
/* The response variable is kept to make sure that the data set isn't empty*/
/* One is subtracted from the total since we don't want to count the response variable.*/
Proc contents data=step(keep = &resp_var. &cont_blk_var. &cat_blk_var.) noprint out=connts;

proc sql noprint;
select count(name) - 1
into :num_blk_var
from connts;
quit;

Proc contents data=step(keep = &cat_expl_var. &Cont_expl_var. ) noprint out=connts;

proc sql noprint;
select name
into : all_expl_var separated by ' | '
from connts;
quit;

data _null_;
layer=&layer.;
interact_level_used=min(&layer.,&interact_level.);
call symput("interact_level_used",strip(interact_level_used));
run;

/*data tt;*/
/*num_blk_var= &num_blk_var.;*/
/*run;*/
/**/
/*proc print data=tt noobs;run;*/
/*%if &layer. > 1 %then %do;%let interact_level=2;%end;*/

%put direction model statement;
%put model &resp_var. = &cont_blk_var. &cat_blk_var. &Cat_expl_var. &all_expl_var. @@&interact_level_used. /
selection= stepwise  include = &num_blk_var.;

/*title "Direction modeling for layer = &layer. and node = &node.";* zxzx ; &Cat_expl_var.*/
ods trace off;
ods exclude All;    ;
ods output ParameterEstimates=parms1a ;
proc glmselect data=step(where=(NNN_rand<1.2)) NAMELEN=105;
class &cat_blk_var. &Cat_expl_var. ;
model &resp_var. = &cont_blk_var. &cat_blk_var. &all_expl_var. @@&interact_level_used./
selection= stepwise  include = &num_blk_var. ; * MAXSTEP=20 none;
run;
ods exclude none;
title ;

/*  */
/*  */
/*  */

/* next two procs don't seem to get used*/
/*proc contents data=step(keep=&Cont_expl_var. &Cat_expl_var. ) noprint out=contents;run;*/
/**/
/*proc sql noprint;*/
/*select upcase(name) */
/*into :var_list separated by '', ''*/
/*from contents;*/
/*quit;*/

data dum;
format effect $105.;
effect = put(0,z32.) || put(0,z32.) || put(0,z32.) || put(0,z9.);
estimate=0; dum=1;ForcedIn=0;
run;

data _null_;
node=put(&node.,z3.);
layer=put(&layer.,z5.);
expl_var='PP' || layer || '_' || node;
call symput('expl_var',expl_var);
run;

data parms1a;
format effect $105.;
set parms1a;
if ForcedIn ne 1 and effect ne "Intercept" and df > 0;
run;

%glmselect_score_code(parms1a, &expl_var.);

data parms1;
set dum parms1a; * (where=( ForcedIn ne 1 and effect ne 'Intercept'  ));
if  ForcedIn ne 1 and effect ne 'Intercept' ;
run;

proc sql noprint;
select
count(estimate)-1
into : kk
from parms1;
quit;

%put current value of expl_var = &expl_var.;

data parms1 ;
set parms1 ;
format code $250.;

Layer=&layer.;Node=&node.;Hyperplane_num=&Hyperplane_num.;

if &kk. = 0 and _n_=1 then code= "&expl_var. = 0; ";

if &kk. > 0 and dum=1 then delete;
/*drop dum;*/
run;

/*title 'Code for the direction.'; */
proc sql noprint;
select code
into : code separated by ' '
from parms1 ;
quit;
title ;

data step;
set step;
&code.;
run;

**********************************;
/* Current version uses 200 knots in the range*/
proc univariate data=step(keep= &expl_var.) noprint;
var &expl_var.;
output out=knots pctlpre=kn pctlpts=0 to 100 by .5;
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


/* Define the blade variables (cx[i]) with in temp.     */
/*  cx[1] is an indicator missingness.                 */
/*  For i > 1, cx[i] is the usual RELU function        */
/*  unless the last knot condition applies             */
/*  in which case it is a step function.               */
/*  In either case cx[i] is zero for missing x.        */
/*  The merge causes the the single row of knots to    */
/*  be appended to all rows of ttemp.                  */


data step;
merge step knots;
by byvar;

	array kn[201] ;
	array minx[201];
	array maxx[201];

/*  misx = missing(&expl_var.);*/
misx=0;
do i=1 to 201;
/*    if missing(&expl_var.)      then minx[i]=0; */
/*    else */
    minx[i]= min(0, &expl_var. -  kn[i]) ;
end;

do i=1 to 201;
/*    if missing(&expl_var.)      then maxx[i]=0; */
/*    else */
    maxx[i]= max(0, &expl_var. -  kn[i]) ;
end;

keep &expl_var. &resp_var. &cont_blk_var. &cat_blk_var. misx minx1-minx201 maxx1-maxx201 byvar NNN_rand;
run;


***********************************************;
/* Main model fitting.  All block variables   */
/*  are forced into the model (even if       */
/*  insignificant). Stepwise selection is of */
/*  the cx variables. Only parameter estmates*/
/*  for the knots are saved.                 */
data _null_;
   if &Activation. = 0 then
      mod_stmnt= "model &resp_var. = &cat_blk_var. &cont_blk_var. misx minx1 - minx201 maxx1 - maxx201 /selection=stepwise include = &num_blk_var. MAXSTEP=&max_dir_reuse.";
   else if &Activation. = 1 then
      mod_stmnt= "model &resp_var. = %cat_blk_var. &cont_blk_var. misx maxx1 - maxx201 /selection=stepwise include = &num_blk_var. MAXSTEP=&max_dir_reuse.";
   else
      mod_stmnt= "model &resp_var. = %cat_blk_var. &cont_blk_var. misx minx1 - minx201 /selection=stepwise include = &num_blk_var. MAXSTEP=&max_dir_reuse.";
   call symput('mod_stmnt',mod_stmnt);
run;

%put second model statement;
%put &mod_stmnt.;


%put &num_blk_var. = &cont_blk_var.;

/*title "node modeling for layer = &layer. and node = &node.";*/
ods exclude all;  zzxx;
ods output ParameterEstimates=parms2 ;
ods output FitStatistics=FitStatistics;
proc glmselect data=step(where=(NNN_rank1<2)) NAMELEN=105;
   class &cat_blk_var. /param=glm;
   &mod_stmnt.;
run;
ods exclude none;
title ;

proc transpose data=FitStatistics out=fit;
var nValue1;
id Label1;
run;

data fit;
set fit;
layer=&layer.;
node=&node.;
run;

data All_fit;
set all_fit fit;
where layer>0;
run;

*******************************************;


data knot;
format effect $105.;
set parms2;
where ('misx' = substr(parameter,1,4)) or ('minx' = substr(parameter,1,4)) or ('maxx' = substr(parameter,1,4));

run;

data _null_;
set parms2;
where 'Intercept' = parameter;
call symput('Intercept',trim(left(estimate)));
run;

data _null_;
dsid=open("knot");
nvalue2=attrn(dsid, "nobs");
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
array kn[201];
if index > 0 then knot=kn[index]; *&expl_var_kt=kn[index];
else if index = 0 then knot = 0;* &expl_var_kt = 0;
else index=-1;

drop kn1-kn201;
run;

proc sort data=knot;
by index;
run;

********************************************;

********************************************;
data _null_;
node=put(&node.,z3.);
layer=put(&layer.,z5.);
expl_var='HP' || layer || '_' || node;
Pre_var='PP' || layer || '_' || node;
call symput('Pre_var',Pre_var);
call symput('expl_var',expl_var);
run;


data code;
set knot;
format New_var $105. code $250. Alteryx_code $250. line $150.;
New_var ="&expl_var." ;
Pre_var="&pre_var." ;
/*Parameter ="&expl_var." ;*/
Layer=&layer.;Node=&node.;Hyperplane_num=&Hyperplane_num.;
if _n_ = 1 then line = left(trim(New_var)) || ' = ';
else line = '  ';
if _n_ > &num_knts then do; end_symbol= ' ;'; a_end_symbol = '   ';end;
else do; end_symbol = ' +' ;a_end_symbol = ' + ';end;

*knot=&expl_var._kt;
beta=estimate;
num_knts=&num_knts.;

/*if _n_ > &num_knts then end= ' ;'; */
/*else end = ' + ';*/

If index > 0 then do;
code = strip(line) || strip(put(estimate,e12.)) || '*' || trim(dir) || '(0, ' || trim(Pre_var) || ' - ' || strip(knot) || ')' || end_symbol;
Alteryx_code = strip(put(estimate,e12.)) || '*' || trim(dir) || '(0, [' || trim(Pre_var) || '] - ' || strip(knot) || ')' || a_end_symbol;
end;
* code = strip(line) || strip(put(estimate,e12.)) || '*' || trim(dir) || '(0, ' || trim(Node_var) || ' - ' || strip(&expl_var._kt) || ')' || end;

If index < 0 then code=trim(New_var) || ' = 0; ' ;* This is the case when nothing is signigicant.;

keep New_var Effect Parameter code Alteryx_code layer node Hyperplane_num df Estimate
Probt StandardizedEst StdErr tValue knot index;*beta end_symbol  ;
run;
 
*******************************;

data &Code_out.;
set &Code_out.(where=(layer < 99999)) parms1(where=(dum ne 1)) code ;
drop dum;
run;

Proc sql noprint;
select code
into :code separated by ' '
from &Code_out.
where layer=&layer. and node=&node.;
quit;

data &dsout. ;
set &dsout. ;
&code.;
run;

%mend;

/*

%macro fix_cat(parm_file,var, type);
data &parm_file.;
set &parm_file.;
format t_sub $105.;
if ^missing(&var.) and "&type." = "Num" then do;
  t_sub = '('|| strip("&var.") || ' = ' || strip(&var.) || ')';
  code = tranwrd(trim(code), trim("&var."), trim(t_sub));
end;
if ^missing(&var.) and "&type." ne "Num" then do;
  t_sub = '('|| strip("&var.") || " = '" || strip(&var.) || "')";
  code = tranwrd(trim(code), trim("&var."), trim(t_sub));
end;
drop t_sub;
%mend;


/*
*/
/* %macro glmselect_score_code(parm_file); */
/*     proc sql noprint; */
/*     select count(estimate) */
/*             into : num_parms */
/*             from &parm_file. */
/*             where df > 0; */
/*     quit; */

/*     ods exclude all; */
/*     ods output variables = t_vvar; */
/*     proc contents data=&parm_file.;run; */
/*     ods exclude none; */

/*     data &parm_file.; */
/*     set &parm_file.; */
/*     where df > 0; */
/*     format code $250.; */
/*         if _n_ < &num_parms. then end_symbol = ' + '; */
/*         else end_symbol = ' ; '; */

/*         if _n_ = 1 then code='NN_Score = ' || put(estimate,e12.) || end_symbol; */
/*         else code= put(estimate,e12.) || ' * ' || strip(effect) || end_symbol; */
/*     drop end_symbol; */
/*     run; */

/*     data _null_; */
/*     set t_vvar(where=(variable not in ('Effect', 'Parameter', 'DF', 'Estimate', 'StandardizedEst', 'StdErr', 'tValue', 'Probt', 'ForcedIn'))); */
/*         call execute ('%nrstr(%fix_cat(' || "&parm_file." || ', ' || strip(variable) || ', ' || strip(type) || '))'); */
/*     run; */
/* %mend; */
/* */

%macro RBNN_scorecode(dsin , resp_var, cont_blk_var = , cat_blk_var = , code_out = All_code);

proc sql noprint;
select max(layer) 
    into : final_layer
    from &code_out.
    where df > 0;
quit;


data ttemp;
final_HP='HP' || put(&final_layer.,z5.);
call symput('Final_HP',Final_HP);
run;

/* Needs a default / skip as it can cause an exception if nothing has ever been selected.
   Maybe a work into the exit criteria */

proc sql noprint;
select distinct(New_var)
    into : final_nodes separated by ' '
    from &code_out.
    where index(New_var,"&Final_HP.") > 0 and df > 0;
quit;

proc contents data=ttemp_out(keep=&resp_var. &cont_blk_var. &cat_blk_var.) noprint out=connts;
run;

    proc sql noprint;
        select count(name) - 1
        into : num_blk_var
        from connts;
    quit;

ods exclude all;
ods output ParameterEstimates=parms_f ;
proc glmselect data=ttemp_out NAMELEN=105;
    class &cat_blk_var. /param=glm;
    model &resp_var. = &cont_blk_var. &cat_blk_var. &final_nodes. /selection=backward include = &num_blk_var. ;
run;
ods exclude none;


%glmselect_score_code(parms_f, NN_score);

data parms_f;
format effect $105.;
set parms_f;
where df > 0;
    layer=9999;
run;

data &code_out.;
set &code_out(where=(0 < layer)) parms_f;
if ^missing(estimate);

%mend;


%macro fix_cat(parm_file,var, type);
data &parm_file.;
set &parm_file.;
format t_sub $105.;

if effect = "&var." and "&type." = "Num" then do;
    T_sub = '('|| strip("&var.") || ' = ' || strip(&var.) || ')';
    code = tranwrd(code, trim("&var."), trim(T_sub));
    IF ^MISSING(&VAR.) THEN
        T_sub = '(IF ['|| strip("&var.") || '] = ' || strip(&var.) || ' THEN 1 ELSE 0 ENDIF)';
    ELSE T_sub = '(IF ISNULL( [' || strip("&var.") || ']) THEN 1 ELSE 0 ENDIF)';
    Alteryx_code = tranwrd(Alteryx_code, trim("&var."), trim(T_sub));
end;
else if index(effect, "&var.") > 0 and "&type." = "Num" then do;
    T_sub = '('|| strip("&var.") || ' = ' || strip(&var.) || ')';
    code = tranwrd(code, "&var. ", '|| trim(T_sub) || '')';
    IF ^MISSING(&VAR.) THEN
        T_sub = '(IF ['|| strip("&var.") || '] = ' || strip(&var.) || ' THEN 1 ELSE 0 ENDIF)'; 
    ELSE T_sub = '(IF ISNULL( [' || strip("&var.") || ']) THEN 1 ELSE 0 ENDIF)';
    Alteryx_code = tranwrd(Alteryx_code, "&var.", trim(T_sub));
end;

if effect = "&var." and "&type." ne "Num" then do;
    T_sub = '('|| strip("&var.") || " = '"  || strip(&var.) || "')";
    code = tranwrd(code, "&var.", trim(T_sub));
    IF ^MISSING(&VAR.) THEN
      T_sub = '(IF ['|| strip("&var.") || '] = "' || strip(&var.) || '" THEN 1 ELSE 0 ENDIF)';
    ELSE T_sub = '(IF ISNULL( ['|| strip("&var.") || '] ) THEN 1 ELSE 0 ENDIF)';
    Alteryx_code = tranwrd(Alteryx_code, "[&var.]", trim(T_sub));
  end;
else if index(effect, "&var.") > 0  and "&type." ne "Num" then do;
    T_sub = '('|| strip("&var.") || " = '" || strip(&var.) || "')";
    code = tranwrd(code, "&var. ", ' ' || trim(T_sub) || ' ' );
    IF ^MISSING(&VAR.) THEN
      T_sub = '(IF ['|| strip("&var.") || '] = "' || strip(&var.) || '" THEN 1 ELSE 0 ENDIF)';
    ELSE T_sub = '(IF ISNULL( ['|| strip("&var.") || '] ) THEN 1 ELSE 0 ENDIF)';
    Alteryx_code = tranwrd(Alteryx_code, "[&var.]", trim(T_sub));
  end;

  drop t_sub;
  run;
%mend;

%macro glmselect_score_code(parm_file, Est_name);
  proc sql noprint;
    select count(estimate)
    into : num_parms
    from &parm_file.;
    /*where df > 0;*/
  quit;

  ods trace off;
  ods exclude all;
  ods output Variables = t_vvar;
  proc contents data=&parm_file.; run;
  ods exclude none;


data &parm_file.;
set &parm_file.(rename=(effect=t_effect));
 /*where df > 0;*/
format code $250. Alteryx_code $250. effect $105. New_var $105. effect2 $105. ;

/* t_effect= tranwrd(t_effect,'_',' ') ;*/
effect= '' || tranwrd(t_effect,'*',' ') || '' ;
effect2= '[' || trim(tranwrd(t_effect,'*','] * [')) ||']') ;
New_var='&Est_name.' ;

if _n_ < &num_parms. then end_symbol = ' + ' ;
else end_symbol = ' ; ' ;

If index(effect,'Intercept')>0 then code="&Est_name.= " || put(estimate,e12.) || end_symbol;
Else if _n_ = 1 then code="&Est_name. = " || put(estimate,e12.) || ' * ' || strip(effect) || end_symbol;
 * above for noint models or cases where the intercept is dropped;
else code= put(estimate,e12.) || ' * ' || strip(effect) || end_symbol;

if _n_ < &num_parms. then end_symbol2 = ' + ' ;
else end_symbol2 = ' ; ' ;

if effect = 'Intercept' then Alteryx_code= put(estimate,e12.) || end_symbol2;
else Alteryx_code= put(estimate,e12.) || ' * ' || strip(effect2) || end_symbol2;

drop t_effect end_symbol end_symbol2 effect2 ;* ;
run;

data _null_;
set t_var(where=(variable not in ('Effect', 'Parameter', 'DF', 'Estimate', 'StandardizedEst', 'StdErr', 'tValue', 'Probt', 'ForcedIn')));
call execute ('%nrstr(%fix_cat(' || "&parm_file." || ', ' || strip(variable) || ', ' || strip(type) || '))');
run;
% mend;

%macro Alteryx_code_out(all_code_in, alteryx_code_out, code_index=);

data ACO_ttemp;
set &all_code_in.(keep=&code_index. layer node New_var Alteryx_code);
by &code_index.  layer node ;
retain order_index var;
%if "&code_index." = "" %then %do;
  if _n_ = 1 then do;
    order_index=1;
    var=new_var;
  end;
%else %do;
  if first.&code_index. then do;
    order_index=1;
    var=new_var;
  end;
%end;
else do;
  if var ne new_var then order_index=order_index + 1;
  var=new_var;
end;
run;

data &alteryx_code_out.;
set ACO_ttemp;
by &code_index. order_index;
format all_alteryx_code $7500.;
retain all_alteryx_code;
if first.order_index then all_alteryx_code = strip(alteryx_code);
else all_alteryx_code = strip(all_alteryx_code) || ' ' || strip(alteryx_code);
if ^last.order_index then delete;
drop alteryx_code;
run;

%mend;

run;

/*    Stack output assumes the following are initialized
data code_stack;
format DND_NB z6. Level $10. Run_date date9. Run_time HHMM5.;
DND_NB=-1;
Level='Daily';
Run_date=today();
Run_time=time();
run;

data Fit_sum;
format DND_NB z6. Level $10. Run_date date9. Run_time HHMM5.;
DND_NB=-1;
Level='Daily';
Run_date=today();
Run_time=time();
run;

data Fit_tracker;
format DND_NB z6. Level $10. Run_date date9. Run_time HHMM5.;
DND_NB=-1;
Level='Daily';
Run_date=today();
Run_time=time();
run;

data plot_stack;
format DND_NB z6. Level $10. Run_date date9. Run_time HHMM5.;
DND_NB = -1;
Level='Daily';
Run_date=today();
Run_time=time();
run;

data tracker;
format DND_NB z6. Level $10. Run_date date9. Run_time HHMM5.;
DND_NB = -1;
Level='Daily';
Run_date=today();
Run_time=time();
run;
*/