# GridPulse DE in plain language

*One page for people who do not work with data. Numbers are measured on one year of German
day-ahead electricity prices (Oct 2025 to Oct 2026). Generated from the analysis; details and
caveats are in [analysis.md](analysis.md).*

## The question
Can a computer forecast of tomorrow's electricity prices, built only from public data, make a
battery (or any flexible electricity user) earn or save more money than a very simple guess?

## The short answer
* **The forecast is more accurate:** its average error is 22% lower than the guess
  "tomorrow looks like today".
* **That did not make a small battery richer.** The extra accuracy did not show up in revenue.
* **A very simple method did better:** averaging the last four weeks by hour of day earned
  about 3,735 EUR more per MW and year than "like yesterday", with no model at all.
* **Lesson:** judge a forecast by the decision it supports, not by its error.

## What decides the price
* **Wind and sun.** Every extra gigawatt of wind or solar lowers the price by about
  3.0 to 3.3 EUR per MWh. Wind and solar explain far more of the price than the
  hour of the day or the temperature.
* **A sunny weekend midday** is the cheapest time (19 EUR/MWh on average, negative half the time).
* **A calm winter evening** is the most expensive (165 EUR/MWh on average).
* **Prices are higher than a year ago** for the same weather and demand (about +70 EUR/MWh).
  Likely fuel and carbon costs, which this project does not measure.

## What it means for different readers
| If you are... | Takeaway |
|---|---|
| A solar owner | Your power sells at about 54% of the average price, as low as 26% in spring. Midday is crowded. |
| A factory or EV fleet that can shift load | Running in the cheapest four hours instead of all day cuts the energy price by about 56%. Prices are published the day before: no forecast needed. |
| A battery owner | Earnings are seasonal (447 EUR/day in the best month, 87 in the worst) and depend on a few extreme days. |
| A power buyer | The risk sits in a few evening hours with little wind. |

## When to trust the forecast
* **More:** when the weather changes from yesterday, in spring, on sunny or windy days.
* **Less:** in winter, when the weather is the same as yesterday, and the day after an extreme
  price. On the 57 hours above 300 EUR/MWh the model averaged 261 against an actual 388.

## What this project is not
A personal portfolio project on open data. It is not trading or investment advice; it uses
day-ahead energy prices only (no grid fees, taxes or intraday trading), one market and one year.
