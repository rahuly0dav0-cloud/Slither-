/* SAMPLE 03 - END-TO-END DATA + GLMSELECT */
libname demo "/prototype/data";

data demo.model_population;
    set demo.raw_customers;
    if missing(customer_id) then delete;
    age = intck('year', date_of_birth, '31DEC2025'd);
    income = coalesce(annual_income, 0);
    tenure_months = max(0, intck('month', customer_since, '31DEC2025'd));
    if missing(credit_score) then credit_score = 650;
    if missing(num_products) then num_products = 0;
    if missing(balance) then balance = 0;
    log_income = log(max(income, 1));
    log_balance = log(max(balance, 1));
    if churn_flag in (0,1) then target = churn_flag;
    else target = .;
    keep customer_id target age income tenure_months credit_score num_products balance log_income log_balance state;
run;

data demo.activity_prep;
    set demo.raw_activity;
    if missing(customer_id) then delete;
    total_activity = sum(login_count, transaction_count, support_calls);
    avg_monthly_spend = mean(of spend_m1-spend_m6);
    active_months = sum((spend_m1 > 0),(spend_m2 > 0),(spend_m3 > 0),(spend_m4 > 0),(spend_m5 > 0),(spend_m6 > 0));
    keep customer_id total_activity avg_monthly_spend active_months;
run;

proc sort data=demo.model_population;
    by customer_id;
run;

proc sort data=demo.activity_prep;
    by customer_id;
run;

data demo.model_data;
    merge demo.model_population(in=a) demo.activity_prep(in=b);
    by customer_id;
    if a and b;
    if missing(total_activity) then total_activity = 0;
    if missing(avg_monthly_spend) then avg_monthly_spend = 0;
    if missing(active_months) then active_months = 0;
    high_activity = (total_activity >= 20);
    high_spend = (avg_monthly_spend >= 1000);
    interaction_income_age = income * age;
    if target ne .;
run;

proc means data=demo.model_data n mean std min p25 median p75 max noprint;
    var target age income tenure_months credit_score num_products balance total_activity avg_monthly_spend active_months;
    output out=demo.model_summary;
run;

proc glmselect data=demo.model_data plots=none;
    model target = age income tenure_months credit_score num_products balance log_income log_balance total_activity avg_monthly_spend active_months high_activity high_spend interaction_income_age
        / selection=lasso choose=cv cvmethod=block(5);
    output out=demo.lasso_output p=predicted_lasso r=residual_lasso;
run;

proc glmselect data=demo.model_data plots=none;
    model target = age income tenure_months credit_score num_products balance log_income log_balance total_activity avg_monthly_spend active_months high_activity high_spend interaction_income_age
        / selection=stepwise select=sl slentry=0.05 slstay=0.05;
    output out=demo.stepwise_output p=predicted_stepwise r=residual_stepwise;
run;
