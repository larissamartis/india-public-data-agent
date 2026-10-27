-- Which metric exists for which state and over which periods. The agent checks this before
-- writing any SQL, so it can say what is available instead of guessing.
select
    metric_id,
    state_code,
    state_name,
    period_type,
    count(*) as periods,
    min(period_start) as first_period,
    max(period_end) as last_period
from {{ ref('fct_state_metric') }}
group by all

union all

select
    metric_id,
    0 as state_code,
    'India' as state_name,
    period_type,
    count(*) as periods,
    min(period_start) as first_period,
    max(period_end) as last_period
from {{ ref('fct_national_metric') }}
group by all
