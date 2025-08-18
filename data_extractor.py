# data_extractor.py
# اسکریپتی برای استخراج داده‌های تاریخی از متاتریدر 5 و ذخیره آن در فایل CSV.

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import argparse
import pytz

# وارد کردن ماژول مدیریت تنظیمات از پروژه
from utils.config_manager import ConfigManager

def extract_data(symbol, timeframe_str, start_date, end_date, output_file):
    """
    به متاتریدر متصل شده، داده‌ها را استخراج و در فایل CSV ذخیره می‌کند.
    """
    try:
        # خواندن تنظیمات اتصال از config.ini
        config = ConfigManager()
        path = config.get('MT5_SETTINGS', 'path')
        login = config.getint('MT5_SETTINGS', 'login')
        password = config.get('MT5_SETTINGS', 'password')
        server = config.get('MT5_SETTINGS', 'server')
        
        # 1. اتصال به متاتریدر 5
        if not mt5.initialize(path=path, login=login, password=password, server=server):
            print(f"Initialize() failed, error code = {mt5.last_error()}")
            return

        print(f"Successfully connected to MetaTrader 5 account #{login}")

        # 2. آماده‌سازی پارامترها
        # تبدیل رشته تایم‌فریم به مقدار متغیر متاتریدر
        timeframe = getattr(mt5, f"TIMEFRAME_{timeframe_str.upper()}")
        
        # تنظیم منطقه زمانی برای درخواست داده
        timezone = pytz.timezone("Etc/UTC")
        utc_from = timezone.localize(datetime.strptime(start_date, '%Y-%m-%d'))
        utc_to = timezone.localize(datetime.strptime(end_date, '%Y-%m-%d'))

        print(f"Fetching data for {symbol} on {timeframe_str} from {start_date} to {end_date}...")

        # 3. استخراج داده‌ها
        rates = mt5.copy_rates_range(symbol, timeframe, utc_from, utc_to)

        # 4. قطع اتصال
        mt5.shutdown()
        print("Disconnected from MetaTrader 5.")

        if rates is None or len(rates) == 0:
            print("No data received from MetaTrader 5.")
            return

        # 5. تبدیل داده به دیتافریم پانداز
        df = pd.DataFrame(rates)
        # تبدیل ستون زمان از timestamp به فرمت تاریخ و زمان خوانا
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # انتخاب ستون‌های مورد نیاز برای بک‌تستر
        df_output = df[['time', 'open', 'high', 'low', 'close']]

        # 6. ذخیره در فایل CSV
        df_output.to_csv(output_file, index=False)
        print(f"Successfully saved {len(df_output)} rows to '{output_file}'")

    except FileNotFoundError:
        print("Error: config.ini not found. Make sure it's in the same directory.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # تعریف آرگومان‌های ورودی از طریق خط فرمان
    parser = argparse.ArgumentParser(description="MetaTrader 5 Historical Data Extractor")
    parser.add_argument("symbol", help="The financial symbol to extract (e.g., EURUSD).")
    parser.add_argument("timeframe", help="Timeframe (e.g., M1, M15, H1, D1).")
    parser.add_argument("start_date", help="Start date in YYYY-MM-DD format.")
    parser.add_argument("end_date", help="End date in YYYY-MM-DD format.")
    parser.add_argument("output_file", help="Name of the output CSV file (e.g., EURUSD_M1.csv).")

    args = parser.parse_args()

    # فراخوانی تابع اصلی با آرگومان‌های ورودی
    extract_data(args.symbol, args.timeframe, args.start_date, args.end_date, args.output_file)
