"""Extract monthly European gas and Australian coal prices from the World Bank Pink Sheet.

Usage: python scripts/update_fuel_prices.py <url-or-path-to-CMO-Historical-Data-Monthly.xlsx>
Output: data_static/fuel_prices_monthly.csv (committed). Needs openpyxl.
Source: World Bank Commodity Price Data (The Pink Sheet), CC BY 4.0. The download URL changes with
each release; find the current one at https://www.worldbank.org/en/research/commodity-markets.
"""

import sys
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd


def main(src: str) -> None:
    path = src
    if src.startswith("http"):
        path = str(Path(tempfile.mkdtemp()) / "pink.xlsx")
        urllib.request.urlretrieve(src, path)  # noqa: S310
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    names = raw.iloc[4].tolist()
    gas = names.index("Natural gas, Europe")
    coal = names.index("Coal, Australian")
    t = raw.iloc[6:, [0, gas, coal]].copy()
    t.columns = ["month", "gas_europe_usd_mmbtu", "coal_australia_usd_t"]
    t["month"] = t["month"].astype(str).str.replace("M", "-", regex=False)
    t = t[t["month"] >= "2024-01"].dropna()
    t[["gas_europe_usd_mmbtu", "coal_australia_usd_t"]] = t[
        ["gas_europe_usd_mmbtu", "coal_australia_usd_t"]
    ].astype(float)
    out = Path("data_static/fuel_prices_monthly.csv")
    out.parent.mkdir(exist_ok=True)
    t.to_csv(out, index=False)
    print(f"wrote {len(t)} months to {out}: {t['month'].min()} to {t['month'].max()}")


if __name__ == "__main__":
    main(sys.argv[1])
