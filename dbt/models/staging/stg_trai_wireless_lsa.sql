-- TRAI wireless (mobile) subscribers by licensed service area at month end.
select
    cast(as_of as date) as as_of,
    service_area,
    wireless_subscribers,
    _source_ref as source_ref
from {{ source('bronze', 'trai_wireless_lsa') }}
