import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import os
import time
from tradeguard_engine import TradeGuardAI

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="TradeGuard Pro Terminal", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
    <style>
    .metric-container { background-color: #0E1117; border: 1px solid #262730; border-radius: 8px; padding: 12px; text-align: center; }
    .metric-value { font-size: 22px; font-weight: 700; color: #f0f6fc; }
    .metric-label { font-size: 11px; color: #8b949e; text-transform: uppercase; margin-bottom: 5px; }
    .live-dot { color: #00E096; font-weight: bold; animation: pulse 2s infinite; display: inline-block; margin-right: 8px; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .big-score { font-size: 80px !important; font-weight: 900; line-height: 1; text-align: center; }
    .stChatMessage { background-color: #161b22; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. MOTORU YÜKLE ---
@st.cache_resource
def load_engine():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ["latest_setup.csv", "data.csv"]:
        path = os.path.join(current_dir, name)
        if os.path.exists(path): return TradeGuardAI(path)
    return None

engine = load_engine()
if not engine: st.error("⚠️ CSV Dosyası Yok! Lütfen GitHub'a 'latest_setup.csv' yükleyin."); st.stop()

# --- 2. CANLI VERİ ---
def get_live_metrics():
    try:
        res = requests.get("https://api.binance.us/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=2).json()
        price, change = float(res['lastPrice']), float(res['priceChangePercent'])
        try:
            w_res = requests.get("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            whale = float(w_res[0]['longAccount'])
            r_res = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            retail = float(r_res[0]['longAccount'])
        except: whale, retail = 0.5, 0.5
        return price, change, whale, retail
    except: return 0, 0, 0.5, 0.5

btc_price, btc_change, whale, retail = get_live_metrics()

# --- 3. ÜST HEADER ---
st.markdown(f"### <span class='live-dot'>●</span> TradeGuard Pro <span style='font-size:14px; color:#666; font-weight:normal'>| Live Market Intelligence</span>", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
def card(col, lbl, val, clr="#fff"): 
    col.markdown(f"<div class='metric-container'><div class='metric-label'>{lbl}</div><div class='metric-value' style='color:{clr}'>{val}</div></div>", unsafe_allow_html=True)

p_clr = "#00E096" if btc_change > 0 else "#FF4B4B"
card(c1, "BTC Fiyat", f"${btc_price:,.0f}", p_clr)
card(c2, "24s Değişim", f"%{btc_change:.2f}", p_clr)
card(c3, "Balina Sentiment", f"%{whale*100:.0f} Long", "#7C3AED")
card(c4, "Aktif Trader", f"{engine.active_trader_count} Kişi", "#F3BA2F")

st.markdown("---")

# --- 4. SİMÜLATÖR PANELİ ---
col_input, col_result = st.columns([1, 2])

with col_input:
    st.subheader("🛠️ Parametreler")
    
    analysts = sorted(list(engine.db['global'].keys()))
    coins = sorted(list(set([k[1] for k in engine.db['coin'].keys()])))
    
    sel_analyst = st.selectbox("Analist Ara", analysts, index=0)
    sel_coin = st.selectbox("Coin Ara", coins, index=0)
    sel_pos = st.selectbox("Yön", ["long", "short"], format_func=lambda x: "LONG 📈" if x=="long" else "SHORT 📉")
    
    st.divider()
    
    # --- BUG DÜZELTMESİ BURADA ---
    # Saati ve Tarihi Session State'e kaydediyoruz ki her tıklamada değişmesin.
    if 'static_now' not in st.session_state:
        st.session_state.static_now = datetime.now()

    st.caption("🗓️ Zamanlama & Market Kontrolü")
    t_col1, t_col2 = st.columns(2)
    
    # Value olarak session_state'deki SABİT zamanı veriyoruz.
    sel_date = t_col1.date_input("Tarih", st.session_state.static_now)
    sel_time = t_col2.time_input("Saat (TRT)", st.session_state.static_now.time())
    
    current_dt = datetime.combine(sel_date, sel_time)
    
    market_code, market_msg = engine.check_market_status(current_dt)
    
    if market_code == "OPEN":
        st.success(f"✅ {market_msg}")
    elif market_code == "WEEKEND":
        st.warning(f"⚠️ {market_msg}")
    else:
        st.error(f"⛔ {market_msg}")

with col_result:
    res = engine.predict_risk(
        analyst=sel_analyst, coin=sel_coin, trade_time_trt=current_dt, position=sel_pos,
        live_btc_change=btc_change, whale_top_ratio=whale, whale_global_ratio=retail
    )
    
    score = res['score']
    d = res['details']
    
    st.subheader("🧠 Yapay Zeka Kararı")
    sc_col, det_col = st.columns([1, 1])
    
    with sc_col:
        if score < 40: clr, lbl = "#FF4B4B", "RİSKLİ"
        elif score > 65: clr, lbl = "#00E096", "FIRSAT"
        else: clr, lbl = "#FFD166", "NÖTR"
        
        st.markdown(f"<div class='big-score' style='color:{clr}'>{score}</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:center; background:{clr}22; color:{clr}; padding:8px; border-radius:8px; font-weight:bold'>{lbl}</div>", unsafe_allow_html=True)
        
    with det_col:
        if d['trap_alert']: st.error(d['trap_alert'])
        else: st.success(f"✅ Zamanlama Güvenli ({sel_time.strftime('%H:%M')})")
        
        if d['trend_alert']: 
            if "TERSİ" in d['trend_alert']: st.warning(d['trend_alert'])
            else: st.success(d['trend_alert'])
            
        if d['whale_alert']:
                if "SMART" in d['whale_alert']: st.info(d['whale_alert'])
                else: st.error(d['whale_alert'])
                
        st.caption(f"İstatistik: {sel_analyst} | {sel_coin} | Başarı: {d['base_stats']['coin']}")

# --- 5. CHATBOT ---
st.divider()
st.subheader("💬 AI Asistan")

if "messages" not in st.session_state: st.session_state.messages = []
for m in st.session_state.messages: st.chat_message(m["role"]).write(m["content"])

prompt = st.chat_input("Örn: Şu an işlem açmak mantıklı mı?")

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state.messages.append({"role":"user", "content":prompt})
    
    ai_resp = f"""
    **Analiz Raporu ({sel_analyst} - {sel_coin}):**
    
    Skorun **{score}/100**.
    
    1. **Market Durumu:** {d['market_status']}
    2. **Zamanlama:** {d['trap_alert'] if d['trap_alert'] else 'Güvenli bölge.'}
    3. **Trend:** {d['trend_alert'] if d['trend_alert'] else 'Yatay seyir.'}
    
    Bu şartlar altında {lbl} görünüyor.
    """
    
    time.sleep(0.5)
    st.chat_message("assistant").write(ai_resp)
    st.session_state.messages.append({"role":"assistant", "content":ai_resp})
