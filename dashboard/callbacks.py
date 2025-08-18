# dashboard/callbacks.py
# نسخه ۸.۱ - رفع باگ TypeError در تنظیمات زنده

from datetime import timedelta
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, callback_context, no_update, State, clientside_callback
import pytz

import dash_bootstrap_components as dbc

from bot.state import BotTradeState
from utils.helpers import map_deal_type_to_string, map_order_type_to_string
from utils.analytics import calculate_performance_metrics

def register_all_callbacks(app, bot_state, trading_thread):
    """تمام callback های برنامه را در یکجا ثبت می‌کند."""

    # --- Clientside Callbacks (برای سرعت بالا و انیمیشن‌های روان) ---
    clientside_callback(
        """
        function(is_dark) {
            if (is_dark) {
                document.body.classList.add('dark-theme');
                document.body.classList.remove('light-theme');
            } else {
                document.body.classList.add('light-theme');
                document.body.classList.remove('dark-theme');
            }
            return is_dark ? 'dark' : 'light';
        }
        """,
        Output('theme-store', 'data'),
        Input('theme-switch', 'value')
    )

    clientside_callback(
        """
        function(n_clicks) {
            if (n_clicks > 0) {
                const sidebar = document.getElementById('sidebar');
                const content = document.getElementById('page-content');
                sidebar.classList.toggle('collapsed');
                content.classList.toggle('collapsed');
            }
            return '';
        }
        """,
        Output('dummy-output', 'children', allow_duplicate=True),
        Input('btn_sidebar_toggle', 'n_clicks'),
        prevent_initial_call=True
    )

    # --- Server-side Callbacks ---

    @app.callback(Output('page-content', 'children'), [Input('url', 'pathname')])
    def render_page_content(pathname):
        from dashboard.layout import create_main_dashboard_layout, create_analytics_layout
        if pathname == '/':
            return create_main_dashboard_layout(app.config_manager)
        elif pathname == '/analytics':
            return create_analytics_layout(app.config_manager)
        return dbc.Container(
            [
                html.H1("404: Page Not Found", className="text-danger"),
                html.Hr(),
                html.P(f"The pathname {pathname} was not recognised..."),
            ],
            fluid=True, className="py-3",
        )

    @app.callback(
        Output('dummy-output', 'children'),
        Input('start-button', 'n_clicks'),
        Input('stop-button', 'n_clicks'),
        prevent_initial_call=True
    )
    def handle_control_buttons(start_clicks, stop_clicks):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
            
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if button_id == 'start-button':
            if not bot_state.is_running:
                bot_state.update(is_running=True, status_message="در حال تحلیل بازار...")
                bot_state.add_log("دریافت فرمان شروع از داشبورد.")
        elif button_id == 'stop-button':
            if bot_state.is_running:
                bot_state.update(is_running=False, status_message="ربات متوقف است.")
                bot_state.add_log("دریافت فرمان توقف از داشبورد.")
        return no_update

    @app.callback(
        Output("signal-panel-col", "style"),
        Output("signal-panel-content", "children"),
        Output("signal-sound", "autoPlay"),
        Input("interval-component", "n_intervals"),
        State("signal-panel-content", "children")
    )
    def update_signal_panel(n, previous_content):
        state = bot_state.get_state_snapshot()
        signal = state.get('last_signal')
        
        if not signal:
            return {'display': 'none'}, no_update, False

        content = dbc.Row([
            dbc.Col(html.P([html.Strong("نماد: "), html.Span(signal['symbol'], className="fs-5 fw-bold")]), md=2),
            dbc.Col(html.P([html.Strong("نوع: "), html.Span(signal['type_str'], className="fs-5 fw-bold")]), md=2),
            dbc.Col(html.P([html.Strong("ورود: "), html.Span(f"{signal['price']:.5f}", className="fs-5 fw-bold")]), md=2),
            dbc.Col(html.P([html.Strong("ضرر: "), html.Span(f"{signal['sl']:.5f}", className="fs-5 fw-bold")]), md=2),
            dbc.Col(html.P([html.Strong("سود: "), html.Span(f"{signal['tp']:.5f}", className="fs-5 fw-bold")]), md=2),
            dbc.Col(html.P([html.Strong("حجم: "), f"{signal['volume']} لات"]), md=2),
        ], align="center")
        
        play_sound = str(content) != str(previous_content)
        
        return {'display': 'block'}, content, play_sound

    @app.callback(
        Output('status-panel-content', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_status_panel(n):
        state = bot_state.get_state_snapshot()
        status_color = 'success' if state['is_running'] else 'danger'
        return html.Div([
            dbc.Row([
                dbc.Col("وضعیت کلی:", width=6, className="fw-bold"),
                dbc.Col(html.Span(f"{'فعال' if state['is_running'] else 'متوقف'}", className=f"badge bg-{status_color} p-2"), width=6)
            ]), html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col("پیام سیستم:", width=6, className="fw-bold"),
                dbc.Col(state['status_message'], width=6)
            ]), html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col("منطقه کشتار:", width=6, className="fw-bold"),
                dbc.Col(state['current_killzone'], width=6)
            ]),
        ])

    @app.callback(
        Output('account-panel-content', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_account_panel(n):
        info = bot_state.get_state_snapshot()['account_info']
        pnl = bot_state.get_state_snapshot()['daily_pnl']
        if not info: return "در حال دریافت اطلاعات حساب..."
        pnl_color = 'text-success' if pnl >= 0 else 'text-danger'
        return dbc.Row([
            dbc.Col([
                html.P([html.Strong("موجودی (Balance): "), f"{info.get('balance', 0):,.2f}"]),
                html.P([html.Strong("سود/زیان شناور (Equity): "), f"{info.get('equity', 0):,.2f}"]),
            ], md=6),
            dbc.Col([
                html.P([html.Strong("مارجین آزاد (Free Margin): "), f"{info.get('margin_free', 0):,.2f}"]),
                html.P([html.Strong("سود/زیان روزانه: "), html.Span(f"{pnl:,.2f}", className=f"fw-bold {pnl_color}")]),
            ], md=6)
        ])

    @app.callback(
        Output('live-settings-panel', 'children'),
        Input('url', 'pathname')
    )
    def update_live_settings_panel(pathname):
        if pathname == '/':
            initial_risk = bot_state.live_risk_percent
            initial_rr = bot_state.live_rr_ratio
            
            return html.Div([
                dbc.Row([
                    dbc.Col(html.Label("درصد ریسک در هر معامله:"), width=7),
                    dbc.Col(dcc.Input(id='risk-percent-input', type='number', value=initial_risk, step=0.1, className="form-control form-control-sm"), width=5)
                ], className="mb-2", align="center"),
                dbc.Row([
                    dbc.Col(html.Label("نسبت ریسک به ریوارد (RR):"), width=7),
                    dbc.Col(dcc.Input(id='rr-ratio-input', type='number', value=initial_rr, step=0.1, className="form-control form-control-sm"), width=5)
                ], align="center"),
                dbc.Button("اعمال تغییرات", id="update-settings-button", color="primary", size="sm", className="mt-3 w-100")
            ])
        return no_update

    @app.callback(
        Output('dummy-output', 'children', allow_duplicate=True),
        Input('update-settings-button', 'n_clicks'),
        State('risk-percent-input', 'value'),
        State('rr-ratio-input', 'value'),
        prevent_initial_call=True
    )
    def handle_update_settings(n, risk, rr):
        # FIX: بررسی اینکه آیا دکمه کلیک شده است (n is not None)
        if n is not None and n > 0:
            bot_state.update(live_risk_percent=risk, live_rr_ratio=rr)
            bot_state.add_log(f"تنظیمات زنده به‌روز شد: ریسک={risk}%, R:R={rr}")
        return no_update

    @app.callback(
        Output('live-price-chart', 'figure'),
        Input('interval-component', 'n_intervals'),
        Input('symbol-dropdown', 'value'),
        Input('theme-store', 'data')
    )
    def update_chart(n, selected_symbol, theme):
        if not selected_symbol: return go.Figure()
        
        state = bot_state.get_state_snapshot()
        symbol_state = state['symbol_states'].get(selected_symbol, {})
        df = symbol_state.get('last_m1_data', pd.DataFrame())
        
        fig = go.Figure()
        if not df.empty:
            fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='M1'))
            if symbol_state.get('target_liquidity', {}).get('level'):
                liq = symbol_state['target_liquidity']
                fig.add_hline(y=liq['level'], line_dash="dot", line_color='red' if liq['type'] == 'SSL' else 'lime', annotation_text=f"Target {liq['type']}")
            if symbol_state.get('mss_level'):
                fig.add_hline(y=symbol_state['mss_level'], line_dash="solid", line_color="orange", annotation_text="MSS Level")
            if symbol_state.get('identified_fvg', {}).get('top'):
                fvg = symbol_state['identified_fvg']
                color = 'rgba(0, 255, 0, 0.2)' if fvg['type'] == 'BULLISH' else 'rgba(255, 0, 0, 0.2)'
                fig.add_shape(type="rect", x0=fvg['time'] - timedelta(minutes=1), y0=fvg['bottom'], x1=df['time'].iloc[-1], y1=fvg['top'], line=dict(color="rgba(0,0,0,0)"), fillcolor=color, layer='below')
        
        template = 'plotly_dark' if theme == 'dark' else 'plotly_white'
        fig.update_layout(title=f"نمودار {selected_symbol}", xaxis_rangeslider_visible=False, template=template, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Vazirmatn, sans-serif'), margin=dict(l=40, r=20, t=40, b=20))
        return fig

    @app.callback(
        Output('log-output', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_logs(n):
        logs = bot_state.get_state_snapshot()['log_messages']
        return [html.P(log, className="mb-0") for log in reversed(logs)]

    @app.callback(
        Output('positions-table-content', 'children'),
        Input('interval-component', 'n_intervals')
    )
    def update_positions_table(n):
        state = bot_state.get_state_snapshot()
        positions, orders = state['open_positions'], state['open_orders']
        if not positions and not orders:
            return dbc.Alert("هیچ موقعیت یا سفارش بازی وجود ندارد.", color="info", className="m-3")
        header = [html.Thead(html.Tr([html.Th(h) for h in ["Symbol", "Ticket", "Type", "Volume", "Open Price", "S/L", "T/P", "Profit/Status"]]))]
        pos_rows = [html.Tr([html.Td(p['symbol']), html.Td(p['ticket']), html.Td("BUY" if p['type'] == 0 else "SELL"), html.Td(p['volume']), html.Td(f"{p['price_open']:.5f}"), html.Td(f"{p['sl']:.5f}"), html.Td(f"{p['tp']:.5f}"), html.Td(f"{p['profit']:.2f}", className='text-success' if p['profit'] >= 0 else 'text-danger')]) for p in positions]
        order_rows = [html.Tr([html.Td(o['symbol']), html.Td(o['ticket']), html.Td(map_order_type_to_string(o['type'])), html.Td(o['volume_initial']), html.Td(f"{o['price_open']:.5f}"), html.Td(f"{o['sl']:.5f}"), html.Td(f"{o['tp']:.5f}"), html.Td("Pending", className='text-warning')]) for o in orders]
        return dbc.Table(header + [html.Tbody(pos_rows + order_rows)], bordered=False, striped=True, hover=True, responsive=True, className="align-middle")

    # --- Callbacks for Analytics Tab ---
    
    @app.callback(
        Output('trade-history-store', 'data'),
        Input('refresh-analytics-button', 'n_clicks'),
        Input('url', 'pathname')
    )
    def load_trade_history(n_clicks, pathname):
        if pathname == '/analytics':
            try:
                df = pd.read_csv("trades.csv")
                return df.to_dict('records')
            except FileNotFoundError:
                return []
        return no_update

    @app.callback(
        Output('equity-curve-chart', 'figure'),
        Output('analytics-cards-row', 'children'),
        Output('full-history-table', 'children'),
        Input('trade-history-store', 'data'),
        Input('theme-store', 'data')
    )
    def update_analytics_page(trade_data, theme):
        if not trade_data:
            return go.Figure(), dbc.Alert("هنوز هیچ معامله‌ای برای تحلیل ثبت نشده است.", color="info"), None

        df = pd.DataFrame(trade_data)
        metrics = calculate_performance_metrics(df)

        equity_fig = go.Figure()
        if 'equity' in df.columns:
            equity_fig.add_trace(go.Scatter(x=pd.to_datetime(df['time_close']), y=df['equity'], mode='lines', name='Equity', line=dict(color=app.config_manager.get('primary-color', '#5865f2'))))
        
        template = 'plotly_dark' if theme == 'dark' else 'plotly_white'
        equity_fig.update_layout(template=template, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(family='Vazirmatn, sans-serif'))

        cards = dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(metrics['net_profit'], className="card-title text-success"), html.P("سود خالص", className="card-text")])), md=2),
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(metrics['total_trades'], className="card-title"), html.P("تعداد کل معاملات", className="card-text")])), md=2),
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(metrics['win_rate'], className="card-title"), html.P("نرخ برد", className="card-text")])), md=2),
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(metrics['profit_factor'], className="card-title"), html.P("فاکتور سود", className="card-text")])), md=2),
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(metrics['max_drawdown'], className="card-title text-danger"), html.P("حداکثر افت سرمایه", className="card-text")])), md=2),
            dbc.Col(dbc.Card(dbc.CardBody([html.H4(f"{metrics['avg_win']} / {metrics['avg_loss']}"), html.P("میانگین سود/زیان", className="card-text")])), md=2),
        ])

        history_table = dbc.Table.from_dataframe(df, striped=True, bordered=False, hover=True, responsive=True, className="align-middle")
        
        return equity_fig, cards, history_table
