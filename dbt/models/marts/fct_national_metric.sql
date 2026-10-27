-- All-India rows as published by the source (not computed by adding states).
select
    long.metric_id,
    long.period_type,
    long.period_label,
    long.period_start,
    long.period_end,
    long.value,
    metric.unit,
    long.source_id,
    long.source_ref,
    long.metric_id || '|' || long.period_label as row_key
from {{ ref('int_metric_long') }} as long
left join {{ ref('dim_metric') }} as metric using (metric_id)
where long.state_code = 0
