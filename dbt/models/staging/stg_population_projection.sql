-- Projected population on 1 July, in thousands (Technical Group, Nov 2019, Table 11).
select
    year,
    state_name as name_as_printed,
    persons_thousand,
    male_thousand,
    female_thousand,
    _source_ref as source_ref
from {{ source('bronze', 'population_projection') }}
