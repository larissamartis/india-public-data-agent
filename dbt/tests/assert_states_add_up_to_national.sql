-- Where a source publishes an All-India figure for an additive metric, the states and UTs
-- must add up to it within 1%. Returns the periods that do not (the test fails on any row).
with states as (
    select f.metric_id, f.period_label, sum(f.value) as states_total
    from {{ ref('fct_state_metric') }} as f
    join {{ ref('dim_metric') }} as m using (metric_id)
    where m.combine_rule = 'sum'
    group by all
)

select
    n.metric_id,
    n.period_label,
    s.states_total,
    n.value as national
from {{ ref('fct_national_metric') }} as n
join states as s using (metric_id, period_label)
where abs(s.states_total - n.value) > 0.01 * abs(n.value)
