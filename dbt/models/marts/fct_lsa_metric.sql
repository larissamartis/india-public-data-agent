-- Telecom figures by TRAI licensed service area. Service areas are not states: several cover
-- more than one state, and Delhi, Mumbai and Kolkata are metro areas.
select
    'wireless_subscribers' as metric_id,
    service_area,
    'month_end' as period_type,
    strftime(as_of, '%Y-%m') as period_label,
    as_of as period_start,
    as_of as period_end,
    cast(wireless_subscribers as double) as value,
    'subscribers' as unit,
    'trai' as source_id,
    source_ref,
    'wireless_subscribers|' || service_area || '|' || strftime(as_of, '%Y-%m') as row_key
from {{ ref('stg_trai_wireless_lsa') }}
