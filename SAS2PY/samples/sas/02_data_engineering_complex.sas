/* SAMPLE 02 - COMPLEX DATA ENGINEERING */
libname demo "/prototype/data";

data demo.accounts_prep;
    set demo.raw_accounts;
    if missing(account_id) then delete;
    balance = coalesce(current_balance, 0);
    credit_limit = coalesce(credit_limit, 0);
    utilization = divide(balance, credit_limit);
    if missing(utilization) then utilization = 0;
    if utilization >= 0.90 then risk_band = 'HIGH';
    else if utilization >= 0.60 then risk_band = 'MEDIUM';
    else risk_band = 'LOW';
    active_flag = (account_status = 'ACTIVE');
    keep customer_id account_id balance credit_limit utilization risk_band active_flag open_date;
run;

data demo.customer_prep;
    set demo.raw_customers;
    if missing(customer_id) then delete;
    age = intck('year', date_of_birth, '31DEC2025'd);
    if age < 18 then age_band = 'UNDER18';
    else if age < 30 then age_band = '18_29';
    else if age < 50 then age_band = '30_49';
    else age_band = '50_PLUS';
    income = coalesce(annual_income, 0);
    if income >= 150000 then income_band = 'HIGH';
    else if income >= 75000 then income_band = 'MEDIUM';
    else income_band = 'LOW';
    keep customer_id age age_band income income_band state;
run;

proc sort data=demo.accounts_prep;
    by customer_id;
run;

proc sort data=demo.customer_prep;
    by customer_id;
run;

data demo.account_customer;
    merge demo.accounts_prep(in=acct) demo.customer_prep(in=cust);
    by customer_id;
    if acct;
    if cust = 0 then do;
        age = .;
        age_band = 'UNKNOWN';
        income = 0;
        income_band = 'UNKNOWN';
        state = 'UNKNOWN';
    end;
    debt_to_income = divide(balance, income);
    if missing(debt_to_income) then debt_to_income = 0;
    if debt_to_income >= 0.50 then dti_flag = 1;
    else dti_flag = 0;
run;

proc means data=demo.account_customer nway noprint;
    class customer_id age_band income_band;
    var balance credit_limit utilization;
    output out=demo.customer_exposure
        n=account_count
        sum(balance)=total_balance
        sum(credit_limit)=total_credit_limit
        mean(utilization)=avg_utilization;
run;

data demo.customer_level;
    set demo.customer_exposure;
    available_credit = total_credit_limit - total_balance;
    if available_credit < 0 then over_limit_flag = 1;
    else over_limit_flag = 0;
    if avg_utilization >= 0.90 then utilization_flag = 1;
    else utilization_flag = 0;
    drop _TYPE_ _FREQ_;
run;
