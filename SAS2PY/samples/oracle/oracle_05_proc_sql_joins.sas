/*======================================================================
  SAS ORACLE #05  --  dummy data + ground truth for sample 05
  (PROC SQL joins & aggregation)

  Self-contained: inlines the four raw tables, runs the SAME PROC SQL
  as samples/sas/05_proc_sql_joins.sas, and exports the key outputs.

  Set OUTDIR first:  %let outdir = /tmp/sas_oracle/05;
======================================================================*/
%let outdir = /tmp/sas_oracle/05;
%let min_orders = 2;

libname demo (work);

data demo.raw_customers;
    infile datalines dsd truncover;
    input customer_id signup_date :date9. region_code :$4. loyalty_points;
    format signup_date date9.;
    datalines;
1,05JAN2024,N1,1200,
2,12FEB2024,S2,300,
3,20MAR2024,N1,50,
4,01APR2024,E3,900,
5,15MAY2024,ZZ,1500,
;
run;

data demo.raw_regions;
    infile datalines dsd truncover;
    input region_code :$4. region_name :$20.;
    datalines;
N1,North
S2,South
E3,East
;
run;

data demo.raw_orders;
    infile datalines dsd truncover;
    input order_id customer_id order_date :date9.;
    format order_date date9.;
    datalines;
101,1,10JAN2024
102,1,15FEB2024
103,2,20FEB2024
104,3,25MAR2024
105,4,01MAY2024
106,4,10MAY2024
107,5,15MAY2024
108,5,20MAY2024
;
run;

data demo.raw_order_lines;
    infile datalines dsd truncover;
    input order_id product_id quantity unit_price;
    datalines;
101,10,2,50
101,11,1,300
102,10,5,50
103,12,1,120
104,13,3,20
105,14,2,2500
106,15,1,80
107,16,1,60
108,17,1,90
;
run;

proc sql;
    create table demo.cust_enriched as
    select  c.customer_id, c.signup_date,
            coalesce(r.region_name, 'UNMAPPED') as region_name length=20,
            case when c.loyalty_points >= 1000 then 'GOLD'
                 when c.loyalty_points >=  250 then 'SILVER'
                 else 'BRONZE' end as loyalty_tier length=6
    from demo.raw_customers as c
    left join demo.raw_regions as r on c.region_code = r.region_code;

    create table demo.order_rollup as
    select  o.order_id, o.customer_id, o.order_date,
            sum(l.quantity * l.unit_price) as order_value,
            count(distinct l.product_id)   as n_products
    from demo.raw_orders as o
    inner join demo.raw_order_lines as l on o.order_id = l.order_id
    group by o.order_id, o.customer_id, o.order_date;

    create table demo.customer_value as
    select  e.customer_id, e.region_name, e.loyalty_tier,
            count(rb.order_id)   as n_orders,
            sum(rb.order_value)  as total_value,
            mean(rb.order_value) as avg_order_value
    from demo.cust_enriched as e
    inner join demo.order_rollup as rb on e.customer_id = rb.customer_id
    group by e.customer_id, e.region_name, e.loyalty_tier
    having count(rb.order_id) >= &min_orders;

    create table demo.above_region_avg as
    select cv.customer_id, cv.region_name, cv.total_value
    from demo.customer_value as cv
    where cv.total_value >
          ( select mean(inner_cv.total_value) from demo.customer_value as inner_cv
            where inner_cv.region_name = cv.region_name );

    create table demo.value_flags as
    select customer_id, 'TOP'    as flag length=6 from demo.customer_value where total_value >= 5000
    union
    select customer_id, 'BOTTOM' as flag length=6 from demo.customer_value where total_value <  200
    order by flag, customer_id;
quit;

%macro dump(ds); proc export data=demo.&ds outfile="&outdir/&ds..csv" dbms=csv replace; run; %mend;
%dump(customer_value);
%dump(above_region_avg);
%dump(value_flags);
