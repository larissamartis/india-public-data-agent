-- One row per day, which MetricFlow needs to place periods on a calendar.
select cast(range as date) as date_day
from range(date '2000-01-01', date '2041-01-01', interval 1 day)
