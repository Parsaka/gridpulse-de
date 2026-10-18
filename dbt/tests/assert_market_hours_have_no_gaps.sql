-- Fails (returns rows) when the market fact has missing hours between its first and last timestamp.
{{ config(severity='warn') }}

select
    count(*) as actual_hours,
    (extract(epoch from max(ts_utc) - min(ts_utc)) / 3600)::int + 1 as expected_hours
from {{ ref('fct_market_hourly') }}
having count(*) <> (extract(epoch from max(ts_utc) - min(ts_utc)) / 3600)::int + 1
