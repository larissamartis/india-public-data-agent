-- RBI Handbook tables: one row per table (dataset), state and period, in the table's own unit.
select
    dataset,
    unit,
    period,
    period_type,
    state_name as name_as_printed,
    value,
    _source_ref as source_ref
from {{ source('bronze', 'rbi_state_annual') }}
