{# Gold: one row per UTC hour, simple mean across the nine regional stations. #}
select
    ts_utc,
    count(*) as stations,
    avg(temperature_c) as temperature_c,
    avg(wind_speed_kmh) as wind_speed_kmh,
    avg(cloud_cover_pct) as cloud_cover_pct,
    avg(solar_kwh_m2) as solar_kwh_m2,
    avg(precipitation_mm) as precipitation_mm
from {{ ref('fct_weather_hourly') }}
group by ts_utc
