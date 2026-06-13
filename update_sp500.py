import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import json
import time
import requests
import io

print("===== S&P 500 UPDATE STARTED =====")

# 1. Credentials
creds_json = os.environ.get('GCP_CREDENTIALS')
if not creds_json:
    print("CRITICAL: GCP_CREDENTIALS missing!")
    exit(1)

creds_dict = json.loads(creds_json)
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 2. Your Google Sheet ID
spreadsheet_id = "1IG1VWIPdshdn8r3i2Icpj-YlKAytzfiPAY8XxA87kt0"

try:
    ss = client.open_by_key(spreadsheet_id)
    ws_sp500 = ss.worksheet("SP500 Top 250")
    print("SP500 sheet connected successfully.")
except Exception as e:
    print(f"Sheet connection error: {e}")
    exit(1)

# 3. Get LIVE S&P 500 tickers from iShares (BlackRock)
#    This is the official IVV ETF holdings file — updated every trading day
#    It always reflects the exact current S&P 500 composition automatically
def get_sp500_tickers():
    sources = [
        # Source 1: iShares IVV ETF holdings (most reliable)
        {
            "url": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=csv&fileName=IVV_holdings&dataType=fund",
            "type": "ishares"
        },
        # Source 2: SPDR SPY ETF holdings (backup)
        {
            "url": "https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-sp-500-etf-trust-spy/IVV_US.csv",
            "type": "spdr"
        }
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.ishares.com/'
    }

    # Try iShares first
    try:
        print("  Trying iShares IVV holdings file...")
        r = requests.get(sources[0]["url"], headers=headers, timeout=30)
        if r.status_code == 200:
            # iShares CSV has some header rows before the actual data
            # We skip rows until we find the actual ticker column
            content = r.text
            lines   = content.split('\n')

            # Find the line that has the column headers
            header_row = 0
            for i, line in enumerate(lines):
                if 'Ticker' in line or 'TICKER' in line:
                    header_row = i
                    break

            df = pd.read_csv(
                io.StringIO(content),
                skiprows=header_row,
                on_bad_lines='skip'
            )

            # Find ticker column
            ticker_col = next(
                (c for c in df.columns if 'ticker' in c.lower()),
                None
            )
            if ticker_col:
                tickers = (df[ticker_col]
                           .dropna()
                           .astype(str)
                           .str.strip()
                           .str.replace('.', '-', regex=False)
                           .tolist())
                # Filter out non-stock rows (cash, empty, etc.)
                tickers = [t for t in tickers
                           if t and len(t) <= 5
                           and t.upper() == t
                           and t not in ['-', 'nan', 'CASH', 'USD']]
                if len(tickers) > 400:  # S&P 500 should give ~500 tickers
                    print(f"  iShares: loaded {len(tickers)} tickers.")
                    return tickers
    except Exception as e:
        print(f"  iShares attempt failed: {e}")

    # Backup: Try fetching via yfinance's built-in S&P 500 constituent data
    try:
        print("  Trying yfinance S&P 500 constituents...")
        # yfinance can fetch index constituents for ^GSPC
        sp500_info = yf.Ticker("^GSPC")
        # Use a known working data endpoint
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            ticker_col = next(
                (c for c in df.columns if 'symbol' in c.lower() or 'ticker' in c.lower()),
                None
            )
            if ticker_col:
                tickers = (df[ticker_col]
                           .dropna()
                           .astype(str)
                           .str.strip()
                           .str.replace('.', '-', regex=False)
                           .tolist())
                tickers = [t for t in tickers if t and len(t) <= 5]
                if len(tickers) > 400:
                    print(f"  GitHub datasets: loaded {len(tickers)} tickers.")
                    return tickers
    except Exception as e:
        print(f"  GitHub datasets attempt failed: {e}")

    # Final fallback: hardcoded list (used only if all live sources fail)
    print("  WARNING: All live sources failed. Using hardcoded fallback list.")
    print("  NOTE: This fallback may be slightly outdated.")
    fallback = [
        "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD",
        "ABNB","AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG",
        "MO","AMZN","AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP",
        "AME","AMGN","APH","ADI","ANSS","AON","APA","APO","AAPL","AMAT",
        "APTV","ACGL","ADM","ANET","AJG","AIZ","T","ATO","ADSK","ADP","AZO",
        "AVB","AVY","AXON","BKR","BALL","BAC","BAX","BDX","BRK-B","BBY",
        "TECH","BIIB","BLK","BX","BA","BMY","AVGO","BR","BRO","BF-B","BLDR",
        "BSX","CHRW","CDNS","CZR","CPT","CPB","COF","CAH","KMX","CCL","CARR",
        "CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNP","CF","CRL","SCHW",
        "CHTR","CVX","CMG","CB","CHD","CI","CINF","CTAS","CSCO","C","CFG",
        "CLX","CME","CMS","KO","CTSH","CL","CMCSA","CAG","COP","ED","STZ",
        "CEG","COO","CPRT","GLW","CPAY","CTVA","CSGP","COST","CTRA","CRWD",
        "CCI","CSX","CMI","CVS","DHR","DRI","DVA","DAY","DECK","DE","DELL",
        "DAL","DVN","DXCM","FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV",
        "DOW","DHI","DTE","DUK","DD","EMN","ETN","EBAY","ECL","EIX","EW",
        "EA","ELV","EMR","ENPH","ETR","EOG","EPAM","EQT","EFX","EQIX","EQR",
        "ERIE","ESS","EL","EG","ES","EXC","EXPE","EXPD","EXR","XOM","FFIV",
        "FDS","FICO","FAST","FRT","FDX","FIS","FITB","FSLR","FE","FI","FMC",
        "F","FTNT","FTV","FOXA","FOX","BEN","FCX","GRMN","IT","GE","GEHC",
        "GEV","GEN","GNRC","GD","GIS","GM","GPC","GILD","GS","HAL","HIG",
        "HAS","HCA","DOC","HSIC","HSY","HES","HPE","HLT","HOLX","HD","HON",
        "HRL","HST","HWM","HPQ","HUBB","HUM","HBAN","HII","IBM","IEX","IDXX",
        "ITW","INCY","IR","PODD","INTC","ICE","IFF","IP","IPG","INTU","ISRG",
        "IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY","J","JNJ","JCI","JPM",
        "JNPR","K","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI","KKR","KLAC",
        "KHC","KR","LHX","LH","LRCX","LW","LVS","LDOS","LEN","LLY","LIN",
        "LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO","MPC","MKTX",
        "MAR","MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK",
        "META","MET","MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH",
        "TAP","MDLZ","MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ",
        "NTAP","NFLX","NEM","NWSA","NWS","NEE","NKE","NI","NDSN","NSC",
        "NTRS","NOC","NCLH","NRG","NUE","NVDA","NVR","NXPI","ORLY","OXY",
        "ODFL","OMC","ON","OKE","ORCL","OTIS","PCAR","PKG","PLTR","PANW",
        "PARA","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE","PCG","PM","PSX",
        "PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PRU","PEG","PTC",
        "PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF","RTX","O","REG",
        "REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST","RCL","SPGI",
        "CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM","SW",
        "SNA","SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK","SMCI",
        "SYF","SNPS","SYY","TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL",
        "TDY","TFX","TER","TSLA","TXN","TXT","TMO","TJX","TSCO","TT","TDG",
        "TRV","TRMB","TFC","TYL","TSN","USB","UBER","UDR","ULTA","UNP","UAL",
        "UPS","URI","UNH","UHS","VLO","VTR","VLTO","VRSN","VRSK","VZ","VRTX",
        "VTRS","VICI","V","VST","VMC","WRB","GWW","WAB","WBA","WMT","DIS",
        "WBD","WM","WAT","WEC","WFC","WELL","WST","WDC","WY","WHR","WMB",
        "WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
    ]
    return fallback

