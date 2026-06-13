import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import json
import time

print("===== S&P 500 UPDATE STARTED =====")

# 1. Credentials — uses the same GCP_CREDENTIALS secret you already have
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    print("CRITICAL: GCP_CREDENTIALS missing!")
    exit(1)

creds_dict = json.loads(creds_json)
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 2. Your Google Sheet ID — paste the same ID you used in update_sheet.py
spreadsheet_id = "1IG1VWIPdshdn8r3i2Icpj-YlKAytzfiPAY8XxA87kt0"

try:
    ss = client.open_by_key(spreadsheet_id)
    ws_sp500 = ss.worksheet("SP500 Top 250")
    print("SP500 sheet connected successfully.")
except Exception as e:
    print(f"Sheet connection error: {e}")
    exit(1)

# 3. Get list of all S&P 500 tickers from Wikipedia (free, no API needed)
def get_sp500_tickers():
    try:
        table = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            header=0
        )[0]
        tickers = (table['Symbol']
                   .str.strip()
                   .str.replace('.', '-', regex=False)
                   .tolist())
        print(f"  Loaded {len(tickers)} S&P 500 tickers.")
        return tickers
    except Exception as e:
        print(f"  Could not load ticker list: {e}")
        return None

# 4. Find the last completed US trading day
#    At 6 AM IST = 12:30 AM UTC, US market closed 8+ hours ago safely
def get_last_us_trading_day():
    today_utc = datetime.utcnow().date()
    for offset in range(7):
        candidate = today_utc - timedelta(days=offset)
        if candidate.weekday() < 5:  # 0=Monday, 4=Friday
            return candidate
    return today_utc - timedelta(days=1)

# 5. Download price + volume data for all tickers
def fetch_sp500_data(tickers, trade_date):
    start = (trade_date - timedelta(days=5)).strftime("%Y-%m-%d")
    end   = (trade_date + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"  Fetching data for {trade_date} (window: {start} to {end}) ...")

    try:
        raw = yf.download(
            tickers,
            start=start,
            end=end,
            group_by='ticker',
            auto_adjust=True,
            progress=False,
            threads=True
        )
        time.sleep(2)
    except Exception as e:
        print(f"  Download error: {e}")
        return None

    records = []
    for ticker in tickers:
        try:
            if ticker not in raw.columns.get_level_values(0):
                continue
            df_t = raw[ticker].dropna(how='all')
            if df_t.empty:
                continue
            last     = df_t.iloc[-1]
            close    = round(float(last['Close']), 2)
            volume   = int(last['Volume'])
            if close > 0 and volume > 0:
                records.append([ticker, volume, close])
        except Exception:
            continue

    if not records:
        print("  No data collected.")
        return None

    df_all = pd.DataFrame(records, columns=['Ticker', 'Volume', 'Close'])
    top250 = df_all.nlargest(250, 'Volume').reset_index(drop=True)
    print(f"  Top 250 ready. No.1 stock: {top250.iloc[0].tolist()}")
    return top250.values.tolist()

# 6. Run it all
tickers = get_sp500_tickers()
if not tickers:
    print("FAILED: Could not load S&P 500 ticker list.")
    exit(1)

trade_date = get_last_us_trading_day()
print(f"  Target date: {trade_date}")

sp500_data = fetch_sp500_data(tickers, trade_date)

if sp500_data:
    ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
    status  = f"Data: {trade_date.strftime('%d-%b-%Y')} | Updated: {ist_now} IST"

    ws_sp500.batch_clear(['A2:C251'])
    ws_sp500.update('A2', sp500_data)
    ws_sp500.update('K2', [[status]])
    print(f"  Sheet updated successfully for {trade_date}.")
else:
    print("FAILED: Could not fetch S&P 500 data.")
    exit(1)

print("===== S&P 500 UPDATE DONE =====")
