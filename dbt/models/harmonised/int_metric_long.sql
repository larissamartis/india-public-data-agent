-- Every state-level source in one long table: metric, area, period, value.
--
-- Units are converted to those in dim_metric (money in ₹ crore; RBI GSDP arrives in ₹ lakh).
-- Periods keep their native grain and get start and end dates:
--   month      GST                 2026-08            1 Aug to 31 Aug
--   fy         RBI income tables   2023-24            1 Apr 2023 to 31 Mar 2024
--   end_march  RBI banking tables  2025-03-31         a stock on that day
--   year_jul1  population          2025               a projection for 1 July
-- Names are matched to LGD codes through ref_state_name (built in Python with the same rules
-- as the loaders); state_code 0 is the national row.

{% set gst_parts = ['total', 'cgst', 'sgst', 'igst'] %}

with gst as (
    {% for part in gst_parts %}
    select
        'gst_{{ part }}' as metric_id,
        name_as_printed,
        'month' as period_type,
        strftime(month, '%Y-%m') as period_label,
        month as period_start,
        last_day(month) as period_end,
        {{ part }} as value,
        'gst' as source_id,
        source_ref
    from {{ ref('stg_gst_state_monthly') }}
    where {{ part }} is not null
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

rbi as (
    select
        dataset as metric_id,
        name_as_printed,
        period_type,
        period as period_label,
        case
            when period_type = 'fy' then make_date(cast(left(period, 4) as integer), 4, 1)
            else try_cast(period as date)
        end as period_start,
        case
            when period_type = 'fy' then make_date(cast(left(period, 4) as integer) + 1, 3, 31)
            else try_cast(period as date)
        end as period_end,
        case when unit = '₹ lakh' then value / 100 else value end as value,
        'rbi' as source_id,
        source_ref
    from {{ ref('stg_rbi_state_annual') }}
),

population as (
    {% for metric, column in [
        ('population', 'persons_thousand'),
        ('population_male', 'male_thousand'),
        ('population_female', 'female_thousand')
    ] %}
    select
        '{{ metric }}' as metric_id,
        name_as_printed,
        'year_jul1' as period_type,
        cast(year as varchar) as period_label,
        make_date(year, 7, 1) as period_start,
        make_date(year, 7, 1) as period_end,
        cast({{ column }} as double) * 1000 as value,
        'population' as source_id,
        source_ref
    from {{ ref('stg_population_projection') }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

combined as (
    select * from gst
    union all
    select * from rbi
    union all
    select * from population
),

matched as (
    select
        combined.*,
        names.state_code as printed_state_code
    from combined
    left join {{ source('bronze', 'ref_state_name') }} as names using (name_as_printed)
)

select
    metric_id,
    -- RBI banking tables: from end-March 2020 'Dadra & Nagar Haveli' covers the merged UT.
    case
        when source_id = 'rbi' and period_type = 'end_march'
            and printed_state_code = 26 and period_end >= date '2020-03-31' then 38
        else printed_state_code
    end as state_code,
    name_as_printed,
    period_type,
    period_label,
    period_start,
    period_end,
    value,
    source_id,
    source_ref,
    case
        when source_id = 'rbi' and printed_state_code = 1 and period_end < date '2019-10-31'
            then 'Jammu and Kashmir figure includes Ladakh'
        when source_id = 'rbi' and printed_state_code = 26 and period_end >= date '2020-03-31'
            then 'Printed as Dadra and Nagar Haveli; includes Daman and Diu'
    end as note
from matched
