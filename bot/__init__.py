# bot/__init__.py
# این فایل پوشه 'bot' را به یک پکیج پایتون تبدیل می‌کند.
# همچنین، کلاس‌های اصلی را برای دسترسی آسان‌تر از خارج ماژول، در اینجا وارد می‌کنیم.

from .state import BotState, BotTradeState
from .trader import TradingBot
