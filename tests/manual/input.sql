WITH src AS (
    select id, region, amount FROM events WHERE day=:Calc_Date
)
select d.region, sum(d.amount), row_number() over (partition by d.region order by sum(d.amount) desc) rn
FROM (
    SELECT id,region,amount FROM src
    WHERE id IN (SELECT id FROM allowed WHERE branch=:Branch)
    UNION ALL
    SELECT id,region,amount FROM archive WHERE day=add_months(:Calc_Date,-2)
    /* derived end */
) d
-- join note
LEFT JOIN flags f ON d.id=f.id AND f.kind=:Flag
-- filter note
WHERE d.amount>:Min AND d.id IS NOT NULL
GROUP BY 1
HAVING sum(d.amount)>:Total
ORDER BY 1;
