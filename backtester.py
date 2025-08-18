# backtester.py
# نسخه ۸.۶ - افزودن منطق تایم‌اوت سفارشات معلق

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta # افزودن timedelta
import pytz

# --- وارد کردن توابع و کلاس‌های مورد نیاز ---
from utils.analysis import get_market_structure_bias, find_liquidity_target, find_mss_level, detect_fvg
from utils.helpers import parse_killzones
from utils.config_manager import ConfigManager
from bot.state import BotTradeState

class Backtester:
    def __init__(self, m15_data, m1_data, h4_data, config):
        """
        کلاس بک‌تستر را با تمام داده‌های مورد نیاز مقداردهی اولیه می‌کند.
        """
        self.m15_data = m15_data
        self.m1_data = m1_data
        self.h4_data = h4_data
        self.config = config
        
        # پارامترهای شبیه‌سازی
        self.balance = 10000
        self.risk_percent = config.getfloat('RISK_MANAGEMENT', 'initial_risk_percent_per_trade') / 100
        self.rr = config.getfloat('RISK_MANAGEMENT', 'initial_take_profit_rr')
        self.trades = []
        self.equity_curve = [self.balance]
        
        # **جدید**: خواندن تنظیمات تایم‌اوت از کانفیگ
        self.order_timeout_minutes = config.getint('TRADING_RULES', 'order_timeout_minutes', fallback=60)
        if self.order_timeout_minutes > 0:
            self.order_timeout_delta = timedelta(minutes=self.order_timeout_minutes)
        else:
            self.order_timeout_delta = None

        # تنظیمات زمانی
        self.ny_tz = pytz.timezone('America/New_York')
        self.killzones = parse_killzones(config)
        
        # ماشین وضعیت
        self.trade_state = BotTradeState.AWAITING_KILLZONE
        self.daily_bias = None
        self.target_liquidity = {}
        self.sweep_candle_info = {}
        self.mss_level = None
        self.pending_order = None
        
        self.acted_on_liquidity_levels = []
        self.last_processed_date = None


    def run(self):
        """حلقه اصلی بک‌تست را بر روی هر کندل M1 اجرا می‌کند."""
        open_trade = None
        
        for i in range(50, len(self.m1_data) - 1):
            current_candle_m1 = self.m1_data.iloc[i]
            current_time = current_candle_m1['time'].to_pydatetime().astimezone(self.ny_tz)
            recent_m1_slice = self.m1_data.iloc[i-15:i]

            current_date = current_time.date()
            if self.last_processed_date and current_date > self.last_processed_date:
                print(f"\n--- New Day: {current_date.strftime('%Y-%m-%d')} ---")
                self.acted_on_liquidity_levels = []
                print("Liquidity memory has been reset.")
            self.last_processed_date = current_date


            if open_trade:
                if self._check_close_conditions(i, open_trade):
                    open_trade = None 
                continue
            
            is_kz, _ = self._is_in_killzone(current_time)

            if not is_kz:
                if self.trade_state != BotTradeState.AWAITING_KILLZONE:
                    self._reset_cycle()
                # **جدید**: اگر سفارشی معلق است و از کیل‌زون خارج شدیم، آن را لغو کن
                if self.pending_order:
                    print(f"[{current_time.strftime('%H:%M')}] Exited killzone. Cancelling pending order.")
                    self.pending_order = None # لغو سفارش
                continue
            
            # --- منطق ماشین وضعیت ---

            if self.trade_state == BotTradeState.AWAITING_KILLZONE:
                relevant_h4 = self.h4_data[self.h4_data['time'] <= current_candle_m1['time']]
                if relevant_h4.empty: continue

                self.daily_bias = get_market_structure_bias(relevant_h4)
                print(f"\n[{current_time.strftime('%Y-%m-%d %H:%M')}] Entering Killzone. Bias is now {self.daily_bias}.")
                self.trade_state = BotTradeState.AWAITING_LIQUIDITY_SWEEP
            
            if self.trade_state == BotTradeState.AWAITING_LIQUIDITY_SWEEP:
                relevant_m15 = self.m15_data[self.m15_data['time'] <= current_candle_m1['time']]
                if relevant_m15.empty: continue
                
                new_liquidity_target = find_liquidity_target(relevant_m15, self.daily_bias)
                
                if new_liquidity_target and new_liquidity_target.get('level'):
                    current_target_level = self.target_liquidity.get('level')
                    if current_target_level != new_liquidity_target['level']:
                        self.target_liquidity = new_liquidity_target
                else:
                    continue 

                prev_candle_m1 = self.m1_data.iloc[i-1]
                swept = False
                if (self.daily_bias == 'صعودی' and prev_candle_m1['low'] < self.target_liquidity['level']):
                    swept = True
                elif (self.daily_bias == 'نزولی' and prev_candle_m1['high'] > self.target_liquidity['level']):
                    swept = True

                if swept:
                    target_level = self.target_liquidity['level']
                    if target_level in self.acted_on_liquidity_levels:
                        continue

                    print(f"[{current_time.strftime('%H:%M')}] Liquidity Swept at {target_level:.5f}.")
                    self.sweep_candle_info = {'low': prev_candle_m1['low'], 'high': prev_candle_m1['high']}
                    self.mss_level = find_mss_level(recent_m1_slice, self.target_liquidity['type'])
                    if self.mss_level:
                        print(f"[{current_time.strftime('%H:%M')}] MSS Level identified at {self.mss_level:.5f}")
                        self.trade_state = BotTradeState.AWAITING_MSS
                    else:
                        self._reset_cycle()

            elif self.trade_state == BotTradeState.AWAITING_MSS:
                prev_candle_m1 = self.m1_data.iloc[i-1]
                
                if self.daily_bias == 'صعودی' and prev_candle_m1['low'] < self.sweep_candle_info['low']:
                    self.sweep_candle_info['low'] = prev_candle_m1['low']
                    new_mss = find_mss_level(recent_m1_slice, self.target_liquidity['type'])
                    if new_mss: self.mss_level = new_mss
                
                elif self.daily_bias == 'نزولی' and prev_candle_m1['high'] > self.sweep_candle_info['high']:
                    self.sweep_candle_info['high'] = prev_candle_m1['high']
                    new_mss = find_mss_level(recent_m1_slice, self.target_liquidity['type'])
                    if new_mss: self.mss_level = new_mss

                if (self.daily_bias == 'صعودی' and prev_candle_m1['close'] > self.mss_level) or \
                   (self.daily_bias == 'نزولی' and prev_candle_m1['close'] < self.mss_level):
                    print(f"[{current_time.strftime('%H:%M')}] MSS Confirmed.")
                    self.trade_state = BotTradeState.AWAITING_ENTRY

            elif self.trade_state == BotTradeState.AWAITING_ENTRY:
                fvg_slice = self.m1_data.iloc[i-20:i]
                fvg = detect_fvg(fvg_slice, self.daily_bias)
                if fvg:
                    print(f"[{current_time.strftime('%H:%M')}] FVG Detected. Setting up pending order.")
                    self._setup_pending_order(fvg, current_time) # **جدید**: زمان فعلی را پاس می‌دهیم
                    self.trade_state = BotTradeState.POSITION_OPEN

            elif self.trade_state == BotTradeState.POSITION_OPEN and self.pending_order:
                # **جدید**: منطق بررسی تایم‌اوت سفارش
                if self.order_timeout_delta and (current_time - self.pending_order['setup_time'] > self.order_timeout_delta):
                    print(f"[{current_time.strftime('%H:%M')}] Pending order timed out. Cancelling.")
                    self._reset_cycle()
                    continue

                if (self.pending_order['type'] == 'long' and current_candle_m1['low'] <= self.pending_order['entry_price']) or \
                   (self.pending_order['type'] == 'short' and current_candle_m1['high'] >= self.pending_order['entry_price']):
                    
                    print(f"[{current_time.strftime('%H:%M')}] Pending order filled!")
                    open_trade = self.pending_order.copy()
                    open_trade['entry_index'] = i
                    self.pending_order = None
                
                elif (self.pending_order['type'] == 'long' and current_candle_m1['low'] <= self.pending_order['sl']) or \
                     (self.pending_order['type'] == 'short' and current_candle_m1['high'] >= self.pending_order['sl']):
                    print(f"[{current_time.strftime('%H:%M')}] Price hit SL before entry. Cancelling order.")
                    self._reset_cycle()


        self.generate_report()

    def _is_in_killzone(self, current_time):
        for kz in self.killzones:
            start_time = datetime.strptime(kz['start'], '%H:%M').time()
            end_time = datetime.strptime(kz['end'], '%H:%M').time()
            if start_time <= current_time.time() < end_time:
                return True, kz
        return False, None

    def _reset_cycle(self):
        self.trade_state = BotTradeState.AWAITING_KILLZONE
        self.target_liquidity = {}
        self.sweep_candle_info = {}
        self.mss_level = None
        self.pending_order = None
        print("--- Cycle Reset ---")


    def _setup_pending_order(self, fvg, setup_time):
        """یک سفارش در حال انتظار را بر اساس FVG شناسایی شده، تنظیم می‌کند."""
        trade_type = 'long' if self.daily_bias == 'صعودی' else 'short'
        
        if trade_type == 'long':
            entry_price = fvg['top']
            sl = self.sweep_candle_info['low']
            tp = entry_price + (entry_price - sl) * self.rr
        else: # short
            entry_price = fvg['bottom']
            sl = self.sweep_candle_info['high']
            tp = entry_price - (sl - entry_price) * self.rr
            
        self.pending_order = {
            'type': trade_type, 'entry_price': entry_price, 'sl': sl, 'tp': tp,
            'entry_time': None,
            'setup_time': setup_time # **جدید**: زمان ثبت سفارش
        }
        print(f"Pending Order Details: {self.pending_order}")
        
        used_level = self.target_liquidity['level']
        self.acted_on_liquidity_levels.append(used_level)
        print(f"Level {used_level:.5f} has been added to memory for today.")


    def _check_close_conditions(self, index, trade):
        # ... (این تابع بدون تغییر باقی می‌ماند)
        current_candle = self.m1_data.iloc[index]
        
        if trade['type'] == 'long':
            if current_candle['low'] <= trade['sl']:
                self._close_trade(index, trade, trade['sl'], "Stop-Loss"); return True
            if current_candle['high'] >= trade['tp']:
                self._close_trade(index, trade, trade['tp'], "Take-Profit"); return True
        elif trade['type'] == 'short':
            if current_candle['high'] >= trade['sl']:
                self._close_trade(index, trade, trade['sl'], "Stop-Loss"); return True
            if current_candle['low'] <= trade['tp']:
                self._close_trade(index, trade, trade['tp'], "Take-Profit"); return True
        return False

    def _close_trade(self, index, trade, close_price, reason):
        # ... (این تابع بدون تغییر باقی می‌ماند)
        pnl_pips = (close_price - trade['entry_price'])
        if trade['type'] == 'short': pnl_pips = -pnl_pips
        
        if pnl_pips > 0:
            pnl_amount = self.balance * self.risk_percent * self.rr
        else:
            pnl_amount = - (self.balance * self.risk_percent)
            
        self.balance += pnl_amount
        self.equity_curve.append(self.balance)
        
        trade.update({
            'close_price': close_price,
            'close_time': self.m1_data['time'].iloc[index],
            'pnl': pnl_amount,
            'reason': reason
        })
        trade['entry_time'] = self.m1_data['time'].iloc[trade['entry_index']]
        self.trades.append(trade)
        print(f"Trade Closed. Reason: {reason}. PnL: {pnl_amount:.2f}, New Balance: {self.balance:.2f}\n")
        self._reset_cycle()

    def generate_report(self):
        # ... (این تابع بدون تغییر باقی می‌ماند)
        df_trades = pd.DataFrame(self.trades)
        if df_trades.empty:
            print("No trades were executed."); return

        output_filename = "backtest_trades_log_fixed.csv"
        df_trades.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\nTrade log with {len(df_trades)} trades saved to '{output_filename}'")

        total_trades = len(df_trades)
        wins = df_trades[df_trades['pnl'] > 0]
        losses = df_trades[df_trades['pnl'] <= 0]
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        
        gross_profit = wins['pnl'].sum()
        gross_loss = abs(losses['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
        
        initial_balance = 10000
        final_balance = self.balance
        net_profit = final_balance - initial_balance
        
        equity_series = pd.Series(self.equity_curve)
        peak = equity_series.cummax()
        drawdown = (equity_series - peak) / peak
        max_drawdown = abs(drawdown.min()) * 100
        
        print("\n--- Backtest Report ---")
        print(f"Final Balance: {final_balance:,.2f}")
        print(f"Net Profit: {net_profit:,.2f} ({net_profit/initial_balance:.2%})")
        print(f"Maximum Drawdown: {max_drawdown:.2f}%")
        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Average Win: {wins['pnl'].mean():.2f}" if not wins.empty else "0.00")
        print(f"Average Loss: {losses['pnl'].mean():.2f}" if not losses.empty else "0.00")
        print("-----------------------")
        
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(12, 6))
            plt.plot(self.equity_curve)
            plt.title("Equity Curve")
            plt.xlabel("Trade Number")
            plt.ylabel("Balance")
            plt.grid(True)
            plt.show()
        except ImportError:
            print("\nFor plotting equity curve, please install matplotlib: pip install matplotlib")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run a backtest on historical data with Market Structure logic.")
    parser.add_argument("m15_file", help="Path to the M15 CSV file for structure.")
    parser.add_argument("m1_file", help="Path to the M1 CSV file for execution.")
    parser.add_argument("h4_file", help="Path to the H4 CSV file for bias.")
    args = parser.parse_args()

    try:
        m15_data = pd.read_csv(args.m15_file, parse_dates=['time'])
        m1_data = pd.read_csv(args.m1_file, parse_dates=['time'])
        h4_data = pd.read_csv(args.h4_file, parse_dates=['time'])
        
        print(f"Loaded {len(m15_data)} M15 rows, {len(m1_data)} M1 rows, and {len(h4_data)} H4 rows.")
        
        config = ConfigManager()
        backtester = Backtester(m15_data, m1_data, h4_data, config)
        backtester.run()

    except FileNotFoundError as e:
        print(f"Error: Data file not found. {e}")
    except Exception as e:
        print(f"An error occurred: {e}")