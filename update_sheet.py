import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta
import os
import json
import yfinance as yf

# 1. Credentials Setup
creds_json = os.environ.get('GCP_CREDENTIALS')
creds_dict = json.loads(creds_json)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Google Sheet ID
spreadsheet_id = "1IG1VWIPdshdn8r3i2Icpj-YlKAytzfiPAY8XxA87kt0"

# ── Connect to spreadsheet object AND individual tab ──
ss        = client.open_by_key(spreadsheet_id)          # parent spreadsheet
worksheet = ss.worksheet("Top 250 Stocks")              # individual tab

# 2. NSE UDiFF Data Fetcher
def fetch_bhavcopy_for_date(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    
                    sym_col   = 'TckrSymb' if 'TckrSymb' in df.columns else 'SYMBOL'
                    close_col = 'ClsPric'  if 'ClsPric'  in df.columns else 'CLOSE'
                    series_col = 'SctySrs' if 'SctySrs'  in df.columns else 'SERIES'
                    
                    vol_col = 'TtlTradgVol'
                    for c in ['TtlTradgVol', 'TtlTrdQty', 'TotTrdQty', 'TOTTRDQTY']:
                        if c in df.columns:
                            vol_col = c
                            break
                    
                    if series_col in df.columns:
                        df = df[df[series_col].astype(str).str.strip() == 'EQ']
                    filter_keywords = 'BEES|ETF|GOLD|LIQUID|CASE|SILVER|LIQ'
                    df = df[~df[sym_col].astype(str).str.contains(filter_keywords, case=False, na=False)]
                    
                    df_top = df.sort_values(by=vol_col, ascending=False).head(250)
                    return df_top[[sym_col, vol_col, close_col]].values.tolist()
        return None
    except:
        return None

# 3. Execution Logic
date          = datetime.now()
data_to_insert = None
fetched_date_str = ""

for i in range(5):
    test_date = date - timedelta(days=i)
    if test_date.weekday() >= 5:
        continue
    data_to_insert = fetch_bhavcopy_for_date(test_date)
    if data_to_insert:
        fetched_date_str = test_date.strftime('%d-%b-%Y')
        break

# 4. Update Sheet
if data_to_insert:
    worksheet.batch_clear(['A2:C251'])
    worksheet.update(range_name='A2', values=data_to_insert)
    ist_now    = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
    status_msg = f"Data Date: {fetched_date_str} | Last Update: {ist_now} (IST)"
    worksheet.update(range_name='K2', values=[[status_msg]])
    print("SUCCESS: Sheet Updated!")
else:
    print("WARNING: No data fetched — sheet not updated.")

# ─────────────────────────────────────────
# TELEGRAM NOTIFICATION — NIFTY FINAL LIST
# ─────────────────────────────────────────

def get_nifty_final_list(spreadsheet):
    """Read Final List tab and return stocks with live prices"""
    try:
        ws_final = spreadsheet.worksheet("Final List")
        data     = ws_final.get_all_values()
        stocks   = []
        for row in data[1:]:          # skip header row
            if row[0] and row[0].strip():
                ticker = row[0].strip()
                try:
                    price_data = yf.Ticker(f"{ticker}.NS")
                    hist       = price_data.history(period="1d")
                    if not hist.empty:
                        price = round(float(hist['Close'].iloc[-1]), 2)
                        stocks.append((ticker, price))
                    else:
                        stocks.append((ticker, "N/A"))
                except Exception:
                    stocks.append((ticker, "N/A"))
        return stocks
    except Exception as e:
        print(f"  Could not read Final List: {e}")
        return []

def send_telegram(bot_token, chat_id, message):
    """Send message via Telegram bot"""
    try:
        url     = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id"    : chat_id,
            "text"       : message,
            "parse_mode" : "HTML"
        }
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print("  Telegram message sent successfully.")
        else:
            print(f"  Telegram error: {r.status_code} {r.text}")
    except Exception as e:
        print(f"  Telegram send failed: {e}")

# Get Telegram credentials from GitHub secrets
bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
chat_id   = os.environ.get('TELEGRAM_CHAT_ID')

if bot_token and chat_id:
    print("\n=== SENDING NIFTY TELEGRAM ALERT ===")

    ist_time     = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b-%Y %I:%M %p')
    nifty_stocks = get_nifty_final_list(ss)      # ← ss is now correctly defined above

    if nifty_stocks:
        lines = []
        for ticker, price in nifty_stocks:
            lines.append(f"  📌 <b>{ticker}</b>  ₹{price}")

        message = (
            f"🇮🇳 <b>NIFTY SCAN RESULTS</b>\n"
            f"🕐 {ist_time} IST\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Bull Run + CAR Buy Stocks:\n\n"
            + "\n".join(lines)
            + f"\n━━━━━━━━━━━━━━━━━━\n"
            f"📊 Total: {len(nifty_stocks)} stocks\n"
            f"⚠️ For educational purposes only"
        )
    else:
        message = (
            f"🇮🇳 <b>NIFTY SCAN RESULTS</b>\n"
            f"🕐 {ist_time} IST\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"❌ No stocks found in Bull Run + CAR Buy today.\n"
            f"⚠️ For educational purposes only"
        )

    send_telegram(bot_token, chat_id, message)
else:
    print("  Telegram secrets not found — skipping notification.")
