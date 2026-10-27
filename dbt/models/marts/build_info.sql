-- One row describing this build: the data version that answers and benchmark gold values
-- are tied to.
select
    current_timestamp::timestamp as built_at,
    '{{ env_var("GITHUB_SHA", "local") }}' as git_sha,
    '{{ env_var("GITHUB_RUN_ID", "local") }}' as run_id,
    (select count(*) from {{ ref('fct_state_metric') }}) as state_rows,
    (select count(*) from {{ ref('fct_national_metric') }}) as national_rows,
    (select count(*) from {{ ref('revisions') }}) as revisions