# 4. Find last completed US trading day
def get_last_us_trading_day():
    today_utc = datetime.utcnow().date()
    for offset in range(7):
        candidate = today_utc - timedelta(days=offset)
        if candidate.weekday() < 5:
            return candidate
    return today_utc - timedelta(days=1)

# 5. Download price + volume data
def fetch_sp500_data(tickers, trade_date):
    start = (trade_date - timedelta(days=5)).strftime("%Y-%m-%d")
    end   = (trade_date + timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"  Fetching data for {trade_date} ...")

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
            last   = df_t.iloc[-1]
            close  = round(float(last['Close']), 2)
            volume = int(last['Volume'])
            if close > 0 and volume > 0:
                records.append([ticker, volume, close])
        except Exception:
            continue

    if not records:
        print("  No data collected.")
        return None

    df_all = pd.DataFrame(records, columns=['Ticker', 'Volume', 'Close'])
    top250 = df_all.nlargest(250, 'Volume').reset_index(drop=True)
    print(f"  Top 250 ready. No.1: {top250.iloc[0].tolist()}")
    return top250.values.tolist()

# 6. Run
tickers = get_sp500_tickers()
if not tickers:
    print("FAILED: Could not load ticker list.")
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
    print(f"  Sheet updated for {trade_date}.")
else:
    print("FAILED: Could not fetch data.")
    exit(1)

print("===== S&P 500 UPDATE DONE =====")
