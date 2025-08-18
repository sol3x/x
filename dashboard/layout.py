# dashboard/layout.py
# نسخه ۸.۰ - طراحی کاملاً جدید با سایدبار جمع‌شونده و تم دوگانه

from dash import dcc, html
import dash_bootstrap_components as dbc

def create_card(title, content_id, color="primary", icon="info-circle-fill"):
    """یک کامپوننت کارت زیبا برای نمایش اطلاعات ایجاد می‌کند."""
    return dbc.Card(
        [
            dbc.CardHeader(
                dbc.Row([
                    dbc.Col(html.I(className=f"bi bi-{icon} me-2"), width="auto"),
                    dbc.Col(title, className="fw-bold"),
                ], align="center"),
                className=f"card-header-{color}"
            ),
            dbc.CardBody(
                dbc.Spinner(
                    html.Div(id=content_id, style={'minHeight': '110px'}),
                    color=color,
                    spinner_style={"width": "2rem", "height": "2rem"}
                ),
                className="p-3",
            ),
        ],
        className="mb-4 shadow-sm h-100 card-custom",
    )

def create_header(config):
    """هدر بالای صفحه را ایجاد می‌کند که شامل عنوان و دکمه‌هاست."""
    return dbc.Row(
        align="center",
        className="mb-4 page-header",
        children=[
            dbc.Col(
                dbc.Button(html.I(className="bi bi-list"), id="btn_sidebar_toggle", n_clicks=0, className="sidebar-toggle-button"),
                width="auto"
            ),
            dbc.Col(html.I(className="bi bi-robot me-3", style={'fontSize': '2.5rem'}), width="auto", className="icon-glow"),
            dbc.Col([
                html.H1("داشبورد آرگوس ۸.۰", className="text-primary mb-0 header-title"),
                html.H5(f"نمادها: {config.get('STRATEGY_SETTINGS', 'symbols')}", className="text-muted"),
            ]),
            dbc.Col(className="text-start d-flex align-items-center justify-content-end", children=[
                dbc.Label(html.I(className="bi bi-moon-stars-fill"), html_for="theme-switch", className="me-2"),
                dbc.Switch(id="theme-switch", value=False, className="d-inline-block"),
                dbc.Label(html.I(className="bi bi-sun-fill"), html_for="theme-switch", className="me-3"),
                dbc.Button([html.I(className="bi bi-play-fill me-2"), "شروع"], id='start-button', color="success", className="ms-3 btn-custom"),
                dbc.Button([html.I(className="bi bi-stop-fill me-2"), "توقف"], id='stop-button', color="danger", className="btn-custom"),
            ])
        ]
    )

def create_main_dashboard_layout(config):
    """محتوای صفحه اصلی داشبورد را ایجاد می‌کند."""
    symbols = [s.strip().upper() for s in config.get('STRATEGY_SETTINGS', 'symbols').split(',')]
    
    return dbc.Container(fluid=True, className="p-4 fade-in", children=[
        create_header(config),
        dbc.Row([
            dbc.Col(id="signal-panel-col", lg=12, style={'display': 'none'}, children=[
                dbc.Alert(
                    [
                        html.H4("🚨 آخرین سیگنال / معامله خودکار", className="alert-heading"),
                        html.Div(id="signal-panel-content")
                    ],
                    color="warning",
                    className="shadow-lg"
                )
            ])
        ]),
        dbc.Row([
            dbc.Col(create_card("وضعیت کلی ربات", "status-panel-content", "primary", "gear-fill"), lg=4, md=12),
            dbc.Col(create_card("اطلاعات حساب", "account-panel-content", "info", "wallet2"), lg=4, md=6),
            dbc.Col(create_card("تنظیمات زنده", "live-settings-panel", "success", "sliders"), lg=4, md=6),
        ]),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader(
                        dbc.Row([
                            dbc.Col("نمودار زنده قیمت"),
                            dbc.Col(
                                dcc.Dropdown(
                                    id='symbol-dropdown',
                                    options=[{'label': s, 'value': s} for s in symbols],
                                    value=symbols[0] if symbols else None,
                                    clearable=False,
                                    className='dash-dropdown'
                                ),
                                width=4
                            )
                        ], justify="between", align="center")
                    ),
                    dbc.CardBody(dcc.Graph(id='live-price-chart', style={'height': '55vh'}))
                ], className="shadow-sm mb-4 card-custom"), lg=8,
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("گزارش لحظه‌ای (Logs)"),
                    dbc.CardBody(
                        html.Div(id='log-output', className="log-container", style={'height': '55vh'})
                    )
                ], className="shadow-sm mb-4 card-custom"), lg=4,
            ),
        ]),
        dbc.Row([
            dbc.Col(create_card("موقعیت‌ها و سفارشات باز", "positions-table-content", "warning", "list-task"), lg=12),
        ]),
    ])

def create_analytics_layout(config):
    """محتوای صفحه تحلیل عملکرد را ایجاد می‌کند."""
    return dbc.Container(fluid=True, className="p-4 fade-in", children=[
        create_header(config),
        dbc.Row([
            dbc.Col(html.H2("تحلیل عملکرد کلی ربات"), width=10),
            dbc.Col(dbc.Button("بارگذاری مجدد آمار", id="refresh-analytics-button", color="primary"), width=2, className="text-start")
        ]),
        html.Hr(),
        dbc.Row(id="analytics-cards-row", className="mb-4"),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("نمودار رشد سرمایه (Equity Curve)"),
                    dbc.CardBody(dcc.Graph(id='equity-curve-chart', style={'height': '60vh'}))
                ], className="shadow-sm mb-4 card-custom"),
                lg=12
            )
        ]),
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("تاریخچه کامل معاملات"),
                    dbc.CardBody(html.Div(id="full-history-table"))
                ], className="shadow-sm mb-4 card-custom"),
                lg=12
            )
        ])
    ])

def create_sidebar():
    """کامپوننت سایدبار (منوی کناری) را ایجاد می‌کند."""
    return html.Div(
        [
            html.Div([
                html.I(className="bi bi-robot me-3", style={'fontSize': '2.5rem'}),
                html.H2("آرگوس ۸.۰", className="d-inline-block align-middle sidebar-title"),
            ], className="sidebar-header"),
            html.Hr(),
            dbc.Nav(
                [
                    dbc.NavLink([html.I(className="bi bi-grid-fill me-2"), html.Span("داشبورد اصلی", className="sidebar-text")], href="/", active="exact"),
                    dbc.NavLink([html.I(className="bi bi-graph-up-arrow me-2"), html.Span("تحلیل عملکرد", className="sidebar-text")], href="/analytics", active="exact"),
                ],
                vertical=True,
                pills=True,
            ),
        ],
        id="sidebar",
        className="sidebar",
    )

def create_app_layout(config):
    """
    ساختار اصلی و کلی برنامه را با سایدبار و بخش محتوا ایجاد می‌کند.
    """
    return html.Div(id="app-container", children=[
        dcc.Store(id='theme-store', data='light'),
        dcc.Location(id="url"),
        create_sidebar(),
        html.Div(id="page-content", className="content"),
        # کامپوننت‌های غیر بصری در اینجا قرار می‌گیرند
        html.Audio(id='signal-sound', src='/assets/notification.mp3', autoPlay=False),
        dcc.Interval(id='interval-component', interval=5*1000, n_intervals=0),
        html.Div(id='dummy-output', style={'display': 'none'}),
        dcc.Store(id='trade-history-store')
    ])
