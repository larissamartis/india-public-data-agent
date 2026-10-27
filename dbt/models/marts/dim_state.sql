-- States and UTs keyed on LGD codes, with the dates each existed; code 0 is India.
select state_code, state_name, kind, valid_from, valid_to
from {{ source('bronze', 'ref_state') }}
