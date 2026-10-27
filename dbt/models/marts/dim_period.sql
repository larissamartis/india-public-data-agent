-- Every period that appears in the facts, with its start and end dates.
select distinct period_type, period_label, period_start, period_end
from (
    select period_type, period_label, period_start, period_end from {{ ref('fct_state_metric') }}
    union all
    select period_type, period_label, period_start, period_end from {{ ref('fct_national_metric') }}
    union all
    select period_type, period_label, period_start, period_end from {{ ref('fct_lsa_metric') }}
)
