-- Figures that a source changed or dropped since the last build. Sources revise past data
-- (GST is provisional; GSDP estimates are updated), so answers can change between builds;
-- this table says which, by how much, and since when. New periods are not revisions.
with current_values as (
    select row_key, metric_id, period_label, value from {{ ref('fct_state_metric') }}
    union all
    select row_key, metric_id, period_label, value from {{ ref('fct_national_metric') }}
)

select
    previous.row_key,
    previous.metric_id,
    previous.period_label,
    previous.value as previous_value,
    current_values.value as new_value,
    case when current_values.row_key is null then 'removed' else 'changed' end as change_type,
    previous.built_at as previous_built_at
from {{ source('bronze', 'previous_values') }} as previous
left join current_values using (row_key)
where current_values.row_key is null
    or abs(current_values.value - previous.value) > 1e-9 * greatest(1, abs(previous.value))
