{# Gold dimension: one row per hour, with Europe/Berlin local calendar attributes. #}
with bounds as (
    select min(ts_utc) as lo, max(ts_utc) as hi from {{ ref('stg_smard_series') }}
),

hours as (
    select generate_series(lo, hi, interval '1 hour') as ts_utc from bounds
)

select
    ts_utc,
    (ts_utc at time zone 'Europe/Berlin') as ts_local,
    (ts_utc at time zone 'Europe/Berlin')::date as date_local,
    extract(hour from ts_utc at time zone 'Europe/Berlin')::int as hour_local,
    extract(isodow from ts_utc at time zone 'Europe/Berlin')::int as iso_weekday,
    extract(isodow from ts_utc at time zone 'Europe/Berlin') in (6, 7) as is_weekend,
    extract(month from ts_utc at time zone 'Europe/Berlin')::int as month_local,
    extract(year from ts_utc at time zone 'Europe/Berlin')::int as year_local
from hours
