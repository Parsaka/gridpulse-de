{{
    config(
        materialized='incremental',
        unique_key='ts_utc',
        on_schema_change='sync_all_columns'
    )
}}

{# Gold fact: one row per hour for the DE-LU market, wide by generation source. #}
{% set renewables = [
    'wind_offshore', 'wind_onshore', 'solar', 'biomass', 'hydro', 'other_renewable'
] %}
{% set conventionals = [
    'lignite', 'hard_coal', 'gas', 'nuclear', 'other_conventional', 'pumped_storage'
] %}

with src as (
    select * from {{ ref('stg_smard_series') }}
    {% if is_incremental() %}
    -- re-process a 3 day window: SMARD revises recent values
    where ts_utc >= (select max(ts_utc) - interval '3 days' from {{ this }})
    {% endif %}
),

pivoted as (
    select
        ts_utc,
        max(case when dataset = 'price_day_ahead' then value end) as price_eur_mwh,
        max(case when dataset = 'load_total' then value end) as load_mwh,
        max(case when dataset = 'load_residual' then value end) as residual_load_mwh,
        {% for s in renewables + conventionals %}
        max(case when dataset = 'generation_{{ s }}' then value end) as gen_{{ s }}_mwh
        {%- if not loop.last %},{% endif %}
        {% endfor %}
    from src
    group by ts_utc
)

select
    ts_utc,
    price_eur_mwh,
    load_mwh,
    residual_load_mwh,
    {% for s in renewables + conventionals %}
    gen_{{ s }}_mwh,
    {% endfor %}
    {% for group, items in [('renewable', renewables), ('conventional', conventionals)] %}
    ({% for s in items %}coalesce(gen_{{ s }}_mwh, 0){% if not loop.last %} + {% endif %}{% endfor %})
        as gen_{{ group }}_mwh,
    {% endfor %}
    case
        when (
            {% for s in renewables + conventionals %}coalesce(gen_{{ s }}_mwh, 0){% if not loop.last %} + {% endif %}{% endfor %}
        ) > 0
        then ({% for s in renewables %}coalesce(gen_{{ s }}_mwh, 0){% if not loop.last %} + {% endif %}{% endfor %})
            / ({% for s in renewables + conventionals %}coalesce(gen_{{ s }}_mwh, 0){% if not loop.last %} + {% endif %}{% endfor %})
    end as renewable_share
from pivoted
