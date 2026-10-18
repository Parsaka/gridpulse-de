-- Silver: typed, deduplicated SMARD series (latest ingestion wins).
select
    dataset,
    region,
    ts as ts_utc,
    value::numeric(14, 3) as value,
    ingested_at
from {{ source('bronze', 'smard_series') }}
where value is not null
