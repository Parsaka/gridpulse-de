select
    row_number() over (order by location) as location_key,
    location,
    latitude,
    longitude,
    region_type
from {{ ref('stg_locations') }}
