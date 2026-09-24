/* SAMPLE 05 - PROC SQL JOINS & AGGREGATION
   Edge cases for the converter:
     - PROC SQL create-table-as with multi-table INNER/LEFT JOIN
     - correlated subquery in the WHERE clause
     - CASE WHEN, GROUP BY ... HAVING, COALESCE, and a UNION
     - a macro variable interpolated into the SQL text
*/
libname demo "/prototype/data";

%let min_orders = 2;

proc sql;
    /* customers enriched with their home region name via a lookup join */
    create table demo.cust_enriched as
    select  c.customer_id,
            c.signup_date,
            coalesce(r.region_name, 'UNMAPPED') as region_name length=20,
            case when c.loyalty_points >= 1000 then 'GOLD'
                 when c.loyalty_points >=  250 then 'SILVER'
                 else 'BRONZE'
            end as loyalty_tier length=6
    from    demo.raw_customers as c
    left join demo.raw_regions as r
           on c.region_code = r.region_code;

    /* order lines rolled up to one row per order */
    create table demo.order_rollup as
    select  o.order_id,
            o.customer_id,
            o.order_date,
            sum(l.quantity * l.unit_price) as order_value,
            count(distinct l.product_id)   as n_products
    from    demo.raw_orders as o
    inner join demo.raw_order_lines as l
           on o.order_id = l.order_id
    group by o.order_id, o.customer_id, o.order_date;

    /* customer-level summary, keeping only repeat buyers (HAVING) */
    create table demo.customer_value as
    select  e.customer_id,
            e.region_name,
            e.loyalty_tier,
            count(rb.order_id)      as n_orders,
            sum(rb.order_value)     as total_value,
            mean(rb.order_value)    as avg_order_value
    from    demo.cust_enriched as e
    inner join demo.order_rollup as rb
           on e.customer_id = rb.customer_id
    group by e.customer_id, e.region_name, e.loyalty_tier
    having  count(rb.order_id) >= &min_orders;

    /* customers who spent more than their region's average (subquery) */
    create table demo.above_region_avg as
    select  cv.customer_id,
            cv.region_name,
            cv.total_value
    from    demo.customer_value as cv
    where   cv.total_value >
            ( select mean(inner_cv.total_value)
              from   demo.customer_value as inner_cv
              where  inner_cv.region_name = cv.region_name );

    /* a small UNION: flag the extreme ends of the value distribution */
    create table demo.value_flags as
    select customer_id, 'TOP'    as flag length=6 from demo.customer_value
        where total_value >= 5000
    union
    select customer_id, 'BOTTOM' as flag length=6 from demo.customer_value
        where total_value <  200
    order by flag, customer_id;
quit;
