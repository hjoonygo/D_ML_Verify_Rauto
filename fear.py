import requests, pandas as pd
r = requests.get("https://api.alternative.me/fng/?limit=0&format=json", timeout=15)
data = r.json()['data']
df = pd.DataFrame(data)
df['timestamp'] = df['timestamp'].astype(int)
df['value'] = df['value'].astype(int)
df = df[['timestamp','value','value_classification']].sort_values('timestamp')
df.to_csv(r"D:\ML\verify\Fear_Greed_Index_Clean.csv", index=False, encoding='utf-8')
print(len(df), "일 |", 
      pd.to_datetime(df.timestamp.iloc[0],unit='s').date(), "~",
      pd.to_datetime(df.timestamp.iloc[-1],unit='s').date())