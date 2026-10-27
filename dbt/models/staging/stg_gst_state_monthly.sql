-- GST collections by state of registration, ₹ crore, provisional.
select
    fy,
    cast(month as date) as month,
    state_name as name_as_printed,
    cgst,
    sgst,
    igst,
    total,
    _source_ref as source_ref
from {{ source('bronze', 'gst_state_monthly') }}
