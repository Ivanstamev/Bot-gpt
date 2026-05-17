"""
app.py — NEXUS BOT PRO
══════════════════════════════════════════════════════════════
Streamlit интерфейс, оптимизиран за мобилни устройства.
Включва:
  • TradingView Live Chart
  • 5 стратегии с редактор
  • Demo сметка
  • Backtest (7/30 дни) + Equity Curve
  • Risk Management настройки
  • Multi-TF тренд таблица
  • AI сигнали с корелационен филтър
══════════════════════════════════════════════════════════════
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import time
from functools import lru_cache
from datetime import datetime

from engine import TradingBot, BotConfig
from risk_management import RiskConfig
from strategy_manager import STRATEGY_TEMPLATES

# ─────────────────────────────────────────────────────────────
#  PAGE CONFIG — Мобилен приоритет
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title    = "NEXUS BOT PRO",
    page_icon     = "⚡",
    layout        = "wide",
    initial_sidebar_state = "collapsed",
)

# ─────────────────────────────────────────────────────────────
#  GLOBAL CSS — Тъмен тийм, мобилни карти
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');

/* Hide Streamlit branding */
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display:none;}

/* Root */
:root {
  --bg:     #040810;
  --bg2:    #080f1e;
  --bg3:    #0d1626;
  --border: #162035;
  --green:  #00ffaa;
  --red:    #ff3355;
  --blue:   #00aaff;
  --yellow: #ffcc00;
  --text:   #d0e4f8;
  --dim:    #4a6080;
}

/* Body */
.stApp {
  background: var(--bg);
  font-family: 'Space Mono', monospace;
}
.stApp * { color: var(--text); }

/* Sidebar */
[data-testid="stSidebar"] {
  background: var(--bg2);
  border-right: 1px solid var(--border);
}

/* Inputs */
.stTextInput input, .stNumberInput input, .stSelectbox select,
.stTextArea textarea {
  background: var(--bg3) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 10px !important;
  font-family: 'Space Mono', monospace !important;
}

/* Buttons */
.stButton > button {
  background: linear-gradient(135deg, #00ffaa, #00aaff) !important;
  color: #000 !important;
  border: none !important;
  border-radius: 12px !important;
  font-family: 'Space Mono', monospace !important;
  font-weight: 700 !important;
  letter-spacing: 1px !important;
  padding: 10px 20px !important;
  width: 100% !important;
}
.stButton > button:hover { opacity: 0.85 !important; }

/* Danger button override */
.danger-btn > button {
  background: transparent !important;
  border: 1px solid var(--red) !important;
  color: var(--red) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg2);
  border-radius: 12px;
  border: 1px solid var(--border);
  gap: 4px;
  padding: 4px;
}
.stTabs [data-baseweb="tab"] {
  background: transparent;
  color: var(--dim);
  border-radius: 8px;
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  font-weight: 700;
}
.stTabs [aria-selected="true"] {
  background: var(--bg3) !important;
  color: var(--text) !important;
  border: 1px solid var(--border) !important;
}

/* Metric cards */
[data-testid="metric-container"] {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
}
[data-testid="metric-container"] label {
  font-size: 9px !important;
  letter-spacing: 2px !important;
  color: var(--dim) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'Syne', sans-serif !important;
  font-size: 22px !important;
  font-weight: 800 !important;
}

/* Sliders */
.stSlider [data-baseweb="slider"] { color: var(--green) !important; }

/* Expander */
.streamlit-expanderHeader {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  font-family: 'Space Mono', monospace !important;
  font-size: 11px !important;
}

/* DataFrames */
.stDataFrame { background: var(--bg2); border-radius: 10px; }

/* Custom card */
.nx-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 18px;
  margin-bottom: 12px;
  position: relative;
}
.nx-card::before {
  content: '';
  position: absolute;
  top: 0; left: 20px; right: 20px; height: 1px;
  background: linear-gradient(90deg, transparent, var(--border), transparent);
}
.nx-label {
  font-size: 9px;
  color: var(--dim);
  letter-spacing: 3px;
  margin-bottom: 8px;
}
.nx-value {
  font-family: 'Syne', sans-serif;
  font-size: 26px;
  font-weight: 800;
}

/* Signal pill */
.pill {
  display: inline-block;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 1px;
}
.pill-long  { background:#00ffaa18; border:1px solid #00ffaa; color:#00ffaa; }
.pill-short { background:#ff335518; border:1px solid #ff3355; color:#ff3355; }
.pill-hold  { background:#ffcc0018; border:1px solid #ffcc00; color:#ffcc00; }

/* Trend table */
.trend-table { width:100%; border-collapse:collapse; font-size:11px; }
.trend-table td, .trend-table th {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
.trend-table th { color: var(--dim); font-size: 9px; letter-spacing: 2px; }

/* Mobile responsiveness */
@media (max-width: 768px) {
  .nx-value { font-size: 20px !important; }
  .stTabs [data-baseweb="tab"] { font-size: 9px !important; padding: 6px 4px !important; }
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  SESSION STATE INIT
# ─────────────────────────────────────────────────────────────

if "bot" not in st.session_state:
    st.session_state.bot          = TradingBot()
    st.session_state.running      = False
    st.session_state.last_tick    = {}
    st.session_state.bt_result    = None
    st.session_state.api_saved    = False
    st.session_state.demo_balance = 10_000.0

bot: TradingBot = st.session_state.bot


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def color_val(v: float, positive_good: bool = True) -> str:
    if positive_good:
        return f"{'#00ffaa' if v >= 0 else '#ff3355'}"
    return f"{'#ff3355' if v >= 0 else '#00ffaa'}"

def fmt_price(p) -> str:
    try: return f"${float(p):,.2f}"
    except: return "—"

def fmt_pct(p) -> str:
    try:
        v = float(p)
        return f"{'+'if v>=0 else ''}{v:.2f}%"
    except: return "—"

def fmt_usdt(p) -> str:
    try:
        v = float(p)
        return f"{'+'if v>=0 else ''}${v:,.2f}"
    except: return "—"


# ─────────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────────

col_logo, col_status, col_ctrl = st.columns([3, 3, 2])

with col_logo:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding:8px 0">
      <div style="width:40px;height:40px;border-radius:12px;
        background:linear-gradient(135deg,#00ffaa,#00aaff);
        display:flex;align-items:center;justify-content:center;
        font-size:20px;box-shadow:0 0 20px #00ffaa40">⚡</div>
      <div>
        <div style="font-family:'Syne',sans-serif;font-size:20px;font-weight:800;
          background:linear-gradient(90deg,#00ffaa,#00aaff);
          -webkit-background-clip:text;-webkit-text-fill-color:transparent">NEXUS BOT</div>
        <div style="font-size:8px;color:#4a6080;letter-spacing:3px">AI TRADING PLATFORM</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

tick = st.session_state.last_tick
price_disp = fmt_price(tick.get("current_price", 0)) if tick else "—"
sig_disp   = tick.get("signal", "—") if tick else "—"
sig_class  = {"LONG": "pill-long", "SHORT": "pill-short"}.get(sig_disp, "pill-hold")

with col_status:
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;padding:10px 0">
      <div>
        <div style="font-size:9px;color:#4a6080;letter-spacing:2px">ЦЕНА</div>
        <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#fff">{price_disp}</div>
      </div>
      <div><span class="pill {sig_class}">{sig_disp}</span></div>
      <div style="display:flex;align-items:center;gap:6px;font-size:11px">
        <div style="width:7px;height:7px;border-radius:50%;
          background:{'#00ff88' if st.session_state.running else '#ff3355'};
          box-shadow:{'0 0 8px #00ff88' if st.session_state.running else 'none'}"></div>
        <span style="color:{'#00ff88' if st.session_state.running else '#ff3355'}">
          {'АКТИВЕН' if st.session_state.running else 'СПРЯН'}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

with col_ctrl:
    if st.session_state.running:
        if st.button("⏹ СПРИ БОТА", key="stop_btn"):
            st.session_state.running = False
            st.rerun()
    else:
        if st.button("▶ СТАРТИРАЙ", key="start_btn"):
            st.session_state.running = True
            st.rerun()

st.markdown("<hr style='border-color:#162035;margin:8px 0'>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  LIVE TICK (само когато е стартиран)
# ─────────────────────────────────────────────────────────────

if st.session_state.running:
    result = bot.tick()
    st.session_state.last_tick = result
    tick = result


# ─────────────────────────────────────────────────────────────
#  TABS
# ─────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📊 DASHBOARD",
    "📈 ГРАФИКА",
    "🧠 СТРАТЕГИЯ",
    "💼 ДЕМО",
    "📉 BACKTEST",
    "⚙️ НАСТРОЙКИ",
    "🌍 ТРЕНД",
])

tab_dash, tab_chart, tab_strat, tab_demo, tab_bt, tab_settings, tab_trend = tabs


# ══════════════════════════════════════════════════════════════
#  TAB 1: DASHBOARD
# ══════════════════════════════════════════════════════════════

with tab_dash:

    # Quick metrics
    c1, c2, c3, c4 = st.columns(4)
    demo_bal  = tick.get("demo_balance", bot.demo.balance) if tick else bot.demo.balance
    demo_pnl  = tick.get("demo_pnl",     bot.demo.pnl)    if tick else bot.demo.pnl
    win_rate  = tick.get("win_rate",     bot.demo.win_rate) if tick else 0
    confidence= tick.get("confidence",   0) if tick else 0
    sentiment = tick.get("sentiment",    "NEUTRAL") if tick else "NEUTRAL"
    sent_color= {"BULLISH":"#00ffaa","BEARISH":"#ff3355","NEUTRAL":"#ffcc00"}.get(sentiment,"#ffcc00")

    c1.metric("💰 БАЛАНС",   f"${demo_bal:,.2f}")
    c2.metric("📊 P&L",      fmt_usdt(demo_pnl),   delta=fmt_pct(demo_pnl/demo_bal*100) if demo_bal else None)
    c3.metric("🎯 WIN RATE", f"{win_rate}%")
    c4.metric("🔥 CONFIDENCE", f"{confidence:.0f}%")

    # Signal card
    if tick:
        sig      = tick.get("signal", "HOLD")
        sig_icon = {"LONG":"🟢","SHORT":"🔴","HOLD":"⚪"}.get(sig,"⚪")
        sig_col  = {"LONG":"#00ffaa","SHORT":"#ff3355","HOLD":"#ffcc00"}.get(sig,"#ffcc00")
        reasons  = tick.get("reasons", [])
        ai_cmt   = tick.get("ai_comment", "")

        st.markdown(f"""
        <div class="nx-card">
          <div class="nx-label">⚡ AI СИГНАЛ — {tick.get('strategy','—')}</div>
          <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
            <div style="font-family:'Syne',sans-serif;font-size:32px;font-weight:800;color:{sig_col}">
              {sig_icon} {sig}
            </div>
            <div>
              <div style="font-size:11px;color:#4a6080">CONFIDENCE</div>
              <div style="font-family:'Syne',sans-serif;font-size:24px;font-weight:800;color:{sig_col}">
                {confidence:.0f}%
              </div>
            </div>
            <div style="margin-left:auto">
              <div style="font-size:11px;color:#4a6080">СЕНТИМЕНТ</div>
              <div style="font-weight:700;color:{sent_color}">{sentiment}</div>
            </div>
          </div>
          <div style="font-size:10px;color:#4a6080">
            {'<br>'.join(f'• {r}' for r in reasons[:6])}
          </div>
          {f'<div style="margin-top:10px;padding:10px;background:#0d1626;border-radius:8px;font-size:11px;border-left:2px solid #00aaff">🤖 {ai_cmt}</div>' if ai_cmt else ''}
        </div>
        """, unsafe_allow_html=True)

    # Active position
    pos = tick.get("demo_position") if tick else bot.demo.position
    if pos:
        cp    = tick.get("current_price", pos["entry"]) if tick else pos["entry"]
        upnl  = (cp - pos["entry"]) / pos["entry"] * 100 if pos["direction"]=="LONG" \
                else (pos["entry"] - cp) / pos["entry"] * 100
        u_col = "#00ffaa" if upnl >= 0 else "#ff3355"

        st.markdown(f"""
        <div class="nx-card" style="border-color:#00ffaa">
          <div class="nx-label">⚡ АКТИВНА ПОЗИЦИЯ — {pos['direction']}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px">
            <div><div style="font-size:9px;color:#4a6080">ВХОД</div>
              <div style="font-weight:700">${pos['entry']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">TAKE-PROFIT</div>
              <div style="font-weight:700;color:#00ffaa">${pos['tp']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">STOP-LOSS</div>
              <div style="font-weight:700;color:#ff3355">${pos['sl']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">UNREALIZED P&L</div>
              <div style="font-weight:700;color:{u_col}">{upnl:+.2f}%</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Risk status
    rs = tick.get("risk_status", {}) if tick else bot.risk.get_status()
    if rs:
        st.markdown(f"""
        <div class="nx-card">
          <div class="nx-label">🛡 RISK STATUS</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:12px">
            <div>Дневна P&L: <b style="color:{'#00ffaa' if rs.get('daily_pnl',0)>=0 else '#ff3355'}">{fmt_usdt(rs.get('daily_pnl',0))}</b></div>
            <div>Поред. загуби: <b>{rs.get('consecutive_losses',0)}</b></div>
            <div>Бот пауза: <b style="color:{'#ff3355' if rs.get('paused') else '#00ffaa'}">{'ДА' if rs.get('paused') else 'НЕ'}</b></div>
          </div>
          {'<div style="color:#ff3355;font-size:11px;margin-top:8px">⛔ Ботът е на пауза — достигнат дневен лимит!</div>' if rs.get('paused') else ''}
        </div>
        """, unsafe_allow_html=True)
        if rs.get("paused") and st.button("▶️ Продължи бота", key="resume_btn"):
            bot.risk.resume()
            st.rerun()

    # Recent trades
    if bot.demo.trades:
        st.markdown("#### 📋 Последни сделки")
        df_trades = pd.DataFrame(bot.demo.trades[-20:])
        df_trades["pnl_usdt"] = df_trades["pnl_usdt"].apply(
            lambda x: f"{'+'if x>=0 else ''}${x:.2f}"
        )
        df_trades["pnl_pct"] = df_trades["pnl_pct"].apply(
            lambda x: f"{'+'if x>=0 else ''}{x:.2f}%"
        )
        show_cols = ["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","exit_reason","closed_at"]
        show_cols = [c for c in show_cols if c in df_trades.columns]
        st.dataframe(df_trades[show_cols].iloc[::-1], use_container_width=True, height=300)

    # Auto-refresh
    if st.session_state.running:
        time.sleep(3)
        st.rerun()


# ══════════════════════════════════════════════════════════════
#  TAB 2: TRADINGVIEW CHART
# ══════════════════════════════════════════════════════════════

with tab_chart:

    # Symbol selector
    col_sym, col_tf, col_ex = st.columns(3)
    with col_sym:
        tv_symbol = st.selectbox("Символ", ["BINANCE:BTCUSDT","BINANCE:ETHUSDT","BINANCE:SOLUSDT",
                                             "MEXC:BTCUSDT","BINGX:BTCUSDT"], key="tv_sym")
    with col_tf:
        tv_tf = st.selectbox("Таймфрейм", ["1","5","15","30","60","240","D"], index=2, key="tv_tf")
    with col_ex:
        tv_theme = st.selectbox("Тема", ["dark","light"], key="tv_theme")

    # TradingView widget
    st.markdown(f"""
    <div style="border:1px solid #162035;border-radius:16px;overflow:hidden;margin:8px 0">
    <div class="tradingview-widget-container" style="height:500px">
      <div id="tradingview_nexus"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width":       "100%",
        "height":      500,
        "symbol":      "{tv_symbol}",
        "interval":    "{tv_tf}",
        "timezone":    "Etc/UTC",
        "theme":       "{tv_theme}",
        "style":       "1",
        "locale":      "en",
        "toolbar_bg":  "#0d1626",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "studies":     ["RSI@tv-basicstudies","MACD@tv-basicstudies","BB@tv-basicstudies"],
        "container_id": "tradingview_nexus",
        "show_popup_button": true,
      }});
      </script>
    </div>
    </div>
    """, unsafe_allow_html=True)

    # Bot signals overlay (plotly)
    signals_log = bot.get_signals_log()
    if signals_log:
        st.markdown("#### 🎯 Сигнали на бота (вписани на графиката)")
        df_sig = pd.DataFrame(signals_log)
        fig = go.Figure()
        longs  = df_sig[df_sig["signal"] == "LONG"]
        shorts = df_sig[df_sig["signal"] == "SHORT"]

        if not longs.empty:
            fig.add_trace(go.Scatter(
                x=longs["time"], y=longs["price"],
                mode="markers", name="LONG",
                marker=dict(color="#00ffaa", symbol="triangle-up", size=12),
                text=longs["confidence"].apply(lambda c: f"Conf: {c:.0f}%"),
            ))
        if not shorts.empty:
            fig.add_trace(go.Scatter(
                x=shorts["time"], y=shorts["price"],
                mode="markers", name="SHORT",
                marker=dict(color="#ff3355", symbol="triangle-down", size=12),
                text=shorts["confidence"].apply(lambda c: f"Conf: {c:.0f}%"),
            ))

        fig.update_layout(
            paper_bgcolor="#080f1e", plot_bgcolor="#080f1e",
            font_color="#d0e4f8", margin=dict(l=10,r=10,t=30,b=10),
            height=250, showlegend=True,
            xaxis=dict(gridcolor="#162035"),
            yaxis=dict(gridcolor="#162035"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 3: СТРАТЕГИЯ (Редактор)
# ══════════════════════════════════════════════════════════════

with tab_strat:

    st.markdown("### 🧠 Избери и редактирай стратегия")

    strategy_names = list(STRATEGY_TEMPLATES.keys())
    style_icons = {
        "scalp":      "⚡",
        "aggressive": "🔥",
        "trend":      "📈",
        "balanced":   "⚖️",
        "safe":       "🛡",
    }

    # Strategy cards
    cols = st.columns(len(strategy_names))
    for i, name in enumerate(strategy_names):
        tmpl = STRATEGY_TEMPLATES[name]
        icon = style_icons.get(tmpl.style, "🤖")
        is_active = bot.strategy._active_name == name
        with cols[i]:
            if st.button(
                f"{icon}\n{name.split()[0]}\n{'✅' if is_active else ''}",
                key=f"strat_{i}",
                help=tmpl.description,
            ):
                bot.select_strategy(name)
                st.rerun()

    st.markdown("---")

    # Active strategy editor
    active_cfg = bot.strategy.get_config_dict()
    st.markdown(f"#### ✏️ Редактиране: **{active_cfg['name']}**")
    st.caption(active_cfg["description"])

    with st.expander("📊 Индикаторни параметри", expanded=True):
        c1, c2, c3 = st.columns(3)

        with c1:
            rsi_p = st.number_input("RSI период", 5, 50, int(active_cfg["rsi_period"]), key="rsi_p")
            rsi_os = st.number_input("RSI Oversold", 10.0, 50.0, float(active_cfg["rsi_oversold"]), 1.0, key="rsi_os")
            rsi_ob = st.number_input("RSI Overbought", 50.0, 90.0, float(active_cfg["rsi_overbought"]), 1.0, key="rsi_ob")
        with c2:
            ef = st.number_input("EMA Fast",   3,  50, int(active_cfg["ema_fast"]),   key="ef")
            em = st.number_input("EMA Medium",  5, 100, int(active_cfg["ema_medium"]), key="em")
            es = st.number_input("EMA Slow",   10, 300, int(active_cfg["ema_slow"]),   key="es")
        with c3:
            mf  = st.number_input("MACD Fast",    3,  30, int(active_cfg["macd_fast"]),   key="mf")
            ms_  = st.number_input("MACD Slow",    5,  60, int(active_cfg["macd_slow"]),   key="ms_")
            msig = st.number_input("MACD Signal",  3,  20, int(active_cfg["macd_signal"]), key="msig")

        c4, c5 = st.columns(2)
        with c4:
            min_conf = st.slider("Min. Confidence %", 50.0, 95.0, float(active_cfg["min_confidence"]), 1.0, key="min_conf")
            vol_mult = st.slider("Volume Multiplier",  1.0,  3.0,  float(active_cfg["vol_multiplier"]), 0.1, key="vol_m")
        with c5:
            bb_p = st.number_input("BB период", 5, 50, int(active_cfg["bb_period"]), key="bb_p")
            bb_s = st.number_input("BB std",    1.0, 4.0, float(active_cfg["bb_std"]), 0.1, key="bb_s")

    with st.expander("⏰ Времеви филтър (Time Filter)"):
        tf_on = st.toggle("Активирай Time Filter", value=active_cfg["time_filter_on"], key="tf_on")
        if tf_on:
            st.markdown("**Търговски сесии (UTC)**")
            sessions = active_cfg.get("sessions", [])
            for i, sess in enumerate(sessions):
                sc1, sc2, sc3, sc4 = st.columns([2,2,2,1])
                sc1.write(sess["name"])
                sc2.text_input("Старт", sess["start"], key=f"sess_s_{i}")
                sc3.text_input("Край",  sess["end"],   key=f"sess_e_{i}")
                if sc4.button("🗑", key=f"del_sess_{i}"):
                    bot.strategy.active.time_filter.remove_session(sess["name"])
                    st.rerun()

            st.markdown("**Ръчен прозорец**")
            custom_on = st.toggle("Ръчен UTC прозорец", key="custom_tf_on")
            if custom_on:
                tc1, tc2 = st.columns(2)
                c_start = tc1.text_input("От (UTC)", active_cfg["custom_start"], key="c_start")
                c_end   = tc2.text_input("До (UTC)", active_cfg["custom_end"],   key="c_end")

    with st.expander("🧪 Персонализиран индикатор (Python код)"):
        st.markdown("""
        Напиши Python код за свой индикатор. Разполагаш с `df` (OHLCV DataFrame) и `ta`, `pd`, `np`.
        Добави нови колони към `df` и те ще бъдат достъпни в стратегията.
        """)
        custom_code = st.text_area(
            "Индикаторен код",
            value=bot.strategy.active.custom_indicator_code or
                  "# Пример:\n# df['my_signal'] = ta.ema(df['close'], length=7) > ta.ema(df['close'], length=21)",
            height=200,
            key="custom_code",
        )

    if st.button("💾 ЗАПАЗИ НАСТРОЙКИТЕ", key="save_strat"):
        params = {
            "rsi_period": rsi_p, "rsi_oversold": rsi_os, "rsi_overbought": rsi_ob,
            "ema_fast": ef, "ema_medium": em, "ema_slow": es,
            "macd_fast": mf, "macd_slow": ms_, "macd_signal": msig,
            "min_confidence": min_conf, "vol_multiplier": vol_mult,
            "bb_period": bb_p, "bb_std": bb_s,
            "custom_indicator_code": custom_code,
        }
        for k, v in params.items():
            bot.strategy.update_param(k, v)
        bot.strategy.update_time_filter(enabled=tf_on)
        st.success("✅ Стратегията е обновена!")


# ══════════════════════════════════════════════════════════════
#  TAB 4: DEMO СМЕТКА
# ══════════════════════════════════════════════════════════════

with tab_demo:

    st.markdown("### 💼 Демо Сметка")

    # Balance setter
    with st.expander("💰 Задай демо баланс", expanded=True):
        preset_cols = st.columns(5)
        for i, v in enumerate([500, 1000, 5000, 10000, 25000]):
            if preset_cols[i].button(f"${v:,}", key=f"preset_{v}"):
                bot.set_demo(True, float(v))
                st.session_state.demo_balance = float(v)
                st.rerun()

        c1, c2 = st.columns([3, 1])
        custom_bal = c1.number_input("Ръчна сума (USDT)", 100.0, 1_000_000.0,
                                     float(st.session_state.demo_balance), 100.0, key="custom_bal_inp")
        if c2.button("ЗАДАЙ", key="set_custom_bal"):
            bot.set_demo(True, custom_bal)
            st.session_state.demo_balance = custom_bal
            st.rerun()

    # Stats
    dm = bot.demo
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Баланс",    f"${dm.balance:,.2f}")
    c2.metric("P&L",       fmt_usdt(dm.pnl),    delta=fmt_pct(dm.pnl/dm.initial*100) if dm.initial else None)
    c3.metric("Win Rate",  f"{dm.win_rate}%")
    c4.metric("Сделки",    len(dm.trades))

    # Force close
    if dm.position:
        if st.button("🔴 ЗАТВОРИ ПОЗИЦИЯТА РЪЧНО", key="force_close"):
            cp = st.session_state.last_tick.get("current_price",
                 dm.position["entry"]) if st.session_state.last_tick else dm.position["entry"]
            dm.force_close(cp)
            st.rerun()

    if st.button("🔄 НУЛИРАЙ ДЕМО СМЕТКАТА", key="reset_demo"):
        bot.set_demo(True, st.session_state.demo_balance)
        st.rerun()

    # Trade history
    if dm.trades:
        st.markdown("#### 📋 Всички сделки")
        df_t = pd.DataFrame(dm.trades)
        st.dataframe(
            df_t[["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","exit_reason","closed_at"]].iloc[::-1],
            use_container_width=True, height=400
        )

        # Equity curve
        eq = dm.equity_curve
        if len(eq) > 1:
            df_eq = pd.DataFrame(eq)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_eq["time"], y=df_eq["balance"],
                fill="tozeroy", fillcolor="rgba(0,255,170,0.08)",
                line=dict(color="#00ffaa", width=2),
                mode="lines+markers",
                marker=dict(size=5),
                name="Баланс",
                text=df_eq.get("trade", pd.Series(dtype=str)),
                hovertemplate="%{text}<br>$%{y:,.2f}<extra></extra>",
            ))
            fig.add_hline(y=dm.initial, line_dash="dash", line_color="#4a6080",
                          annotation_text=f"Начало ${dm.initial:,.0f}")
            fig.update_layout(
                title="📈 Equity Curve",
                paper_bgcolor="#080f1e", plot_bgcolor="#080f1e",
                font_color="#d0e4f8",
                margin=dict(l=10,r=10,t=40,b=10), height=350,
                xaxis=dict(gridcolor="#162035", title=""),
                yaxis=dict(gridcolor="#162035", title="USDT"),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 5: BACKTEST
# ══════════════════════════════════════════════════════════════

with tab_bt:

    st.markdown("### 📉 Backtest Engine")

    c1, c2, c3 = st.columns(3)
    with c1:
        bt_days = st.selectbox("Период", [7, 14, 30], index=0, key="bt_days")
    with c2:
        bt_strat = st.selectbox("Стратегия", strategy_names, key="bt_strat")
    with c3:
        bt_lev = st.number_input("Леверидж", 1, 125, 10, key="bt_lev")

    if st.button("🚀 СТАРТИРАЙ BACKTEST", key="run_bt"):
        with st.spinner(f"Изпълнява се backtest {bt_days} дни..."):
            bot.select_strategy(bt_strat)
            bot.risk.update_config(leverage=bt_lev)
            result = bot.run_backtest(days=bt_days)
            st.session_state.bt_result = result

    if st.session_state.bt_result:
        res    = st.session_state.bt_result
        stats  = res.get("stats", {})
        trades = res.get("trades", [])
        equity = res.get("equity_curve", [])

        if "error" in res:
            st.error(res["error"])
        else:
            # Stats
            s1,s2,s3,s4,s5,s6 = st.columns(6)
            s1.metric("Начален",   f"${stats['initial']:,.0f}")
            s2.metric("Краен",     f"${stats['final']:,.0f}", delta=fmt_pct(stats['return_pct']))
            s3.metric("Win Rate",  f"{stats['win_rate']}%")
            s4.metric("Сделки",    stats['total_trades'])
            s5.metric("Max DD",    f"{stats['max_drawdown']:.2f}%")
            s6.metric("Prof. Fct", stats['profit_factor'])

            # Equity curve
            if equity:
                df_eq = pd.DataFrame(equity)
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=df_eq["time"], y=df_eq["balance"],
                    fill="tozeroy", fillcolor="rgba(0,170,255,0.08)",
                    line=dict(color="#00aaff", width=2),
                    name="Equity",
                ))
                fig_eq.add_hline(y=stats["initial"], line_dash="dash", line_color="#4a6080")
                fig_eq.update_layout(
                    title=f"📈 Equity Curve — {bt_days} дни",
                    paper_bgcolor="#080f1e", plot_bgcolor="#080f1e",
                    font_color="#d0e4f8",
                    margin=dict(l=10,r=10,t=40,b=10), height=320,
                    xaxis=dict(gridcolor="#162035"),
                    yaxis=dict(gridcolor="#162035", title="USDT"),
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            # Trade log
            if trades:
                st.markdown("#### 📋 Хронология на сделките")
                df_tr = pd.DataFrame(trades)
                def color_pnl(v):
                    return "color: #00ffaa" if v > 0 else "color: #ff3355"
                st.dataframe(
                    df_tr[["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","reason","opened","closed"]].iloc[::-1],
                    use_container_width=True, height=400
                )

                # PnL Distribution
                df_pnl = pd.DataFrame({"pnl": [t["pnl_usdt"] for t in trades]})
                fig_hist = px.histogram(
                    df_pnl, x="pnl", nbins=30,
                    color_discrete_sequence=["#00aaff"],
                    title="Разпределение на P&L",
                )
                fig_hist.update_layout(
                    paper_bgcolor="#080f1e", plot_bgcolor="#080f1e",
                    font_color="#d0e4f8", height=250,
                    margin=dict(l=10,r=10,t=40,b=10),
                )
                st.plotly_chart(fig_hist, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 6: НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════

with tab_settings:

    st.markdown("### ⚙️ Настройки")

    # API connection
    with st.expander("🔑 API Настройки", expanded=True):
        col_ex, col_mode = st.columns(2)
        with col_ex:
            exchange = st.selectbox("Борса", ["mexc","bingx"], key="exch_sel")
        with col_mode:
            mode = st.selectbox("Режим", ["futures","spot"], key="mode_sel")

        c1, c2 = st.columns(2)
        api_key = c1.text_input("API Key", type="password", key="api_key_inp")
        api_sec = c2.text_input("API Secret", type="password", key="api_sec_inp")

        lev_col, sym_col = st.columns(2)
        with lev_col:
            leverage = st.number_input("Леверидж", 1, 125, 10, key="lev_inp")
        with sym_col:
            symbol = st.selectbox("Символ", [
                "BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT","DOGE/USDT"
            ], key="sym_sel")

        use_demo = st.toggle("Демо режим (без реални средства)", value=True, key="demo_tog")

        if st.button("🔗 СВЪРЖИ СЕ", key="connect_btn"):
            if use_demo:
                bot.set_demo(True)
                st.success("✅ Демо режим активиран!")
            else:
                with st.spinner("Свързване..."):
                    ok = bot.setup(exchange=exchange, api_key=api_key,
                                   api_secret=api_sec, mode=mode, leverage=leverage)
                st.success("✅ Свързан!" if ok else "❌ Грешка при свързване")
            bot.set_symbol(symbol)
            st.session_state.api_saved = True

    # Risk settings
    with st.expander("🛡 Risk Management"):
        rc = bot.risk.cfg
        c1, c2, c3 = st.columns(3)
        with c1:
            risk_pct  = st.slider("Риск % на сделка", 0.5, 5.0, float(rc.risk_pct), 0.1, key="r_pct")
            max_pos   = st.slider("Макс. позиция %",  5.0, 50.0, float(rc.max_position_pct), 1.0, key="r_mpos")
        with c2:
            tp_pct    = st.number_input("TP %", 0.5, 20.0, float(rc.tp_pct), 0.1, key="r_tp")
            sl_pct    = st.number_input("SL %", 0.2, 10.0, float(rc.sl_pct), 0.1, key="r_sl")
            use_atr   = st.toggle("ATR-базиран TP/SL", value=rc.use_atr, key="r_atr")
        with c3:
            trail     = st.toggle("Trailing Stop", value=rc.trailing_stop, key="r_trail")
            trail_pct = st.number_input("Trailing %", 0.1, 5.0, float(rc.trailing_pct), 0.1, key="r_tpct")
            act_pct   = st.number_input("Активиране %", 0.1, 3.0, float(rc.trailing_activation_pct), 0.1, key="r_act")

        c4, c5 = st.columns(2)
        with c4:
            daily_lim = st.number_input("Дневен лимит загуба %", 1.0, 20.0, float(rc.daily_loss_limit_pct), 0.5, key="r_dlim")
        with c5:
            max_cons  = st.number_input("Макс. поред. загуби", 2, 10, int(rc.max_consecutive_losses), 1, key="r_mcons")

        if st.button("💾 ЗАПАЗИ РИСКА", key="save_risk"):
            bot.risk.update_config(
                risk_pct=risk_pct, max_position_pct=max_pos,
                tp_pct=tp_pct, sl_pct=sl_pct, use_atr=use_atr,
                trailing_stop=trail, trailing_pct=trail_pct,
                trailing_activation_pct=act_pct,
                daily_loss_limit_pct=daily_lim,
                max_consecutive_losses=int(max_cons),
            )
            st.success("✅ Риск настройките са запазени!")

    # AI Brain settings
    with st.expander("🤖 AI Brain"):
        use_ai   = st.toggle("Активирай OpenAI анализ", value=bot.cfg.use_ai, key="ai_tog")
        use_corr = st.toggle("Корелационен филтър (DXY/ETH)", value=bot.brain.corr_filter.enabled, key="corr_tog")
        if use_ai:
            ai_key = st.text_input("OpenAI API Key", type="password", key="ai_key_inp")
            if ai_key and st.button("Запази AI ключ", key="save_ai"):
                bot.brain._openai_key = ai_key
                bot.brain.use_ai      = True
                st.success("✅ AI активиран!")
        dxy_thr = st.slider("DXY прагова промяна %", 0.1, 2.0, 0.3, 0.05, key="dxy_thr")

        if st.button("💾 ЗАПАЗИ AI НАСТРОЙКИ", key="save_ai_cfg"):
            bot.brain.corr_filter.enabled       = use_corr
            bot.brain.corr_filter.dxy_threshold = dxy_thr
            bot.brain.use_ai                    = use_ai
            st.success("✅ AI настройките са запазени!")

    # Timeframe
    with st.expander("📡 Таймфрейм"):
        tf_opt = st.selectbox("Основен таймфрейм", ["1m","5m","15m","30m","1h","4h","1d"], index=2, key="tf_main")
        if st.button("Задай TF", key="set_tf"):
            bot.set_timeframe(tf_opt)
            st.success(f"TF = {tf_opt}")


# ══════════════════════════════════════════════════════════════
#  TAB 7: MULTI-TF ТРЕНД
# ══════════════════════════════════════════════════════════════

with tab_trend:

    st.markdown("### 🌍 Multi-Timeframe Тренд")

    if st.button("🔄 ОБНОВИ ТРЕНД АНАЛИЗ", key="refresh_trend"):
        with st.spinner("Зарежда данни..."):
            mtf_data   = bot._fetch_mtf()
            mtf_result = bot.brain.mtf_trend.analyze(mtf_data)
            st.session_state.mtf_result = mtf_result

    mtf_result = getattr(st.session_state, "mtf_result",
                         st.session_state.last_tick.get("mtf", {}) if st.session_state.last_tick else {})

    if mtf_result and "timeframes" in mtf_result:
        overall = mtf_result.get("overall", "N/A")
        ov_col  = "#00ffaa" if "BULLISH" in overall else "#ff3355" if "BEARISH" in overall else "#ffcc00"

        st.markdown(f"""
        <div class="nx-card" style="text-align:center">
          <div class="nx-label">ОБОБЩЕН ТРЕНД</div>
          <div style="font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:{ov_col}">
            {overall}
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Table
        rows = []
        for tf, data in sorted(mtf_result["timeframes"].items(),
                                key=lambda x: ["1m","5m","15m","30m","1h","4h","1d"].index(x[0])
                                if x[0] in ["1m","5m","15m","30m","1h","4h","1d"] else 99):
            trend = data.get("trend", "N/A")
            rows.append({
                "TF":     tf,
                "Тренд":  trend,
                "RSI":    data.get("rsi",  "—"),
                "EMA9":   data.get("ema9", "—"),
                "EMA21":  data.get("ema21","—"),
                "Цена":   data.get("price","—"),
            })

        df_mtf = pd.DataFrame(rows)
        st.dataframe(df_mtf, use_container_width=True, hide_index=True, height=300)

        # Chart
        bullish_tfs = sum(1 for r in rows if "BULLISH" in str(r["Тренд"]))
        bearish_tfs = sum(1 for r in rows if "BEARISH" in str(r["Тренд"]))
        neutral_tfs = len(rows) - bullish_tfs - bearish_tfs

        fig_pie = go.Figure(go.Pie(
            labels=["BULLISH","BEARISH","NEUTRAL"],
            values=[bullish_tfs, bearish_tfs, neutral_tfs],
            marker_colors=["#00ffaa","#ff3355","#ffcc00"],
            hole=0.5,
            textfont_size=12,
        ))
        fig_pie.update_layout(
            paper_bgcolor="#080f1e", font_color="#d0e4f8",
            margin=dict(l=0,r=0,t=30,b=0), height=250,
            showlegend=True,
            annotations=[dict(text=f"{bullish_tfs}/{len(rows)}<br>Bull", x=0.5, y=0.5,
                              font_size=14, showarrow=False, font_color="#00ffaa")]
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("👆 Натисни 'ОБНОВИ' за да заредиш multi-timeframe анализа.")


# ─────────────────────────────────────────────────────────────
#  FOOTER
# ─────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center;font-size:9px;color:#3a5570;
  letter-spacing:2px;padding:20px 0 8px;font-family:'Space Mono',monospace">
  NEXUS BOT PRO · НЕ Е ФИНАНСОВ СЪВЕТ · ИЗПОЛЗВАЙ НА СВОЙ РИСК
</div>
""", unsafe_allow_html=True)


# Safety fallback
try:
    if 'df' in locals() and df is not None and df.empty:
        st.warning("No chart data available.")
except:
    pass
