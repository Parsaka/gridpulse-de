{{
    config(
        materialized='incremental',
        unique_key=['location', 'ts_utc'],
        on_schema_change='sync_all_columns'
    )
}}

select
    w.location,
    w.ts_utc,
    w.temperature_c,
    w.wind_speed_kmh,
    w.wind_direction_deg,
    w.cloud_cover_pct,
    w.sunshine_min,
    w.solar_kwh_m2,
    w.precipitation_mm,
    w.pressure_hpa
from {{ ref('stg_weather') }} as w
{% if is_incremental() %}
where w.ts_utc >= (select max(ts_utc) - interval '3 days' from {{ this }})
{% endif %}
