# main.py
# نسخه ۸.۱ - معماری نهایی و پایدار

import logging
import webbrowser
from threading import Timer
import os

import dash
import dash_bootstrap_components as dbc
import dash_auth

from utils.config_manager import ConfigManager
from bot import BotState, TradingBot
from dashboard.layout import create_app_layout
from dashboard.callbacks import register_all_callbacks

# ==============================================================================
# بخش اصلی: اجرای برنامه
# ==============================================================================

if __name__ == '__main__':
    # تنظیمات اولیه برای ثبت وقایع در فایل
    logging.basicConfig(filename='argus_bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    try:
        # ۱. بارگذاری تنظیمات و ایجاد وضعیت ربات
        config = ConfigManager()
        bot_state = BotState(config)
        
        # ۲. پیدا کردن مسیر پوشه assets به صورت پایدار
        base_dir = os.path.dirname(os.path.abspath(__file__))
        assets_path = os.path.join(base_dir, 'assets')

        if not os.path.isdir(assets_path):
            print("="*60)
            print(f"خطای مهم: پوشه 'assets' در مسیر زیر پیدا نشد:\n{assets_path}")
            print("لطفاً این پوشه را در کنار فایل main.py بسازید و فایل style.css را در آن قرار دهید.")
            print("="*60)
            exit()
        
        print(f"پوشه assets با موفقیت در مسیر '{assets_path}' پیدا شد.")
        
        # ۳. ایجاد برنامه Dash
        app = dash.Dash(
            __name__, 
            external_stylesheets=[dbc.icons.BOOTSTRAP],
            assets_folder=assets_path,
            suppress_callback_exceptions=True
        )
        app.title = "داشبورد آرگوس ۸.۱"
        app.config.suppress_callback_exceptions = True
        
        # ۴. تنظیم لایوت اصلی برنامه
        app.layout = create_app_layout(config)
        app.config_manager = config
        
        # ۵. فعال‌سازی سیستم امنیتی (پسورد)
        USERNAME = config.get('SECURITY', 'username', fallback='admin')
        PASSWORD = config.get('SECURITY', 'password', fallback='password')
        auth = dash_auth.BasicAuth(app, {USERNAME: PASSWORD})
        
        # ۶. راه‌اندازی ترد اصلی ربات در پس‌زمینه
        trading_thread = TradingBot(config, bot_state)
        trading_thread.daemon = True
        trading_thread.start()
        
        # ۷. ثبت کردن تمام توابع واکنش‌گرا (Callbacks)
        register_all_callbacks(app, bot_state, trading_thread)
        
        print("="*60)
        print("ربات معامله‌گر آرگوس نسخه ۸.۱ (طراحی حرفه‌ای)")
        print("برای دسترسی به داشبورد، آدرس زیر را در مرورگر خود باز کنید:")
        print(f"http://<Your_VPS_Public_IP>:8050")
        print("="*60)

        # ۸. اجرای سرور داشبورد
        app.run(debug=False, host='0.0.0.0', port=8050)

    except FileNotFoundError as e:
        print(f"خطا: {e}")
        logging.error(f"خطا: {e}")
    except Exception as e:
        print(f"یک خطای پیش‌بینی نشده رخ داد: {e}")
        logging.critical(f"یک خطای پیش‌بینی نشده رخ داد: {e}", exc_info=True)
