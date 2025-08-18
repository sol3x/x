# utils/analytics.py
# فایل جدید برای محاسبه معیارهای عملکرد از تاریخچه معاملات ثبت شده.

import pandas as pd
import numpy as np

def calculate_performance_metrics(df):
    """
    یک دیتافریم از تاریخچه معاملات را دریافت کرده و معیارهای کلیدی عملکرد را محاسبه می‌کند.
    این تابع قلب تب "آمار و عملکرد" در داشبورد است.
    
    Args:
        df (pd.DataFrame): دیتافریم شامل تاریخچه معاملات با ستون‌های 'profit' و 'time_close'.

    Returns:
        dict: یک دیکشنری شامل تمام معیارهای محاسبه شده.
              None را برمی‌گرداند اگر دیتافریم ورودی خالی باشد.
    """
    if df.empty:
        return None

    # فرض یک بالانس اولیه برای محاسبه منحنی سرمایه
    initial_balance = 10000 
    df['cumulative_pnl'] = df['profit'].cumsum()
    df['equity'] = initial_balance + df['cumulative_pnl']

    total_trades = len(df)
    wins = df[df['profit'] > 0]
    losses = df[df['profit'] <= 0]
    
    # محاسبه نرخ برد (Win Rate)
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    
    # محاسبه سود و زیان ناخالص
    gross_profit = wins['profit'].sum()
    gross_loss = abs(losses['profit'].sum())
    
    # محاسبه فاکتور سود (Profit Factor)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    
    # محاسبه حداکثر افت سرمایه (Maximum Drawdown)
    peak = df['equity'].cummax()
    drawdown = (df['equity'] - peak) / peak
    max_drawdown = abs(drawdown.min()) * 100
    
    # آماده‌سازی دیکشنری خروجی با فرمت‌بندی مناسب
    metrics = {
        "total_trades": total_trades,
        "win_rate": f"{win_rate:.2f}%",
        "profit_factor": f"{profit_factor:.2f}",
        "max_drawdown": f"{max_drawdown:.2f}%",
        "net_profit": f"{df['profit'].sum():,.2f}",
        "avg_win": f"{wins['profit'].mean():,.2f}" if not wins.empty else "0.00",
        "avg_loss": f"{losses['profit'].mean():,.2f}" if not losses.empty else "0.00",
    }
    
    return metrics
