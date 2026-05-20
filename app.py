"""
app.py — NEXUS BOT PRO
Streamlit интерфейс — мобилен приоритет
• TradingView Live Chart (жива графика BTC)
• Backtest с реални данни + маркиране на сделки на графика
• Reset бутон на настройките
• Демо баланс от $1 до $1M
"""

import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
import time
from datetime import datetime

from engine import TradingBot, BotConfig
from risk_management import RiskConfig
from strategy_manager import STRATEGY_TEMPLATES
from engine import STRATEGY_RISK_DEFAULTS

st.set_page_config(
    page_title="NEXUS BOT PRO", page_icon="⚡",
    layout="wide", initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@700;800&display=swap');
#MainMenu,footer,header{visibility:hidden;}
.stDeployButton{display:none;}
:root{
  --bg:#040810;--bg2:#080f1e;--bg3:#0d1626;--border:#162035;
  --green:#00ffaa;--red:#ff3355;--blue:#00aaff;--yellow:#ffcc00;
  --text:#d0e4f8;--dim:#4a6080;
}
.stApp{background:var(--bg);font-family:'Space Mono',monospace;}
.stApp *{color:var(--text);}
[data-testid="stSidebar"]{background:var(--bg2);border-right:1px solid var(--border);}
.stTextInput input,.stNumberInput input,.stSelectbox select,.stTextArea textarea{
  background:var(--bg3)!important;border:1px solid var(--border)!important;
  color:var(--text)!important;border-radius:10px!important;
  font-family:'Space Mono',monospace!important;
}
.stButton>button{
  background:linear-gradient(135deg,#00ffaa,#00aaff)!important;
  color:#000!important;border:none!important;border-radius:12px!important;
  font-family:'Space Mono',monospace!important;font-weight:700!important;
  letter-spacing:1px!important;padding:10px 20px!important;width:100%!important;
}
.stButton>button:hover{opacity:0.85!important;}
.btn-reset>button{
  background:transparent!important;border:1px solid var(--red)!important;
  color:var(--red)!important;
}
.stTabs [data-baseweb="tab-list"]{
  background:var(--bg2);border-radius:12px;border:1px solid var(--border);gap:4px;padding:4px;
}
.stTabs [data-baseweb="tab"]{
  background:transparent;color:var(--dim);border-radius:8px;
  font-family:'Space Mono',monospace;font-size:11px;font-weight:700;
}
.stTabs [aria-selected="true"]{
  background:var(--bg3)!important;color:var(--text)!important;
  border:1px solid var(--border)!important;
}
[data-testid="metric-container"]{
  background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:14px;
}
[data-testid="metric-container"] label{font-size:9px!important;letter-spacing:2px!important;color:var(--dim)!important;}
[data-testid="metric-container"] [data-testid="stMetricValue"]{
  font-family:'Syne',sans-serif!important;font-size:22px!important;font-weight:800!important;
}
.streamlit-expanderHeader{
  background:var(--bg2)!important;border:1px solid var(--border)!important;
  border-radius:10px!important;font-family:'Space Mono',monospace!important;font-size:11px!important;
}
.nx-card{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:16px 18px;margin-bottom:12px;position:relative;
}
.nx-label{font-size:9px;color:var(--dim);letter-spacing:3px;margin-bottom:8px;}
.nx-value{font-family:'Syne',sans-serif;font-size:26px;font-weight:800;}
.pill{display:inline-block;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:700;letter-spacing:1px;}
.pill-long{background:#00ffaa18;border:1px solid #00ffaa;color:#00ffaa;}
.pill-short{background:#ff335518;border:1px solid #ff3355;color:#ff3355;}
.pill-hold{background:#ffcc0018;border:1px solid #ffcc00;color:#ffcc00;}
@media(max-width:768px){
  .nx-value{font-size:18px!important;}
  .stTabs [data-baseweb="tab"]{font-size:9px!important;padding:6px 4px!important;}
}
</style>
""", unsafe_allow_html=True)


# ── SESSION STATE ──────────────────────────────────────────────

if "bot" not in st.session_state:
    st.session_state.bot           = TradingBot()
    st.session_state.running       = False
    st.session_state.last_tick     = {}
    st.session_state.bt_result     = None
    st.session_state.bt_strat_name = ""
    st.session_state.api_saved     = False
    st.session_state.demo_balance  = 1_000.0

bot: TradingBot = st.session_state.bot

def fmt_price(p):
    try: return f"${float(p):,.2f}"
    except: return "—"

def fmt_pct(p):
    try:
        v = float(p)
        return f"{'+'if v>=0 else ''}{v:.2f}%"
    except: return "—"

def fmt_usdt(p):
    try:
        v = float(p)
        return f"{'+'if v>=0 else ''}${v:,.2f}"
    except: return "—"


# ── HEADER ────────────────────────────────────────────────────

col_logo, col_status, col_ctrl = st.columns([3, 3, 2])

tick = st.session_state.last_tick
price_disp = fmt_price(tick.get("current_price", 0)) if tick else "—"
sig_disp   = tick.get("signal", "—") if tick else "—"
sig_class  = {"LONG": "pill-long", "SHORT": "pill-short"}.get(sig_disp, "pill-hold")

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

with col_status:
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:14px;padding:10px 0">
      <div>
        <div style="font-size:9px;color:#4a6080;letter-spacing:2px">ЦЕНА</div>
        <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#fff">{price_disp}</div>
      </div>
      <span class="pill {sig_class}">{sig_disp}</span>
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

if st.session_state.running:
    result = bot.tick()
    st.session_state.last_tick = result
    tick = result

strategy_names = list(STRATEGY_TEMPLATES.keys())

tabs = st.tabs([
    "📊 DASHBOARD", "📈 ГРАФИКА", "🧠 СТРАТЕГИЯ",
    "💼 ДЕМО", "📉 BACKTEST", "⚙️ НАСТРОЙКИ", "🌍 ТРЕНД",
])
tab_dash, tab_chart, tab_strat, tab_demo, tab_bt, tab_settings, tab_trend = tabs


# ══════════════════════════════════════════════════════════════
#  TAB 1: DASHBOARD
# ══════════════════════════════════════════════════════════════

with tab_dash:
    c1, c2, c3, c4 = st.columns(4)
    demo_bal   = tick.get("demo_balance", bot.demo.balance) if tick else bot.demo.balance
    demo_pnl   = tick.get("demo_pnl",    bot.demo.pnl)     if tick else bot.demo.pnl
    win_rate   = tick.get("win_rate",    bot.demo.win_rate) if tick else 0
    confidence = tick.get("confidence",  0) if tick else 0
    sentiment  = tick.get("sentiment",   "NEUTRAL") if tick else "NEUTRAL"
    sent_color = {"BULLISH":"#00ffaa","BEARISH":"#ff3355","NEUTRAL":"#ffcc00"}.get(sentiment,"#ffcc00")

    c1.metric("💰 БАЛАНС",   f"${demo_bal:,.2f}")
    c2.metric("📊 P&L",      fmt_usdt(demo_pnl),  delta=fmt_pct(demo_pnl/demo_bal*100) if demo_bal else None)
    c3.metric("🎯 WIN RATE", f"{win_rate}%")
    c4.metric("🔥 CONF.",    f"{confidence:.0f}%")

    if tick:
        sig      = tick.get("signal","HOLD")
        sig_icon = {"LONG":"🟢","SHORT":"🔴","HOLD":"⚪"}.get(sig,"⚪")
        sig_col  = {"LONG":"#00ffaa","SHORT":"#ff3355","HOLD":"#ffcc00"}.get(sig,"#ffcc00")
        reasons  = tick.get("reasons",[])
        ai_cmt   = tick.get("ai_comment","")
        st.markdown(f"""
        <div class="nx-card">
          <div class="nx-label">⚡ AI СИГНАЛ — {tick.get('strategy','—')}</div>
          <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
            <div style="font-family:'Syne',sans-serif;font-size:32px;font-weight:800;color:{sig_col}">
              {sig_icon} {sig}
            </div>
            <div>
              <div style="font-size:11px;color:#4a6080">CONFIDENCE</div>
              <div style="font-family:'Syne',sans-serif;font-size:24px;font-weight:800;color:{sig_col}">{confidence:.0f}%</div>
            </div>
            <div style="margin-left:auto">
              <div style="font-size:11px;color:#4a6080">СЕНТИМЕНТ</div>
              <div style="font-weight:700;color:{sent_color}">{sentiment}</div>
            </div>
          </div>
          <div style="font-size:10px;color:#4a6080">{'<br>'.join(f'• {r}' for r in reasons[:6])}</div>
          {f'<div style="margin-top:10px;padding:10px;background:#0d1626;border-radius:8px;font-size:11px;border-left:2px solid #00aaff">🤖 {ai_cmt}</div>' if ai_cmt else ''}
        </div>
        """, unsafe_allow_html=True)

    pos = tick.get("demo_position") if tick else bot.demo.position
    if pos:
        cp   = tick.get("current_price", pos["entry"]) if tick else pos["entry"]
        upnl = (cp-pos["entry"])/pos["entry"]*100 if pos["direction"]=="LONG" \
               else (pos["entry"]-cp)/pos["entry"]*100
        u_col = "#00ffaa" if upnl >= 0 else "#ff3355"
        st.markdown(f"""
        <div class="nx-card" style="border-color:#00ffaa">
          <div class="nx-label">⚡ АКТИВНА ПОЗИЦИЯ — {pos['direction']}</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px">
            <div><div style="font-size:9px;color:#4a6080">ВХОД</div><div style="font-weight:700">${pos['entry']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">TAKE-PROFIT</div><div style="font-weight:700;color:#00ffaa">${pos['tp']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">STOP-LOSS</div><div style="font-weight:700;color:#ff3355">${pos['sl']:,.2f}</div></div>
            <div><div style="font-size:9px;color:#4a6080">UNREALIZED P&L</div><div style="font-weight:700;color:{u_col}">{upnl:+.2f}%</div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    rs = tick.get("risk_status",{}) if tick else bot.risk.get_status()
    if rs:
        st.markdown(f"""
        <div class="nx-card">
          <div class="nx-label">🛡 RISK STATUS</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;font-size:12px">
            <div>Дневна P&L: <b style="color:{'#00ffaa' if rs.get('daily_pnl',0)>=0 else '#ff3355'}">{fmt_usdt(rs.get('daily_pnl',0))}</b></div>
            <div>Поред. загуби: <b>{rs.get('consecutive_losses',0)}</b></div>
            <div>Пауза: <b style="color:{'#ff3355' if rs.get('paused') else '#00ffaa'}">{'ДА' if rs.get('paused') else 'НЕ'}</b></div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        if rs.get("paused") and st.button("▶️ Продължи бота", key="resume_btn"):
            bot.risk.resume(); st.rerun()

    if bot.demo.trades:
        st.markdown("#### 📋 Последни сделки")
        df_trades = pd.DataFrame(bot.demo.trades[-20:])
        df_trades["pnl_usdt"] = df_trades["pnl_usdt"].apply(lambda x: f"{'+'if x>=0 else ''}${x:.2f}")
        df_trades["pnl_pct"]  = df_trades["pnl_pct"].apply(lambda x: f"{'+'if x>=0 else ''}{x:.2f}%")
        cols_ = [c for c in ["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","exit_reason","closed_at"] if c in df_trades.columns]
        st.dataframe(df_trades[cols_].iloc[::-1], use_container_width=True, height=280)

    if st.session_state.running:
        time.sleep(3)
        st.rerun()


# ══════════════════════════════════════════════════════════════
#  TAB 2: ЖИВА ГРАФИКА (TradingView)
# ══════════════════════════════════════════════════════════════

with tab_chart:
    col_sym, col_tf, col_theme = st.columns(3)
    with col_sym:
        tv_symbol = st.selectbox("Символ", [
            "BINANCE:BTCUSDT","BINANCE:ETHUSDT","BINANCE:SOLUSDT",
            "MEXC:BTCUSDT","BINGX:BTCUSDT",
        ], key="tv_sym")
    with col_tf:
        tv_tf = st.selectbox("Таймфрейм", ["1","5","15","30","60","240","D"], index=2, key="tv_tf")
    with col_theme:
        tv_theme = st.selectbox("Тема", ["dark","light"], key="tv_theme")

    # Жива TradingView графика — пълен widget с всички функции
    components.html(f"""<!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
      body{{margin:0;padding:0;background:#040810;}}
      #tv_wrap{{border:1px solid #162035;border-radius:14px;overflow:hidden;}}
    </style>
    </head><body>
    <div id="tv_wrap">
      <div class="tradingview-widget-container" style="height:520px;width:100%">
        <div id="tradingview_nexus" style="height:100%;width:100%"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
          "autosize": true,
          "symbol": "{tv_symbol}",
          "interval": "{tv_tf}",
          "timezone": "Etc/UTC",
          "theme": "{tv_theme}",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#0d1626",
          "enable_publishing": false,
          "withdateranges": true,
          "hide_side_toolbar": false,
          "allow_symbol_change": true,
          "watchlist": ["BINANCE:BTCUSDT","BINANCE:ETHUSDT","BINANCE:SOLUSDT"],
          "details": true,
          "hotlist": true,
          "calendar": false,
          "studies": [
            "RSI@tv-basicstudies",
            "MACD@tv-basicstudies",
            "BB@tv-basicstudies",
            "Volume@tv-basicstudies"
          ],
          "container_id": "tradingview_nexus",
          "show_popup_button": true,
          "popup_width": "1000",
          "popup_height": "650"
        }});
        </script>
      </div>
    </div>
    </body></html>""", height=540, scrolling=False)

    # Сигнали overlay
    signals_log = bot.get_signals_log()
    if signals_log:
        st.markdown("#### 🎯 Сигнали на бота")
        df_sig = pd.DataFrame(signals_log)
        fig = go.Figure()
        longs  = df_sig[df_sig["signal"]=="LONG"]
        shorts = df_sig[df_sig["signal"]=="SHORT"]
        if not longs.empty:
            fig.add_trace(go.Scatter(
                x=longs["time"], y=longs["price"], mode="markers", name="LONG",
                marker=dict(color="#00ffaa", symbol="triangle-up", size=14),
                text=longs["confidence"].apply(lambda c: f"LONG {c:.0f}%"),
            ))
        if not shorts.empty:
            fig.add_trace(go.Scatter(
                x=shorts["time"], y=shorts["price"], mode="markers", name="SHORT",
                marker=dict(color="#ff3355", symbol="triangle-down", size=14),
                text=shorts["confidence"].apply(lambda c: f"SHORT {c:.0f}%"),
            ))
        fig.update_layout(
            paper_bgcolor="#080f1e", plot_bgcolor="#080f1e", font_color="#d0e4f8",
            margin=dict(l=10,r=10,t=30,b=10), height=220, showlegend=True,
            xaxis=dict(gridcolor="#162035"), yaxis=dict(gridcolor="#162035"),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 3: СТРАТЕГИЯ
# ══════════════════════════════════════════════════════════════

with tab_strat:
    st.markdown("### 🧠 Избери и редактирай стратегия")
    style_icons = {"scalp":"⚡","aggressive":"🔥","trend":"📈","balanced":"⚖️","safe":"🛡"}

    cols = st.columns(len(strategy_names))
    for i, name in enumerate(strategy_names):
        tmpl = STRATEGY_TEMPLATES[name]
        icon = style_icons.get(tmpl.style,"🤖")
        is_active = bot.strategy._active_name == name
        tgt = getattr(tmpl, 'target_days', '?')
        with cols[i]:
            if st.button(f"{icon}\n{name.split()[0]}\n{'✅' if is_active else ''}", key=f"strat_{i}", help=f"{tmpl.description}\nЦел: {tgt} дни"):
                bot.select_strategy(name)
                st.rerun()

    # Показваме info за активната стратегия
    active_tmpl = STRATEGY_TEMPLATES.get(bot.strategy._active_name)
    if active_tmpl:
        tgt = getattr(active_tmpl, 'target_days', '?')
        st.info(f"📌 **{active_tmpl.name}** — {active_tmpl.description} | Цел: **{tgt} дни** за 2x")

    st.markdown("---")
    active_cfg = bot.strategy.get_config_dict()
    st.markdown(f"#### ✏️ Редактиране: **{active_cfg['name']}**")

    with st.expander("📊 Индикаторни параметри", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            rsi_p  = st.number_input("RSI период",   5, 50, int(active_cfg["rsi_period"]),    key="rsi_p")
            rsi_os = st.number_input("RSI Oversold", 10.0,50.0, float(active_cfg["rsi_oversold"]),  1.0, key="rsi_os")
            rsi_ob = st.number_input("RSI Overbought",50.0,90.0, float(active_cfg["rsi_overbought"]),1.0, key="rsi_ob")
        with c2:
            ef = st.number_input("EMA Fast",   3,  50,  int(active_cfg["ema_fast"]),   key="ef")
            em = st.number_input("EMA Medium", 5, 100,  int(active_cfg["ema_medium"]), key="em")
            es = st.number_input("EMA Slow",  10, 300,  int(active_cfg["ema_slow"]),   key="es")
        with c3:
            mf   = st.number_input("MACD Fast",   3, 30, int(active_cfg["macd_fast"]),   key="mf")
            ms_  = st.number_input("MACD Slow",   5, 60, int(active_cfg["macd_slow"]),   key="ms_")
            msig = st.number_input("MACD Signal", 3, 20, int(active_cfg["macd_signal"]), key="msig")

        c4, c5 = st.columns(2)
        with c4:
            min_conf = st.slider("Min. Confidence %", 50.0, 95.0, float(active_cfg["min_confidence"]), 1.0, key="min_conf")
            vol_mult = st.slider("Volume Multiplier",  1.0,  3.0,  float(active_cfg["vol_multiplier"]), 0.1, key="vol_m")
        with c5:
            bb_p = st.number_input("BB период", 5, 50, int(active_cfg["bb_period"]), key="bb_p")
            bb_s = st.number_input("BB std",  1.0, 4.0, float(active_cfg["bb_std"]), 0.1, key="bb_s")

    with st.expander("⏰ Времеви филтър"):
        tf_on = st.toggle("Активирай Time Filter", value=active_cfg["time_filter_on"], key="tf_on")

    c_save, c_reset = st.columns(2)
    with c_save:
        if st.button("💾 ЗАПАЗИ НАСТРОЙКИТЕ", key="save_strat"):
            for k,v in [("rsi_period",rsi_p),("rsi_oversold",rsi_os),("rsi_overbought",rsi_ob),
                        ("ema_fast",ef),("ema_medium",em),("ema_slow",es),
                        ("macd_fast",mf),("macd_slow",ms_),("macd_signal",msig),
                        ("min_confidence",min_conf),("vol_multiplier",vol_mult),
                        ("bb_period",bb_p),("bb_std",bb_s)]:
                bot.strategy.update_param(k,v)
            bot.strategy.update_time_filter(enabled=tf_on)
            st.success("✅ Стратегията е обновена!")

    with c_reset:
        st.markdown('<div class="btn-reset">', unsafe_allow_html=True)
        if st.button("🔄 РЕСЕТ ДО ФАБРИЧНИ", key="reset_strat"):
            bot.strategy.reset_to_default()
            st.success(f"✅ '{bot.strategy._active_name}' е нулирана до фабрични настройки!")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  TAB 4: ДЕМО
# ══════════════════════════════════════════════════════════════

with tab_demo:
    st.markdown("### 💼 Демо Сметка")

    with st.expander("💰 Задай демо баланс", expanded=True):
        preset_cols = st.columns(6)
        for i, v in enumerate([10, 20, 100, 500, 1000, 5000]):
            if preset_cols[i].button(f"${v:,}", key=f"preset_{v}"):
                bot.set_demo(True, float(v))
                st.session_state.demo_balance = float(v)
                st.rerun()
        c1, c2 = st.columns([3,1])
        custom_bal = c1.number_input("Ръчна сума (USDT)", 1.0, 1_000_000.0,
                                     float(st.session_state.demo_balance), 1.0, key="custom_bal_inp")
        if c2.button("ЗАДАЙ", key="set_custom_bal"):
            bot.set_demo(True, custom_bal)
            st.session_state.demo_balance = custom_bal
            st.rerun()

    dm = bot.demo
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Баланс",   f"${dm.balance:,.2f}")
    c2.metric("P&L",      fmt_usdt(dm.pnl), delta=fmt_pct(dm.pnl/dm.initial*100) if dm.initial else None)
    c3.metric("Win Rate", f"{dm.win_rate}%")
    c4.metric("Сделки",   len(dm.trades))

    if dm.position and st.button("🔴 ЗАТВОРИ ПОЗИЦИЯТА РЪЧНО", key="force_close"):
        cp = st.session_state.last_tick.get("current_price", dm.position["entry"]) if st.session_state.last_tick else dm.position["entry"]
        dm.force_close(cp); st.rerun()

    if st.button("🔄 НУЛИРАЙ ДЕМО СМЕТКАТА", key="reset_demo"):
        bot.set_demo(True, st.session_state.demo_balance); st.rerun()

    if dm.trades:
        st.markdown("#### 📋 Всички сделки")
        df_t = pd.DataFrame(dm.trades)
        cols_ = [c for c in ["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","exit_reason","closed_at"] if c in df_t.columns]
        st.dataframe(df_t[cols_].iloc[::-1], use_container_width=True, height=350)

        eq = dm.equity_curve
        if len(eq) > 1:
            df_eq = pd.DataFrame(eq)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_eq["time"], y=df_eq["balance"],
                fill="tozeroy", fillcolor="rgba(0,255,170,0.08)",
                line=dict(color="#00ffaa",width=2), mode="lines+markers",
                marker=dict(size=5), name="Баланс",
                text=df_eq.get("trade", pd.Series(dtype=str)),
                hovertemplate="%{text}<br>$%{y:,.2f}<extra></extra>",
            ))
            fig.add_hline(y=dm.initial, line_dash="dash", line_color="#4a6080",
                          annotation_text=f"Начало ${dm.initial:,.0f}")
            fig.update_layout(
                title="📈 Equity Curve",
                paper_bgcolor="#080f1e", plot_bgcolor="#080f1e", font_color="#d0e4f8",
                margin=dict(l=10,r=10,t=40,b=10), height=320,
                xaxis=dict(gridcolor="#162035"), yaxis=dict(gridcolor="#162035",title="USDT"),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 5: BACKTEST с реални данни + маркиране на свещна графика
# ══════════════════════════════════════════════════════════════

with tab_bt:
    st.markdown("### 📉 Backtest Engine — Реални данни")

    c1, c2, c3 = st.columns(3)
    with c1: bt_days  = st.selectbox("Период", [7,14,30], index=0, key="bt_days")
    with c2: bt_strat = st.selectbox("Стратегия", strategy_names, key="bt_strat")
    with c3: bt_lev   = st.number_input("Леверидж", 1, 125, 10, key="bt_lev")

    if st.button("🚀 СТАРТИРАЙ BACKTEST", key="run_bt"):
        with st.spinner(f"Зарежда се {bt_days} дни реални данни за {bt_strat}..."):
            prev_strategy = bot.strategy._active_name
            bot.select_strategy(bt_strat)
            bot.risk.update_config(leverage=bt_lev)
            from risk_management import DailyGuard
            bot.risk.daily = DailyGuard(bot.risk.cfg)
            result = bot.run_backtest(days=bt_days)
            bot.select_strategy(prev_strategy)
            st.session_state.bt_result     = result
            st.session_state.bt_strat_name = bt_strat

    if st.session_state.bt_result:
        res    = st.session_state.bt_result
        stats  = res.get("stats", {})
        trades = res.get("trades", [])
        equity = res.get("equity_curve", [])
        ohlcv  = res.get("ohlcv", [])

        if "error" in res:
            st.error(res["error"])
        else:
            strat_name = st.session_state.bt_strat_name
            ret_pct    = stats.get("return_pct", 0)
            ret_color  = "#00ffaa" if ret_pct >= 0 else "#ff3355"

            # Stats
            st.markdown(f"""
            <div class="nx-card">
              <div class="nx-label">📊 РЕЗУЛТАТИ — {strat_name} | {bt_days} дни</div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
                <div><div style="font-size:9px;color:#4a6080">НАЧАЛЕН</div>
                  <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800">${stats.get('initial',0):,.0f}</div></div>
                <div><div style="font-size:9px;color:#4a6080">КРАЕН</div>
                  <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:{ret_color}">${stats.get('final',0):,.2f}</div></div>
                <div><div style="font-size:9px;color:#4a6080">ДОХОДНОСТ</div>
                  <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:{ret_color}">{ret_pct:+.2f}%</div></div>
                <div><div style="font-size:9px;color:#4a6080">WIN RATE</div>
                  <div style="font-family:'Syne',sans-serif;font-size:18px;font-weight:800">{stats.get('win_rate',0)}%</div></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            s1,s2,s3,s4 = st.columns(4)
            s1.metric("Сделки",    stats.get("total_trades",0))
            s2.metric("Max DD",    f"{stats.get('max_drawdown',0):.2f}%")
            s3.metric("Prof. Fct", stats.get("profit_factor",0))
            s4.metric("Avg R:R",   stats.get("avg_rr",0))

            # ── СВЕЩНА ГРАФИКА С МАРКИРАНЕ НА СДЕЛКИТЕ ───────────
            if ohlcv and trades:
                st.markdown("#### 📊 Графика с маркирани сделки")
                try:
                    df_ohl = pd.DataFrame(ohlcv)
                    # Намираме timestamp колоната
                    ts_col = next((c for c in df_ohl.columns if "time" in c.lower() or "index" in c.lower()), None)
                    if ts_col:
                        df_ohl[ts_col] = pd.to_datetime(df_ohl[ts_col])
                        x_vals = df_ohl[ts_col]
                    else:
                        x_vals = list(range(len(df_ohl)))

                    fig_candle = go.Figure()

                    # Свещи
                    fig_candle.add_trace(go.Candlestick(
                        x=x_vals,
                        open=df_ohl["open"],
                        high=df_ohl["high"],
                        low=df_ohl["low"],
                        close=df_ohl["close"],
                        name="BTC/USDT",
                        increasing_line_color="#00ffaa",
                        decreasing_line_color="#ff3355",
                        increasing_fillcolor="rgba(0,255,170,0.15)",
                        decreasing_fillcolor="rgba(255,51,85,0.15)",
                    ))

                    # Маркираме сделките
                    for t in trades:
                        oi = t.get("opened_i", 0)
                        ci = t.get("closed_i", 0)
                        x_open  = x_vals.iloc[oi] if hasattr(x_vals, 'iloc') and oi < len(x_vals) else oi
                        x_close = x_vals.iloc[ci] if hasattr(x_vals, 'iloc') and ci < len(x_vals) else ci
                        is_long = t["direction"] == "LONG"
                        col_in  = "#00ffaa" if is_long else "#ff3355"
                        col_out = "#00ffaa" if t["pnl_usdt"] > 0 else "#ff3355"
                        sym_in  = "triangle-up" if is_long else "triangle-down"

                        # Вход
                        fig_candle.add_trace(go.Scatter(
                            x=[x_open], y=[t["entry"]],
                            mode="markers+text",
                            marker=dict(color=col_in, symbol=sym_in, size=14, line=dict(width=1,color="#fff")),
                            text=[f"{'▲' if is_long else '▼'} {t['direction']}"],
                            textposition="top center" if is_long else "bottom center",
                            textfont=dict(size=9, color=col_in),
                            showlegend=False,
                            hovertemplate=f"<b>ВХОД {t['direction']}</b><br>Цена: ${t['entry']:,.2f}<br>TP: ${t['tp']:,.2f}<br>SL: ${t['sl']:,.2f}<extra></extra>",
                        ))

                        # Изход
                        fig_candle.add_trace(go.Scatter(
                            x=[x_close], y=[t["exit"]],
                            mode="markers+text",
                            marker=dict(color=col_out, symbol="x", size=11, line=dict(width=2,color="#fff")),
                            text=[f"{'✅' if t['pnl_usdt']>0 else '⛔'} {t['pnl_pct']:+.1f}%"],
                            textposition="bottom center" if is_long else "top center",
                            textfont=dict(size=9, color=col_out),
                            showlegend=False,
                            hovertemplate=f"<b>ИЗХОД {t['reason']}</b><br>Цена: ${t['exit']:,.2f}<br>P&L: ${t['pnl_usdt']:+.2f}<extra></extra>",
                        ))

                        # Линия между вход и изход
                        fig_candle.add_shape(type="line",
                            x0=x_open, y0=t["entry"], x1=x_close, y1=t["exit"],
                            line=dict(color=col_out, width=1, dash="dot"),
                        )

                        # TP и SL нива
                        fig_candle.add_shape(type="line",
                            x0=x_open, y0=t["tp"], x1=x_close, y1=t["tp"],
                            line=dict(color="#00ffaa", width=0.8, dash="dash"),
                        )
                        fig_candle.add_shape(type="line",
                            x0=x_open, y0=t["sl"], x1=x_close, y1=t["sl"],
                            line=dict(color="#ff3355", width=0.8, dash="dash"),
                        )

                    fig_candle.update_layout(
                        title=f"📊 {strat_name} — {bt_days} дни | {len(trades)} сделки",
                        paper_bgcolor="#080f1e", plot_bgcolor="#080f1e", font_color="#d0e4f8",
                        margin=dict(l=10,r=10,t=50,b=10), height=520,
                        xaxis=dict(gridcolor="#162035", rangeslider=dict(visible=False)),
                        yaxis=dict(gridcolor="#162035", title="USDT"),
                        showlegend=False,
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_candle, use_container_width=True)
                except Exception as e:
                    st.warning(f"Графиката не може да се покаже: {e}")

            # Equity curve
            if equity:
                df_eq = pd.DataFrame(equity)
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=df_eq["time"], y=df_eq["balance"],
                    fill="tozeroy", fillcolor="rgba(0,170,255,0.08)",
                    line=dict(color="#00aaff",width=2), name="Equity",
                ))
                # Маркираме TP/SL точките
                for t in trades:
                    col = "#00ffaa" if t["pnl_usdt"] > 0 else "#ff3355"
                    fig_eq.add_trace(go.Scatter(
                        x=[t["closed_ts"]], y=[t["balance"]],
                        mode="markers",
                        marker=dict(color=col, size=8, symbol="circle"),
                        showlegend=False,
                        hovertemplate=f"<b>{t['direction']} {t['reason']}</b><br>P&L: ${t['pnl_usdt']:+.2f}<br>Баланс: ${t['balance']:,.2f}<extra></extra>",
                    ))
                fig_eq.add_hline(y=stats["initial"], line_dash="dash", line_color="#4a6080",
                                 annotation_text=f"Начало ${stats['initial']:,.0f}")
                fig_eq.update_layout(
                    title="📈 Equity Curve",
                    paper_bgcolor="#080f1e", plot_bgcolor="#080f1e", font_color="#d0e4f8",
                    margin=dict(l=10,r=10,t=40,b=10), height=300,
                    xaxis=dict(gridcolor="#162035"), yaxis=dict(gridcolor="#162035",title="USDT"),
                    showlegend=False,
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            # Trade log
            if trades:
                st.markdown("#### 📋 Хронология на сделките")
                df_tr = pd.DataFrame(trades)
                show = [c for c in ["direction","entry","exit","tp","sl","pnl_pct","pnl_usdt","rr","reason","opened_ts","closed_ts"] if c in df_tr.columns]
                st.dataframe(df_tr[show].iloc[::-1], use_container_width=True, height=350)

                # PnL Distribution
                fig_hist = px.histogram(
                    pd.DataFrame({"P&L ($)":[t["pnl_usdt"] for t in trades]}),
                    x="P&L ($)", nbins=20,
                    color_discrete_sequence=["#00aaff"],
                    title="Разпределение на P&L",
                )
                fig_hist.update_layout(
                    paper_bgcolor="#080f1e", plot_bgcolor="#080f1e",
                    font_color="#d0e4f8", height=220,
                    margin=dict(l=10,r=10,t=40,b=10),
                )
                st.plotly_chart(fig_hist, use_container_width=True)


# ══════════════════════════════════════════════════════════════
#  TAB 6: НАСТРОЙКИ с Reset бутони
# ══════════════════════════════════════════════════════════════

with tab_settings:
    st.markdown("### ⚙️ Настройки")

    with st.expander("🔑 API Настройки", expanded=True):
        col_ex, col_mode = st.columns(2)
        with col_ex:   exchange = st.selectbox("Борса",  ["mexc","bingx"], key="exch_sel")
        with col_mode: mode     = st.selectbox("Режим",  ["futures","spot"], key="mode_sel")

        c1, c2 = st.columns(2)
        api_key = c1.text_input("API Key",    type="password", key="api_key_inp")
        api_sec = c2.text_input("API Secret", type="password", key="api_sec_inp")

        lev_col, sym_col = st.columns(2)
        with lev_col: leverage = st.number_input("Леверидж", 1, 125, 10, key="lev_inp")
        with sym_col: symbol   = st.selectbox("Символ", ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT","DOGE/USDT"], key="sym_sel")

        use_demo = st.toggle("Демо режим", value=True, key="demo_tog")

        if st.button("🔗 СВЪРЖИ СЕ", key="connect_btn"):
            if use_demo:
                bot.set_demo(True)
                st.success("✅ Демо режим активиран!")
            else:
                with st.spinner("Свързване..."):
                    ok = bot.setup(exchange=exchange, api_key=api_key, api_secret=api_sec, mode=mode, leverage=leverage)
                st.success("✅ Свързан!" if ok else "❌ Грешка при свързване")
            bot.set_symbol(symbol)
            st.session_state.api_saved = True

    with st.expander("🛡 Risk Management"):
        rc = bot.risk.cfg

        # Бутони за предефинирани настройки по стратегия
        st.markdown("**⚡ Бързи настройки по стратегия:**")
        risk_btns = st.columns(len(strategy_names))
        for i, sname in enumerate(strategy_names):
            with risk_btns[i]:
                short = sname.split()[0]
                if st.button(f"{short}", key=f"risk_preset_{i}"):
                    bot.apply_strategy_risk_defaults(sname)
                    st.success(f"✅ Приложени настройки за {sname}")
                    st.rerun()

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            risk_pct = st.slider("Риск % на сделка", 0.5, 10.0, float(rc.risk_pct), 0.5, key="r_pct")
            max_pos  = st.slider("Макс. позиция %",  5.0, 50.0, float(rc.max_position_pct), 1.0, key="r_mpos")
        with c2:
            tp_pct   = st.number_input("TP %",  0.5, 20.0, float(rc.tp_pct),  0.1, key="r_tp")
            sl_pct   = st.number_input("SL %",  0.2, 10.0, float(rc.sl_pct),  0.1, key="r_sl")
            use_atr  = st.toggle("ATR-базиран TP/SL", value=rc.use_atr, key="r_atr")
        with c3:
            atr_tp   = st.number_input("ATR TP множител", 1.0, 8.0, float(rc.atr_tp_mult), 0.5, key="r_atp")
            atr_sl   = st.number_input("ATR SL множител", 0.5, 4.0, float(rc.atr_sl_mult), 0.1, key="r_asl")
            trail    = st.toggle("Trailing Stop", value=rc.trailing_stop, key="r_trail")

        c4, c5, c6 = st.columns(3)
        with c4: trail_pct  = st.number_input("Trailing %", 0.1, 5.0, float(rc.trailing_pct), 0.1, key="r_tpct")
        with c5: act_pct    = st.number_input("Активиране %", 0.1, 5.0, float(rc.trailing_activation_pct), 0.1, key="r_act")
        with c6: daily_lim  = st.number_input("Дневен лимит загуба %", 1.0, 25.0, float(rc.daily_loss_limit_pct), 0.5, key="r_dlim")

        max_cons = st.number_input("Макс. поред. загуби", 2, 15, int(rc.max_consecutive_losses), 1, key="r_mcons")

        cs, cr = st.columns(2)
        with cs:
            if st.button("💾 ЗАПАЗИ РИСКА", key="save_risk"):
                bot.risk.update_config(
                    risk_pct=risk_pct, max_position_pct=max_pos,
                    tp_pct=tp_pct, sl_pct=sl_pct, use_atr=use_atr,
                    atr_tp_mult=atr_tp, atr_sl_mult=atr_sl,
                    trailing_stop=trail, trailing_pct=trail_pct,
                    trailing_activation_pct=act_pct,
                    daily_loss_limit_pct=daily_lim,
                    max_consecutive_losses=int(max_cons),
                )
                st.success("✅ Риск настройките са запазени!")

        with cr:
            st.markdown('<div class="btn-reset">', unsafe_allow_html=True)
            if st.button("🔄 РЕСЕТ НА РИСКА", key="reset_risk"):
                # Фабрични стойности
                bot.risk.update_config(
                    risk_pct=3.0, max_position_pct=35.0,
                    tp_pct=5.0, sl_pct=1.2, use_atr=True,
                    atr_tp_mult=4.0, atr_sl_mult=1.0,
                    trailing_stop=True, trailing_pct=1.5,
                    trailing_activation_pct=1.2,
                    daily_loss_limit_pct=12.0, max_consecutive_losses=6,
                )
                st.success("✅ Риск настройките са нулирани!")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("🤖 AI Brain"):
        use_ai   = st.toggle("Активирай OpenAI анализ", value=bot.cfg.use_ai, key="ai_tog")
        use_corr = st.toggle("Корелационен филтър", value=bot.brain.corr_filter.enabled, key="corr_tog")
        if use_ai:
            ai_key = st.text_input("OpenAI API Key", type="password", key="ai_key_inp")
            if ai_key and st.button("Запази AI ключ", key="save_ai"):
                bot.brain._openai_key = ai_key
                bot.brain.use_ai      = True
                st.success("✅ AI активиран!")

        if st.button("💾 ЗАПАЗИ AI НАСТРОЙКИ", key="save_ai_cfg"):
            bot.brain.corr_filter.enabled = use_corr
            bot.brain.use_ai              = use_ai
            st.success("✅ AI настройките са запазени!")

    with st.expander("📡 Таймфрейм"):
        tf_opt = st.selectbox("Основен TF", ["1m","5m","15m","30m","1h","4h","1d"], index=2, key="tf_main")
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

    mtf_result = getattr(st.session_state,"mtf_result",
                         st.session_state.last_tick.get("mtf",{}) if st.session_state.last_tick else {})

    if mtf_result and "timeframes" in mtf_result:
        overall = mtf_result.get("overall","N/A")
        ov_col  = "#00ffaa" if "BULLISH" in overall else "#ff3355" if "BEARISH" in overall else "#ffcc00"
        st.markdown(f"""
        <div class="nx-card" style="text-align:center">
          <div class="nx-label">ОБОБЩЕН ТРЕНД</div>
          <div style="font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:{ov_col}">{overall}</div>
        </div>
        """, unsafe_allow_html=True)

        rows = []
        tf_order = ["1m","5m","15m","30m","1h","4h","1d"]
        for tf, data in sorted(mtf_result["timeframes"].items(), key=lambda x: tf_order.index(x[0]) if x[0] in tf_order else 99):
            rows.append({"TF":tf,"Тренд":data.get("trend","N/A"),"RSI":data.get("rsi","—"),
                         "EMA9":data.get("ema9","—"),"EMA21":data.get("ema21","—"),"Цена":data.get("price","—")})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=280)

        bullish = sum(1 for r in rows if "BULLISH" in str(r["Тренд"]))
        bearish = sum(1 for r in rows if "BEARISH" in str(r["Тренд"]))
        neutral = len(rows) - bullish - bearish
        fig_pie = go.Figure(go.Pie(
            labels=["BULLISH","BEARISH","NEUTRAL"], values=[bullish,bearish,neutral],
            marker_colors=["#00ffaa","#ff3355","#ffcc00"], hole=0.5, textfont_size=12,
        ))
        fig_pie.update_layout(
            paper_bgcolor="#080f1e", font_color="#d0e4f8",
            margin=dict(l=0,r=0,t=20,b=0), height=230, showlegend=True,
            annotations=[dict(text=f"{bullish}/{len(rows)}<br>Bull",x=0.5,y=0.5,
                              font_size=14,showarrow=False,font_color="#00ffaa")]
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("👆 Натисни 'ОБНОВИ' за да заредиш multi-timeframe анализа.")


# ── FOOTER ───────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center;font-size:9px;color:#3a5570;
  letter-spacing:2px;padding:20px 0 8px;font-family:'Space Mono',monospace">
  NEXUS BOT PRO · НЕ Е ФИНАНСОВ СЪВЕТ · ИЗПОЛЗВАЙ НА СВОЙ РИСК
</div>
""", unsafe_allow_html=True)
