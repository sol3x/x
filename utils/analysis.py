# utils/analysis.py
# نسخه ۸.۰ - ارتقای منطق تشخیص روند به تحلیل ساختار بازار (Market Structure)

import pandas as pd
import numpy as np
from datetime import datetime

from utils.news_fetcher import get_todays_high_impact_news

def find_swing_points(df, window=10): # پنجره بزرگتر برای یافتن نوسانات مهم‌تر
    """
    نقاط سقف و کف نوسانی (Swing High/Low) را در یک دیتافریم شناسایی می‌کند.
    """
    df_copy = df.copy()
    df_copy['swing_high'] = df_copy['high'][(df_copy['high'] == df_copy['high'].rolling(window, center=True, min_periods=1).max())]
    df_copy['swing_low'] = df_copy['low'][(df_copy['low'] == df_copy['low'].rolling(window, center=True, min_periods=1).min())]
    return df_copy

def get_market_structure_bias(df_bias):
    """
    جهت‌گیری روند را بر اساس ساختار بازار (سقف‌ها و کف‌های نوسانی) و شکست ساختار تعیین می‌کند.
    این تابع جایگزین منطق EMA می‌شود.
    """
    if df_bias.empty or len(df_bias) < 50: # نیاز به داده کافی برای تحلیل ساختار
        return "نامشخص"

    df = df_bias.copy()
    
    # ۱. پیدا کردن نقاط نوسانی مهم در تایم‌فریم بالا
    df = find_swing_points(df, window=10)
    
    swing_highs = df[df['swing_high'].notna()][['time', 'swing_high']].rename(columns={'swing_high': 'price'})
    swing_highs['type'] = 'high'
    
    swing_lows = df[df['swing_low'].notna()][['time', 'swing_low']].rename(columns={'swing_low': 'price'})
    swing_lows['type'] = 'low'
    
    # ۲. ترکیب و مرتب‌سازی تمام نقاط نوسانی
    swings = pd.concat([swing_highs, swing_lows]).sort_values(by='time').drop_duplicates(subset=['time', 'price']).tail(5)

    if len(swings) < 4:
        return "نامشخص" # ساختار واضحی برای تحلیل وجود ندارد

    # ۳. تحلیل ساختار بر اساس ۴ نوسان آخر
    p3, p2, p1, last_swing = swings.iloc[-4], swings.iloc[-3], swings.iloc[-2], swings.iloc[-1]

    trend = "نامشخص"
    critical_level = None

    # بررسی روند صعودی: آیا ما یک کف بالاتر (HL) و یک سقف بالاتر (HH) داریم؟
    # الگو: Low -> High -> Higher Low -> Higher High
    if p3['type'] == 'low' and p2['type'] == 'high' and p1['type'] == 'low' and last_swing['type'] == 'high':
        if last_swing['price'] > p2['price'] and p1['price'] > p3['price']:
            trend = "صعودی"
            # کفی که باعث آخرین شکست ساختار (BOS) شده است
            critical_level = p1['price'] 

    # بررسی روند نزولی: آیا ما یک سقف پایین‌تر (LH) و یک کف پایین‌تر (LL) داریم؟
    # الگو: High -> Low -> Lower High -> Lower Low
    if p3['type'] == 'high' and p2['type'] == 'low' and p1['type'] == 'high' and last_swing['type'] == 'low':
        if last_swing['price'] < p2['price'] and p1['price'] < p3['price']:
            trend = "نزولی"
            # سقفی که باعث آخرین شکست ساختار (BOS) شده است
            critical_level = p1['price']

    # ۴. بررسی شکست ساختار (Change of Character - CHOCH)
    current_close = df['close'].iloc[-1]
    
    if trend == "صعودی":
        if current_close < critical_level:
            return "نزولی" # CHOCH رخ داده، روند نزولی شد
        else:
            return "صعودی"
            
    if trend == "نزولی":
        if current_close > critical_level:
            return "صعودی" # CHOCH رخ داده، روند صعودی شد
        else:
            return "نزولی"

    return "نامشخص" # اگر هیچکدام از الگوهای واضح صعودی یا نزولی مطابقت نداشت

# ... (سایر توابع مانند find_liquidity_target, detect_fvg و غیره بدون تغییر باقی می‌مانند) ...
def find_liquidity_target(df_context, bias):
    df_with_swings = find_swing_points(df_context, window=5) # window کوچکتر برای نقدینگی
    last_price = df_with_swings['close'].iloc[-1]
    if bias == "صعودی":
        potential_ssl = df_with_swings['swing_low'].dropna()
        if not potential_ssl[potential_ssl < last_price].empty:
            closest_ssl = potential_ssl[potential_ssl < last_price].max()
            return {"level": closest_ssl, "type": "SSL"}
    elif bias == "نزولی":
        potential_bsl = df_with_swings['swing_high'].dropna()
        if not potential_bsl[potential_bsl > last_price].empty:
            closest_bsl = potential_bsl[potential_bsl > last_price].min()
            return {"level": closest_bsl, "type": "BSL"}
    return None

def find_mss_level(df_exec, target_type):
    df_with_swings = find_swing_points(df_exec.iloc[-15:], window=5)
    if target_type == 'SSL':
        return df_with_swings['swing_high'].dropna().iloc[-1] if not df_with_swings['swing_high'].dropna().empty else None
    else:
        return df_with_swings['swing_low'].dropna().iloc[-1] if not df_with_swings['swing_low'].dropna().empty else None

def detect_fvg(df_exec, bias):
    for i in range(len(df_exec) - 3, 0, -1):
        c1, c2, c3 = df_exec.iloc[i], df_exec.iloc[i+1], df_exec.iloc[i+2]
        if bias == "صعودی" and c1['high'] < c3['low']:
            return {"type": "BULLISH", "top": c3['low'], "bottom": c1['high'], "time": c2['time']}
        if bias == "نزولی" and c1['low'] > c3['high']:
            return {"type": "BEARISH", "top": c1['low'], "bottom": c3['high'], "time": c2['time']}
    return None

def is_safe_to_trade(target_currencies, min_impact, buffer_minutes):
    import pytz
    now_utc = datetime.now(pytz.utc)
    news_event_times = get_todays_high_impact_news(target_currencies, min_impact)
    if not news_event_times: return True
    buffer = pd.Timedelta(minutes=buffer_minutes)
    for event_time in news_event_times:
        if (event_time - buffer) <= now_utc <= (event_time + buffer):
            return False
    return True
