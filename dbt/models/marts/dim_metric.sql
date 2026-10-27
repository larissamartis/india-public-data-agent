-- What each metric means, its unit and grain, and how states may be combined:
-- 'sum' means state values can be added; 'recompute' means a group's value must be rebuilt
-- from its parts (for example per-capita figures), never added or averaged.
select * from {{ ref('seed_metrics') }}
