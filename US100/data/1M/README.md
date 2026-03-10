# M1 data

This folder stores raw 1-minute historical data downloads.

Current target:
- `US100` from Dukascopy (`usatechidxusd`)

Downloaders:
- Sample: `python -m src.data.download_dukascopy_m1_sample --symbol usatechidxusd --days 3`
- Yearly: `python -m src.data.download_dukascopy_m1_years --symbol usatechidxusd --years 2021 2022 2023 2024 2025`
