# bot/trader.py
# نسخه ۸.۵ - افزودن تایم‌اوت برای سفارشات معلق

import time
import threading
from datetime import datetime, time as dt_time, timedelta # افزودن timedelta
import pytz
import pandas as pd
import MetaTrader5 as mt5
import os

from bot.state import BotTradeState
from utils.analysis import get_market_structure_bias, find_liquidity_target, find_mss_level, detect_fvg, is_safe_to_trade
from utils.helpers import parse_killzones, map_order_type_to_string, map_deal_type_to_string, send_telegram_message

class TradingBot(threading.Thread):
    def __init__(self, config, state):
        super().__init__()
        self.config = config
        self.state = state
        self.stop_event = threading.Event()
        self.ny_tz = pytz.timezone('America/New_York')
        
        self.symbols = [s.strip().upper() for s in config.get('STRATEGY_SETTINGS', 'symbols').split(',')]
        self.tf_context = getattr(mt5, f"TIMEFRAME_{config.get('STRATEGY_SETTINGS', 'timeframe_context')}")
        self.tf_exec = getattr(mt5, f"TIMEFRAME_{config.get('STRATEGY_SETTINGS', 'timeframe_execution')}")
        self.tf_bias = getattr(mt5, f"TIMEFRAME_{config.get('STRATEGY_SETTINGS', 'daily_bias_timeframe')}")
        self.max_daily_loss_pct = config.getfloat('RISK_MANAGEMENT', 'max_daily_loss_percent')
        
        self.avoid_weekends = config.get('TRADING_RULES', 'avoid_weekends', fallback='true').lower() == 'true'
        self.close_eod = config.get('TRADING_RULES', 'close_positions_eod', fallback='true').lower() == 'true'
        eod_time_str = config.get('TRADING_RULES', 'eod_close_time_ny', fallback='16:45')
        self.eod_time = dt_time.fromisoformat(eod_time_str)
        
        # **جدید**: خواندن تنظیمات تایم‌اوت سفارش
        self.order_timeout_minutes = config.getint('TRADING_RULES', 'order_timeout_minutes', fallback=60)

        self.eod_closure_done = False
        self.last_eod_date = None

        self.killzones = parse_killzones(config)
        self.tracked_positions = set()

        self.enable_news_filter = config.get('FILTERS', 'enable_news_filter', fallback='false').lower() == 'true'
        self.news_impact_level = config.get('FILTERS', 'news_impact_level', fallback='High')
        self.news_buffer_minutes = config.getint('FILTERS', 'news_buffer_minutes', fallback=30)
        self.news_currencies = [c.strip().upper() for c in config.get('FILTERS', 'news_currencies', fallback='').split(',')]

        self.enable_telegram = config.get('TELEGRAM', 'enable_telegram', fallback='false').lower() == 'true'
        self.telegram_token = config.get('TELEGRAM', 'bot_token', fallback='')
        self.telegram_chat_id = config.get('TELEGRAM', 'chat_id', fallback='')
        self.trades_log_file = "trades.csv"

    def is_market_closed(self, now_ny):
        if not self.avoid_weekends: return False
        if now_ny.weekday() == 4 and now_ny.time() >= dt_time(17, 0): return True
        if now_ny.weekday() == 5: return True
        if now_ny.weekday() == 6 and now_ny.time() < dt_time(17, 0): return True
        return False

    def run(self):
        self.state.add_log("موتور تحلیل آرگوس شروع به کار کرد.")
        if not self._initialize_mt5():
            self.state.update(is_running=False, status_message="خطا در اتصال به متاتریدر 5.")
            return
        
        now_ny_initial = datetime.now(self.ny_tz)
        if self.is_market_closed(now_ny_initial):
            self.state.update(status_message="بازار تعطیل است.")
        
        while not self.stop_event.is_set():
            try:
                now_ny = datetime.now(self.ny_tz)
                
                if self.last_eod_date is not None and now_ny.date() > self.last_eod_date:
                    self.eod_closure_done = False; self.last_eod_date = None
                    self.state.add_log("روز معاملاتی جدید شروع شد.")
                    for symbol in self.symbols:
                        self.state.symbol_states[symbol]['acted_on_liquidity_levels'] = []
                        self.state.add_log(f"[{symbol}] حافظه سطوح نقدینگی برای روز جدید ریست شد.")

                    if self.state.is_running: self.state.update(status_message="در حال تحلیل بازار...")
                    else: self.state.update(status_message="ربات متوقف است.")

                market_is_closed = self.is_market_closed(now_ny)
                if market_is_closed:
                    if self.state.status_message != "بازار تعطیل است.": self.state.update(status_message="بازار تعطیل است.")
                    time.sleep(3600); continue

                is_after_eod = self.close_eod and now_ny.weekday() < 5 and now_ny.time() >= self.eod_time
                if is_after_eod and not self.eod_closure_done:
                    self._handle_end_of_day_close()
                    self.eod_closure_done = True; self.last_eod_date = now_ny.date()

                trading_allowed = not market_is_closed and not self.eod_closure_done

                if self.state.is_running:
                    if trading_allowed:
                        if self.state.status_message != "در حال تحلیل بازار...": self.state.update(status_message="در حال تحلیل بازار...")
                        self._update_common_info()
                        
                        # **جدید**: بررسی سفارشات تایم‌اوت شده
                        if self.order_timeout_minutes > 0:
                            self._handle_timed_out_orders()

                        for symbol in self.symbols:
                            self._state_machine_manager(symbol)
                        time.sleep(1)
                    else:
                         if self.state.status_message != "منتظر زمان مناسب معاملاتی...": self.state.update(status_message="منتظر زمان مناسب معاملاتی...")
                else:
                    if trading_allowed and self.state.status_message != "ربات متوقف است.": self.state.update(status_message="ربات متوقف است.")

                time.sleep(5)
            except Exception as e:
                self.state.add_log(f"خطای بحرانی در حلقه اصلی: {e}", level='error')
                time.sleep(30)
        self._shutdown_mt5()
        self.state.add_log("موتور تحلیل متوقف شد.")

    # **جدید**: تابع برای لغو سفارشاتی که تایم‌اوت شده‌اند
    def _handle_timed_out_orders(self):
        open_orders = self.state.open_orders
        if not open_orders:
            return

        now_utc = datetime.now(pytz.utc)
        timeout_delta = timedelta(minutes=self.order_timeout_minutes)

        for order in open_orders:
            # زمان ثبت سفارش به وقت UTC است
            order_time = datetime.fromtimestamp(order['time_setup'], tz=pytz.utc)
            if now_utc - order_time > timeout_delta:
                self.state.add_log(f"[{order['symbol']}] سفارش {order['ticket']} به دلیل تایم‌اوت در حال لغو شدن است.", 'warning')
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": order['ticket'],
                    "comment": "Order Timeout"
                }
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    self.state.add_log(f"[{order['symbol']}] لغو سفارش تایم‌اوت شده ناموفق بود: {result.comment}", 'error')
                else:
                    self.state.add_log(f"[{order['symbol']}] سفارش {order['ticket']} با موفقیت لغو شد.")
                    # بعد از لغو، چرخه را برای آن نماد ریست می‌کنیم تا آماده فرصت جدید شود
                    self._reset_trade_cycle(order['symbol'], "سفارش به دلیل تایم‌اوت لغو شد.")


    def _initialize_mt5(self):
        # ... (بقیه توابع بدون تغییر باقی می‌مانند)
        path = self.config.get('MT5_SETTINGS', 'path')
        login = self.config.getint('MT5_SETTINGS', 'login')
        password = self.config.get('MT5_SETTINGS', 'password')
        server = self.config.get('MT5_SETTINGS', 'server')
        if not mt5.initialize(path=path, login=login, password=password, server=server):
            self.state.add_log(f"Initialize() failed, error code = {mt5.last_error()}", 'error')
            return False
        self.state.add_log("با موفقیت به متاتریدر 5 متصل شد.")
        return True

    def _shutdown_mt5(self):
        mt5.shutdown()
        self.state.add_log("اتصال از متاتریدر 5 قطع شد.")

    def _get_market_data(self, symbol, timeframe, count):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0: return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def _update_common_info(self):
        account_info = mt5.account_info()
        if account_info: self.state.update(account_info=account_info._asdict())
        
        open_positions = mt5.positions_get() or []
        open_orders = mt5.orders_get() or []
        self.state.update(
            open_positions=[p._asdict() for p in open_positions],
            open_orders=[o._asdict() for o in open_orders]
        )
        
        current_position_tickets = {p.ticket for p in open_positions}
        closed_tickets = self.tracked_positions - current_position_tickets
        if closed_tickets:
            self._handle_closed_positions(closed_tickets)
        self.tracked_positions = current_position_tickets

        from_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        history_deals = mt5.history_deals_get(from_date, datetime.now())
        
        if history_deals:
            df_deals = pd.DataFrame(list(history_deals))
            if 'entry' in df_deals.columns:
                trade_deals = df_deals[df_deals['entry'].isin([mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_OUT])].copy()
                daily_pnl = trade_deals['profit'].sum()
                
                if not trade_deals.empty:
                    trade_deals['type_str'] = trade_deals['type'].apply(map_deal_type_to_string)
                
                self.state.update(daily_pnl=daily_pnl, daily_trade_history=trade_deals.to_dict('records'))
            else:
                self.state.update(daily_pnl=0.0, daily_trade_history=[])

    def _handle_end_of_day_close(self):
        """
        این تابع تمام موقعیت‌های باز را می‌بندد و تمام سفارشات در حال انتظار را در پایان روز لغو می‌کند.
        """
        self.state.add_log("پایان روز معاملاتی. در حال بستن تمام موقعیت‌ها و سفارشات...", 'info')
        
        # بستن تمام موقعیت‌های باز
        open_positions = mt5.positions_get()
        if open_positions and len(open_positions) > 0:
            for position in open_positions:
                self.state.add_log(f"[{position.symbol}] در حال بستن موقعیت {position.ticket}...", 'info')
                tick = mt5.symbol_info_tick(position.symbol)
                if not tick:
                    self.state.add_log(f"[{position.symbol}] دریافت قیمت برای بستن موقعیت ناموفق بود.", 'error')
                    continue

                if position.type == mt5.ORDER_TYPE_BUY:
                    order_type = mt5.ORDER_TYPE_SELL
                    price = tick.bid
                else:
                    order_type = mt5.ORDER_TYPE_BUY
                    price = tick.ask
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": position.ticket,
                    "symbol": position.symbol,
                    "volume": position.volume,
                    "type": order_type,
                    "price": price,
                    "magic": 0,
                    "comment": "",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_FOK,
                }
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                    self.state.add_log(f"[{position.symbol}] بستن موقعیت {position.ticket} ناموفق بود: {result.comment}", 'error')
                else:
                    self.state.add_log(f"[{position.symbol}] موقعیت {position.ticket} با موفقیت بسته شد.", 'info')
        else:
            self.state.add_log("هیچ موقعیت بازی برای بستن وجود ندارد.", 'info')

        # لغو تمام سفارشات در حال انتظار
        open_orders = mt5.orders_get()
        if open_orders and len(open_orders) > 0:
            for order in open_orders:
                self.state.add_log(f"[{order.symbol}] در حال لغو سفارش {order.ticket}...", 'info')
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": order.ticket,
                    "comment": "EOD Cancellation"
                }
                result = mt5.order_send(request)
                if result.retcode != mt5.TRADE_RETCODE_DONE:
                     self.state.add_log(f"[{order.symbol}] لغو سفارش {order.ticket} ناموفق بود: {result.comment}", 'error')
                else:
                     self.state.add_log(f"[{order.symbol}] سفارش {order.ticket} با موفقیت لغو شد.", 'info')
        else:
            self.state.add_log("هیچ سفارش بازی برای لغو وجود ندارد.", 'info')


        self.state.update(status_message="تمام موقعیت‌ها در پایان روز بسته شدند.")

    def _handle_closed_positions(self, closed_tickets):
        for ticket in closed_tickets:
            history_deals = mt5.history_deals_get(0, datetime.now())
            if not history_deals: continue
            df_deals = pd.DataFrame(list(history_deals))
            if 'position_id' not in df_deals.columns: continue
            closing_deals = df_deals[df_deals['position_id'] == ticket]
            if not closing_deals.empty:
                closing_deal = closing_deals.iloc[-1].to_dict()
                comment = closing_deal.get('comment', '')
                profit = closing_deal.get('profit', 0.0)
                reason = "Manual Close"
                if '[sl]' in comment.lower(): reason = "Stop Loss"
                elif '[tp]' in comment.lower(): reason = "Take Profit"
                elif 'eod' in comment.lower(): reason = "End of Day"
                result = "Win" if profit >= 0 else "Loss"
                self.state.add_log(f"[{closing_deal.get('symbol')}] موقعیت {ticket} با {result} در {reason} بسته شد. P/L: {profit:.2f}", 'info')
                trade_log_info = {
                    'ticket': ticket, 'symbol': closing_deal.get('symbol'),
                    'type': "BUY" if closing_deal.get('type') == mt5.DEAL_TYPE_BUY else "SELL",
                    'profit': profit,
                    'time_close': datetime.fromtimestamp(closing_deal.get('time')).strftime('%Y-%m-%d %H:%M:%S'),
                    'reason': reason
                }
                self._log_trade_to_csv(trade_log_info)

    def _log_trade_to_csv(self, deal_info):
        try:
            file_exists = os.path.isfile(self.trades_log_file)
            df = pd.DataFrame([deal_info])
            df.to_csv(self.trades_log_file, mode='a', header=not file_exists, index=False)
        except Exception as e:
            self.state.add_log(f"خطا در ثبت معامله در فایل CSV: {e}", 'error')

    def _execute_trade(self, fvg, symbol):
        if self.enable_news_filter:
            relevant_currencies = [c for c in self.news_currencies if c in symbol]
            if relevant_currencies and not is_safe_to_trade(relevant_currencies, self.news_impact_level, self.news_buffer_minutes):
                self.state.add_log(f"[{symbol}] معامله به دلیل نزدیکی به اخبار مهم لغو شد.", 'warning')
                self._reset_trade_cycle(symbol, "ریست به دلیل فیلتر اخبار.")
                return

        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            self.state.add_log(f"[{symbol}] اطلاعات نماد پیدا نشد.", 'error'); return

        point = symbol_info.point
        balance = self.state.account_info.get('balance', 0)
        symbol_state = self.state.symbol_states[symbol]
        
        if symbol_state['daily_bias'] == "صعودی":
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
            entry_price = fvg['top']
            sl = symbol_state['sweep_candle_info']['low'] - 3 * point
            tp = entry_price + (entry_price - sl) * self.state.live_rr_ratio
        else:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
            entry_price = fvg['bottom']
            sl = symbol_state['sweep_candle_info']['high'] + 3 * point
            tp = entry_price - (sl - entry_price) * self.state.live_rr_ratio

        risk_amount = balance * (self.state.live_risk_percent / 100)
        sl_points = abs(entry_price - sl)
        if sl_points == 0: return
        
        volume = risk_amount / (sl_points * symbol_info.trade_contract_size)
        volume = round(volume / symbol_info.volume_step) * symbol_info.volume_step
        if volume < symbol_info.volume_min: volume = symbol_info.volume_min
        if volume <= 0: return

        order_type_str = map_order_type_to_string(order_type)
        
        signal_details = {
            "symbol": symbol, "volume": volume, "type_str": order_type_str,
            "price": entry_price, "sl": sl, "tp": tp, "time": datetime.now()
        }
        self.state.update(last_signal=signal_details)
        self.state.add_log(f"🚨 [{symbol}] سیگنال جدید شناسایی شد: {order_type_str}")
        
        self.state.add_log(f"[{symbol}] ارسال خودکار سفارش: حجم={volume}, ورود={entry_price:.5f}, SL={sl:.5f}, TP={tp:.5f}")
        request = {
            "action": mt5.TRADE_ACTION_PENDING, "symbol": symbol, "volume": volume,
            "type": order_type, "price": entry_price, "sl": sl, "tp": tp,
            "magic": 0, "comment": "", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.state.add_log(f"[{symbol}] ارسال سفارش ناموفق بود, کد خطا={result.retcode}, کامنت={result.comment}", 'error')
        else:
            self.state.add_log(f"[{symbol}] دستور Limit با موفقیت در تیکت {result.order} ارسال شد.")
            used_liquidity_level = symbol_state['target_liquidity']['level']
            symbol_state['acted_on_liquidity_levels'].append(used_liquidity_level)
            self.state.add_log(f"[{symbol}] سطح نقدینگی {used_liquidity_level:.5f} به حافظه اضافه شد.")

            if self.enable_telegram:
                message = f"🚨 سیگنال جدید آرگوس\n\n" \
                          f"نماد: {symbol}\n" \
                          f"نوع: {order_type_str}\n" \
                          f"ورود: {entry_price:.5f}\n" \
                          f"ضرر: {sl:.5f}\n" \
                          f"سود: {tp:.5f}\n" \
                          f"حجم پیشنهادی: {volume} لات"
                send_telegram_message(self.telegram_token, self.telegram_chat_id, message)

    def _state_machine_manager(self, symbol):
        symbol_state = self.state.symbol_states[symbol]
        current_state = symbol_state['trade_state']
        
        open_pos_for_symbol = [p for p in self.state.open_positions if p['symbol'] == symbol]
        open_orders_for_symbol = [o for o in self.state.open_orders if o['symbol'] == symbol]

        if open_pos_for_symbol or open_orders_for_symbol:
            if current_state != BotTradeState.POSITION_OPEN:
                 symbol_state['trade_state'] = BotTradeState.POSITION_OPEN
            return
        elif current_state == BotTradeState.POSITION_OPEN:
             self._reset_trade_cycle(symbol, "موقعیت/سفارش بسته شد. آماده برای چرخه بعدی.")
             current_state = symbol_state['trade_state']

        if current_state == BotTradeState.IDLE: self._handle_idle(symbol)
        elif current_state == BotTradeState.AWAITING_KILLZONE: self._handle_awaiting_killzone(symbol)
        elif current_state == BotTradeState.AWAITING_LIQUIDITY_SWEEP: self._handle_awaiting_sweep(symbol)
        elif current_state == BotTradeState.AWAITING_MSS: self._handle_awaiting_mss(symbol)
        elif current_state == BotTradeState.AWAITING_ENTRY: self._handle_awaiting_entry(symbol)

    def _reset_trade_cycle(self, symbol, message="چرخه معاملاتی ریست شد."):
        self.state.add_log(f"[{symbol}] {message}")
        symbol_state = self.state.symbol_states[symbol]
        symbol_state['trade_state'] = BotTradeState.AWAITING_KILLZONE
        symbol_state['target_liquidity'] = {"level": None, "type": None}
        symbol_state['sweep_candle_info'] = {}
        symbol_state['mss_level'] = None
        symbol_state['identified_fvg'] = {}

    def _is_in_killzone(self):
        now_utc = datetime.now(pytz.utc)
        now_ny = now_utc.astimezone(self.ny_tz)
        for kz in self.killzones:
            start_time = datetime.strptime(kz['start'], '%H:%M').time()
            end_time = datetime.strptime(kz['end'], '%H:%M').time()
            if start_time <= now_ny.time() < end_time:
                self.state.update(current_killzone=f"فعال: {kz['name']}")
                return True
        self.state.update(current_killzone="خارج از محدوده")
        return False

    def _handle_idle(self, symbol):
        self.state.symbol_states[symbol]['trade_state'] = BotTradeState.AWAITING_KILLZONE

    def _handle_awaiting_killzone(self, symbol):
        balance = self.state.account_info.get('balance', 0)
        if balance > 0 and (self.state.daily_pnl < 0 and abs(self.state.daily_pnl) / balance * 100 > self.max_daily_loss_pct):
            if self.state.is_running:
                self.state.add_log(f"حد ضرر روزانه ({self.max_daily_loss_pct}%) فعال شد.", 'warning')
                self.state.update(is_running=False, status_message="حد ضرر روزانه فعال شد.")
            return
        if self._is_in_killzone():
            self.state.add_log(f"[{symbol}] وارد منطقه کشتار شدیم. شروع تحلیل...")
            df_bias = self._get_market_data(symbol, self.tf_bias, 300)
            daily_bias_val = get_market_structure_bias(df_bias)
            self.state.symbol_states[symbol]['daily_bias'] = daily_bias_val
            
            self.state.symbol_states[symbol]['trade_state'] = BotTradeState.AWAITING_LIQUIDITY_SWEEP
        elif self.state.symbol_states[symbol]['trade_state'] != BotTradeState.AWAITING_KILLZONE:
            self._reset_trade_cycle(symbol, "خارج از منطقه کشتار.")

    def _handle_awaiting_sweep(self, symbol):
        if not self._is_in_killzone(): self._reset_trade_cycle(symbol, "خروج از منطقه کشتار."); return
        
        symbol_state = self.state.symbol_states[symbol]
        
        df_m15 = self._get_market_data(symbol, self.tf_context, 200)
        if df_m15.empty: return
        symbol_state['last_m15_data'] = df_m15
        
        new_liquidity_target = find_liquidity_target(df_m15, symbol_state['daily_bias'])
        
        if new_liquidity_target and new_liquidity_target.get('level'):
            current_target_level = symbol_state['target_liquidity'].get('level')
            if current_target_level != new_liquidity_target['level']:
                self.state.add_log(f"[{symbol}] هدف نقدینگی به‌روز شد: {new_liquidity_target['type']} در سطح {new_liquidity_target['level']:.5f}")
                symbol_state['target_liquidity'] = new_liquidity_target
        else:
            self.state.add_log(f"[{symbol}] در حال حاضر هدف نقدینگی معتبری یافت نشد...", 'warning')
            return 

        df_m1 = self._get_market_data(symbol, self.tf_exec, 15)
        if df_m1.empty or len(df_m1) < 3: return
        symbol_state['last_m1_data'] = df_m1
        
        last_closed_candle = df_m1.iloc[-2]
        target_level = symbol_state['target_liquidity']['level']
        target_type = symbol_state['target_liquidity']['type']
        
        swept = False
        if target_type == 'SSL' and last_closed_candle['low'] < target_level: swept = True
        elif target_type == 'BSL' and last_closed_candle['high'] > target_level: swept = True
        
        if swept:
            if target_level in symbol_state.get('acted_on_liquidity_levels', []):
                return

            symbol_state['sweep_candle_info'] = {'low': last_closed_candle['low'], 'high': last_closed_candle['high']}
            self.state.add_log(f"[{symbol}] نقدینگی {target_type} در {target_level:.5f} جارو شد.")
            mss_level_val = find_mss_level(df_m1, target_type)
            if mss_level_val:
                symbol_state['mss_level'] = mss_level_val
                symbol_state['trade_state'] = BotTradeState.AWAITING_MSS
                self.state.add_log(f"[{symbol}] سطح MSS برای شکست در {mss_level_val:.5f} تعیین شد.")
            else:
                self._reset_trade_cycle(symbol, "سطح MSS پیدا نشد.")

    def _handle_awaiting_mss(self, symbol):
        if not self._is_in_killzone(): self._reset_trade_cycle(symbol, "خروج از منطقه کشتار."); return
        df_m1 = self._get_market_data(symbol, self.tf_exec, 15)
        if df_m1.empty or len(df_m1) < 3: return
        self.state.symbol_states[symbol]['last_m1_data'] = df_m1
        
        symbol_state = self.state.symbol_states[symbol]
        last_closed_candle = df_m1.iloc[-2]
        
        if symbol_state['daily_bias'] == "صعودی" and last_closed_candle['low'] < symbol_state['sweep_candle_info']['low']:
            self.state.add_log(f"[{symbol}] تطبیق با کف جدید. سطوح SL و MSS به‌روزرسانی شدند.")
            symbol_state['sweep_candle_info']['low'] = last_closed_candle['low']
            new_mss = find_mss_level(df_m1, symbol_state['target_liquidity']['type'])
            if new_mss: symbol_state['mss_level'] = new_mss
        
        elif symbol_state['daily_bias'] == "نزولی" and last_closed_candle['high'] > symbol_state['sweep_candle_info']['high']:
            self.state.add_log(f"[{symbol}] تطبیق با سقف جدید. سطوح SL و MSS به‌روزرسانی شدند.")
            symbol_state['sweep_candle_info']['high'] = last_closed_candle['high']
            new_mss = find_mss_level(df_m1, symbol_state['target_liquidity']['type'])
            if new_mss: symbol_state['mss_level'] = new_mss

        mss_level = symbol_state['mss_level']
        mss_confirmed = False
        if symbol_state['daily_bias'] == "صعودی" and last_closed_candle['close'] > mss_level: mss_confirmed = True
        elif symbol_state['daily_bias'] == "نزولی" and last_closed_candle['close'] < mss_level: mss_confirmed = True
        
        if mss_confirmed:
            self.state.add_log(f"[{symbol}] تغییر ساختار بازار (MSS) در {mss_level:.5f} تایید شد.")
            symbol_state['trade_state'] = BotTradeState.AWAITING_ENTRY

    def _handle_awaiting_entry(self, symbol):
        if not self._is_in_killzone(): self._reset_trade_cycle(symbol, "خروج از منطقه کشتار."); return
        df_m1 = self._get_market_data(symbol, self.tf_exec, 20)
        if df_m1.empty: return
        self.state.symbol_states[symbol]['last_m1_data'] = df_m1
        
        symbol_state = self.state.symbol_states[symbol]
        fvg = detect_fvg(df_m1, symbol_state['daily_bias'])
        if fvg:
            self.state.add_log(f"[{symbol}] FVG از نوع {fvg['type']} در محدوده {fvg['top']:.5f}-{fvg['bottom']:.5f} شناسایی شد.")
            symbol_state['identified_fvg'] = fvg
            self._execute_trade(fvg, symbol)