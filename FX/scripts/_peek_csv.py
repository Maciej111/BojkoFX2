import pandas as pd
df = pd.read_csv('data/raw_dl_fx/download/m30/eurusd_m30_ask_2021_2024.csv', nrows=5)
print(df.columns.tolist())
print(df.head())

