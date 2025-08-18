# bot/state.py
# نسخه ۸.۰ - پشتیبانی از چند نمادی و تنظیمات زنده

import threading
import logging
from enum import Enum
from collections import deque
import pandas as pd
from datetime import datetime

class BotTradeState(Enum):
    """وضعیت‌های مختلف ماشین وضعیت استراتژی را تعریف می‌کند."""
    IDLE = "غیرفعال"
    AWAITING_KILLZONE = "در انتظار منطقه کشتار"
    AWAITING_LIQUIDITY_SWEEP = "در انتظار جاروی نقدینگی"
    AWAITING_MSS = "در انتظار تغییر ساختار بازار (MSS)"
    AWAITING_ENTRY = "در انتظار ورود به معامله (FVG)"
    POSITION_OPEN = "موقعیت باز است"

class BotState:
    """
    این کلاس تمام اطلاعات وضعیت ربات را به صورت thread-safe نگهداری می‌کند.
    این کلاس به عنوان یک منبع واحد حقیقت (Single Source of Truth) بین ترد اصلی ربات
    و ترد داشbord عمل می‌کند.
    """
    def __init__(self, config):
        self.lock = threading.Lock()
        self.is_running = False
        self.status_message = "ربات متوقف است."
        
        # --- تنظیمات زنده (Live Settings) ---
        # این مقادیر از config.ini مقداردهی اولیه شده و می‌توانند در حین اجرا از داشbord تغییر کنند.
        self.live_risk_percent = config.getfloat('RISK_MANAGEMENT', 'initial_risk_percent_per_trade')
        self.live_rr_ratio = config.getfloat('RISK_MANAGEMENT', 'initial_take_profit_rr')
        
        # --- داده‌های چند نمادی (Multi-Symbol Data) ---
        # یک دیکشنری برای نگهداری وضعیت هر نماد به صورت جداگانه
        self.symbol_states = {}
        symbols = [s.strip().upper() for s in config.get('STRATEGY_SETTINGS', 'symbols').split(',')]
        for symbol in symbols:
            self.symbol_states[symbol] = {
                "trade_state": BotTradeState.IDLE,
                "daily_bias": "نامشخص",
                "target_liquidity": {"level": None, "type": None},
                "sweep_candle_info": {},
                "mss_level": None,
                "identified_fvg": {},
                "last_m1_data": pd.DataFrame(),
                "last_m15_data": pd.DataFrame(),
                # **FIX**: This list will act as the memory for used liquidity levels.
                "acted_on_liquidity_levels": [],
            }
            
        # --- متغیرهای عمومی وضعیت ---
        self.current_killzone = "خارج از محدوده"
        self.open_positions = []
        self.open_orders = []
        self.daily_trade_history = []
        self.daily_pnl = 0.0
        self.account_info = {}
        self.log_messages = deque(maxlen=200)
        self.last_signal = None  # برای نگهداری آخرین سیگنال/معامله انجام شده

    def update(self, **kwargs):
        """
        یک متد thread-safe برای به‌روزرسانی یک یا چند متغیر وضعیت.
        """
        with self.lock:
            for key, value in kwargs.items():
                if key == 'trade_state' and isinstance(value, BotTradeState):
                    self.status_message = f"وضعیت فعلی: {value.value}"
                setattr(self, key, value)

    def get_state_snapshot(self):
        """
        یک کپی ایمن از وضعیت فعلی ربات را برای استفاده در داشbord برمی‌گرداند.
        این کار از بروز مشکلات همزمانی (race conditions) جلوگیری می‌کند.
        """
        with self.lock:
            state_copy = {
                'is_running': self.is_running,
                'status_message': self.status_message,
                'live_risk_percent': self.live_risk_percent,
                'live_rr_ratio': self.live_rr_ratio,
                'symbol_states': {k: v.copy() for k, v in self.symbol_states.items()}, # کپی عمیق
                'current_killzone': self.current_killzone,
                'open_positions': list(self.open_positions),
                'open_orders': list(self.open_orders),
                'daily_trade_history': list(self.daily_trade_history),
                'daily_pnl': self.daily_pnl,
                'account_info': self.account_info.copy(),
                'log_messages': list(self.log_messages),
                'last_signal': self.last_signal.copy() if self.last_signal else None
            }
            # کپی کردن دیتافریم‌ها به صورت جداگانه
            for symbol in self.symbol_states:
                state_copy['symbol_states'][symbol]['last_m1_data'] = self.symbol_states[symbol]['last_m1_data'].copy()
                state_copy['symbol_states'][symbol]['last_m15_data'] = self.symbol_states[symbol]['last_m15_data'].copy()
            return state_copy

    def add_log(self, message, level='info'):
        """
        یک پیام جدید به لاگ‌های سیستم اضافه می‌کند (هم در حافظه و هم در فایل).
        """
        with self.lock:
            timestamp = datetime.now().strftime('%H:%M:%S')
            log_entry = f"[{timestamp}] {message}"
            self.log_messages.append(log_entry)
            if level == 'info': 
                logging.info(message)
            elif level == 'warning': 
                logging.warning(message)
            elif level == 'error': 
                logging.error(message)

# Note: The SYMBOL_STATE_TEMPLATE at the end of the original file was redundant
# as the initialization is handled within the __init__ method. 
# The fix has been applied directly in the __init__ method.
