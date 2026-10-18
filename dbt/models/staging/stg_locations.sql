select location, latitude, longitude, region_type
from {{ ref('locations') }}
