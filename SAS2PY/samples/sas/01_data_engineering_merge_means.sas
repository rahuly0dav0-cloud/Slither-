/* SAMPLE 01 - DATA ENGINEERING / MERGE / MEANS */
libname demo "/prototype/data";

data demo.customer_master;
    set demo.raw_customers;
    length customer_segment $12;
    if missing(customer_id) then delete;
    customer_age = intck('year', date_of_birth, '31DEC2025'd);
    annual_income = coalesce(income, 0);
    if annual_income >= 100000 then customer_segment = 'PREMIUM';
    else if annual_income >= 50000 then customer_segment = 'STANDARD';
    else customer_segment = 'BASIC';
    if missing(state) then state = 'UNKNOWN';
    keep customer_id state date_of_birth customer_age annual_income customer_segment;
run;

data demo.transaction_clean;
    set demo.raw_transactions;
    transaction_amount = sum(amount, fee);
    if missing(transaction_amount) then transaction_amount = 0;
    if transaction_date < '01JAN2025'd then delete;
    month = month(transaction_date);
    year = year(transaction_date);
    keep customer_id transaction_date transaction_amount month year;
run;

proc sort data=demo.customer_master;
    by customer_id;
run;

proc sort data=demo.transaction_clean;
    by customer_id;
run;

data demo.customer_transactions;
    merge demo.customer_master(in=a) demo.transaction_clean(in=b);
    by customer_id;
    if a and b;
    high_value_txn = (transaction_amount >= 5000);
run;

proc means data=demo.customer_transactions nway noprint;
    class customer_id customer_segment;
    var transaction_amount;
    output out=demo.customer_summary
        n=transaction_count
        sum=total_transaction_amount
        mean=avg_transaction_amount
        min=min_transaction_amount
        max=max_transaction_amount;
run;

data demo.customer_summary_final;
    set demo.customer_summary;
    if transaction_count > 0 then avg_transaction_amount = total_transaction_amount / transaction_count;
    if total_transaction_amount >= 25000 then activity_flag = 'HIGH';
    else if total_transaction_amount >= 10000 then activity_flag = 'MEDIUM';
    else activity_flag = 'LOW';
    drop _TYPE_ _FREQ_;
run;
