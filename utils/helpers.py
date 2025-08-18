# utils/helpers.py
# این ماژول شامل توابع کمکی است که در سراسر پروژه استفاده می‌شوند.

import MetaTrader5 as mt5
import requests # کتابخانه برای ارسال درخواست‌های HTTP

def parse_killzones(config):
    """
    رشته‌های زمانی مناطق کشتار را از فایل کانفیگ خوانده و به یک لیست دیکشنری تبدیل می‌کند.
    این کار به ربات اجازه می‌دهد تا بداند در چه ساعاتی باید فعال باشد.
    """
    zones = []
    kz_map = {
        "London Open": config.get('STRATEGY_SETTINGS', 'london_open_killzone'),
        "NY AM Session": config.get('STRATEGY_SETTINGS', 'ny_am_killzone'),
        "NY PM Session": config.get('STRATEGY_SETTINGS', 'ny_pm_killzone'),
    }
    for name, time_range in kz_map.items():
        if time_range:
            try:
                start, end = time_range.split('-')
                zones.append({"name": name, "start": start, "end": end})
            except ValueError:
                print(f"Warning: Invalid format for killzone '{name}'. Expected 'HH:MM-HH:MM'. Skipping.")
    return zones

def map_deal_type_to_string(deal_type):
    """
    کد عددی نوع معامله (deal) در متاتریدر را به رشته متنی خوانا تبدیل می‌کند.
    این تابع به صورت پایدار طراحی شده تا با نسخه‌های مختلف کتابخانه MT5 سازگار باشد.
    """
    type_map = {}
    
    # اضافه کردن ثابت‌ها فقط در صورت وجود در کتابخانه برای جلوگیری از خطا
    if hasattr(mt5, 'DEAL_TYPE_BUY'): type_map[mt5.DEAL_TYPE_BUY] = "Buy"
    if hasattr(mt5, 'DEAL_TYPE_SELL'): type_map[mt5.DEAL_TYPE_SELL] = "Sell"
    if hasattr(mt5, 'DEAL_TYPE_BALANCE'): type_map[mt5.DEAL_TYPE_BALANCE] = "Balance"
    if hasattr(mt5, 'DEAL_TYPE_CREDIT'): type_map[mt5.DEAL_TYPE_CREDIT] = "Credit"
    if hasattr(mt5, 'DEAL_TYPE_CHARGE'): type_map[mt5.DEAL_TYPE_CHARGE] = "Charge"
    if hasattr(mt5, 'DEAL_TYPE_CORRECTION'): type_map[mt5.DEAL_TYPE_CORRECTION] = "Correction"
    if hasattr(mt5, 'DEAL_TYPE_BONUS'): type_map[mt5.DEAL_TYPE_BONUS] = "Bonus"
    if hasattr(mt5, 'DEAL_TYPE_COMMISSION'): type_map[mt5.DEAL_TYPE_COMMISSION] = "Commission"
    if hasattr(mt5, 'DEAL_TYPE_COMMISSION_DAILY'): type_map[mt5.DEAL_TYPE_COMMISSION_DAILY] = "Commission Daily"
    if hasattr(mt5, 'DEAL_TYPE_COMMISSION_MONTHLY'): type_map[mt5.DEAL_TYPE_COMMISSION_MONTHLY] = "Commission Monthly"
    if hasattr(mt5, 'DEAL_TYPE_AGENT_DAILY'): type_map[mt5.DEAL_TYPE_AGENT_DAILY] = "Agent Daily"
    if hasattr(mt5, 'DEAL_TYPE_AGENT_MONTHLY'): type_map[mt5.DEAL_TYPE_AGENT_MONTHLY] = "Agent Monthly"
    if hasattr(mt5, 'DEAL_TYPE_INTERESTRATE'): type_map[mt5.DEAL_TYPE_INTERESTRATE] = "Interest Rate"
    if hasattr(mt5, 'DEAL_TYPE_BUY_CANCELED'): type_map[mt5.DEAL_TYPE_BUY_CANCELED] = "Buy Canceled"
    if hasattr(mt5, 'DEAL_TYPE_SELL_CANCELED'): type_map[mt5.DEAL_TYPE_SELL_CANCELED] = "Sell Canceled"
    
    return type_map.get(deal_type, f"Unknown ({deal_type})")

def map_order_type_to_string(order_type):
    """کد عددی نوع سفارش (order) در متاتریدر را به رشته متنی خوانا تبدیل می‌کند."""
    type_map = {
        mt5.ORDER_TYPE_BUY: "Buy Market",
        mt5.ORDER_TYPE_SELL: "Sell Market",
        mt5.ORDER_TYPE_BUY_LIMIT: "Buy Limit",
        mt5.ORDER_TYPE_SELL_LIMIT: "Sell Limit",
        mt5.ORDER_TYPE_BUY_STOP: "Buy Stop",
        mt5.ORDER_TYPE_SELL_STOP: "Sell Stop",
        mt5.ORDER_TYPE_BUY_STOP_LIMIT: "Buy Stop Limit",
        mt5.ORDER_TYPE_SELL_STOP_LIMIT: "Sell Stop Limit",
        mt5.ORDER_TYPE_CLOSE_BY: "Close By",
    }
    return type_map.get(order_type, f"Unknown Order ({order_type})")

def send_telegram_message(token, chat_id, message):
    """
    یک پیام متنی به یک چت تلگرام از طریق ربات ارسال می‌کند.
    این تابع برای ارسال نوتیفیکیشن‌های فوری سیگنال‌ها و خطاها استفاده می‌شود.
    """
    if not token or not chat_id or token == 'YOUR_TELEGRAM_BOT_TOKEN' or chat_id == 'YOUR_TELEGRAM_CHAT_ID':
        # اگر توکن یا چت آی‌دی به درستی تنظیم نشده باشد، از ارسال پیام صرف نظر کن.
        print("Warning: Telegram token or chat_id is not configured. Skipping notification.")
        return
        
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        # ارسال درخواست POST به API تلگرام
        response = requests.post(api_url, json={'chat_id': chat_id, 'text': message}, timeout=10)
        response.raise_for_status() # بررسی خطاهای HTTP (مانند 404 یا 500)
    except requests.exceptions.RequestException as e:
        # مدیریت خطاهای احتمالی شبکه یا API
        print(f"خطا در ارسال پیام تلگرام: {e}")
