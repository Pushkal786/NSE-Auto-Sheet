import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import requests
import zipfile
import io
import time
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
ss        = client.open
