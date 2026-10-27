-- One row per metric, state or UT, and period. National rows are in fct_national_metric.
select
    long.metric_id,
    long.state_code,
    state.state_name,
    long.period_type,
    long.period_label,
    long.period_start,
    long.period_end,
    long.value,
    metric.unit,
    long.source_id,
    long.source_ref,
    long.name_as_printed,
    long.note,
    long.metric_id || '|' || long.state_code || '|' || long.period_label as row_key
from {{ ref('int_metric_long') }} as long
left join {{ ref('dim_state') }} as state using (state_code)
left join {{ ref('dim_metric') }} as metric using (metric_id)
where long.state_code is distinct from 0
