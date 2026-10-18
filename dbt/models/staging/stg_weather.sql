-- Silver: hourly weather with explicit units and plausibility filtering.
select
    location,
    ts as ts_utc,
    temperature as temperature_c,
    wind_speed as wind_speed_kmh,
    wind_direction as wind_direction_deg,
    cloud_cover as cloud_cover_pct,
    sunshine as sunshine_min,
    solar as solar_kwh_m2,
    precipitation as precipitation_mm,
    pressure_msl as pressure_hpa,
    ingested_at
from {{ source('bronze', 'dwd_weather') }}
where temperature is null or temperature between -50 and 60
