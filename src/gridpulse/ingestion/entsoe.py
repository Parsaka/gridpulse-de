"""ENTSO-E Transparency Platform wrapper (needs a free API token, see .env.example)."""

import pandas as pd

BIDDING_ZONE = "DE_LU"


def fetch_day_ahead_prices(api_key: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not api_key:
        raise RuntimeError("ENTSOE_API_KEY is not set. Request a token from ENTSO-E first.")
    from entsoe import EntsoePandasClient  # optional dependency: pip install '.[entsoe]'

    client = EntsoePandasClient(api_key=api_key)
    series = client.query_day_ahead_prices(BIDDING_ZONE, start=start, end=end)
    df = series.rename("price_eur_mwh").reset_index()
    df.columns = ["timestamp", "price_eur_mwh"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["bidding_zone"] = BIDDING_ZONE
    return df
