import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import os
import time
from tradeguard_engine import TradeGuardAI

# --- SAYFA YAPISI ---
st.set_page_config(
    page_title="TradeGuard Pro Terminal", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS (PROFESYONEL GÖRÜNÜM) ---
st.markdown("""
    <style>
    /* Metric Kartları */
    .metric-container {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 15px;
        text-align: center;
    }
    .metric-label { font-size: 12px; color: #8b949e; text-transform: uppercase; margin-bottom: 5px; }
    .metric-value { font-size: 24px; font-weight: 700; color: #f0f6fc; }
    
    /* Skor */
    .big-score { font-size: 90px !important; font-weight: 900; line-height: 1; text-align: center; text-shadow: 0 0 20px rgba(0,0,0,0.5); }
    
    /* Live Indicator */
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .live-dot { color: #00E096; font-size: 20px; animation: pulse 2s infinite; vertical-align: middle; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. MOTORU BAŞLAT ---
@st.cache_resource
def load_engine():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ["latest_setup.csv", "data.csv"]:
        path = os.path.join(current_dir, name)
        if os.path.exists(path):
            return TradeGuardAI(path)
    return None

engine = load_engine()

if engine is None:
    st.error("⚠️ Veri Bulunamadı! GitHub'a 'latest_setup.csv' yükleyin.")
    st.stop()

# --- 2. CANLI VERİ ÇEKME FONKSİYONLARI ---

def get_market_metrics():
    """Fiyat, Fonlama Oranı ve Rasyoları Çeker"""
    try:
        # Spot Fiyat
        res_spot = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=2).json()
        price = float(res_spot['lastPrice'])
        change = float(res_spot['priceChangePercent'])
        
        # Funding Rate (Likidasyon Göstergesi)
        res_fund = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT", timeout=2).json()
        funding = float(res_fund['lastFundingRate']) * 100 # Yüzdeye çevir
        
        # Whale/Retail Ratios
        try:
            res_top = requests.get("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            whale = float(res_top[0]['longAccount'])
            res_glob = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            retail = float(res_glob[0]['longAccount'])
        except:
            whale, retail = 0.5, 0.5
            
        return price, change, funding, whale, retail
    except:
        return 0, 0, 0, 0.5, 0.5

def get_candles():
    """Grafik İçin Mum Verilerini Çeker"""
    try:
        # Son 50 mum (15 dakikalık)
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50"
        data = requests.get(url, timeout=2).json()
        # DataFrame'e çevir
        df = pd.DataFrame(data, columns=['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'CT', 'QV', 'NO', 'TBQ', 'TBV', 'Ign'])
        df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
        df['Open'] = df['Open'].astype(float)
        df['High'] = df['High'].astype(float)
        df['Low'] = df['Low'].astype(float)
        df['Close'] = df['Close'].astype(float)
        return df
    except:
        return pd.DataFrame()

# Verileri Çek
price, change, funding, whale, retail = get_market_metrics()
df_candles = get_candles()

# --- 3. ÜST BAR & METRİKLER ---
c_title, c_metrics = st.columns([1, 3])

with c_title:
    st.markdown(f"## <span class='live-dot'>●</span> TradeGuard", unsafe_allow_html=True)
    st.caption(f"v11.0 | Canlı Veri Akışı")

with c_metrics:
    m1, m2, m3, m4 = st.columns(4)
    
    def metric_card(col, label, val, color="#fff"):
        col.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">{label}</div>
                <div class="metric-value" style="color:{color}">{val}</div>
            </div>
        """, unsafe_allow_html=True)

    color_p = "#00E096" if change >= 0 else "#FF4B4B"
    metric_card(m1, "BTC Fiyat", f"${price:,.0f}", color_p)
    metric_card(m2, "24s Değişim", f"%{change:.2f}", color_p)
    
    # Funding Rate Renkleri (Likidasyon Riski)
    if funding > 0.01: f_col = "#FF4B4B" # Long Riski
    elif funding < -0.01: f_col = "#00E096" # Short Riski
    else: f_col = "#FFD166"
    metric_card(m3, "Funding (Risk)", f"%{funding:.4f}", f_col)
    
    metric_card(m4, "Balina Long", f"%{whale*100:.1f}", "#7C3AED")

# --- 4. GRAFİK VE SENTIMENT (ORTA PANEL) ---
g_chart, g_sent = st.columns([3, 1])

with g_chart:
    if not df_candles.empty:
        fig = go.Figure(data=[go.Candlestick(
            x=df_candles['Open Time'],
            open=df_candles['Open'], high=df_candles['High'],
            low=df_candles['Low'], close=df_candles['Close'],
            increasing_line_color='#00E096', decreasing_line_color='#FF4B4B'
        )])
        fig.update_layout(
            height=350, 
            margin=dict(l=0, r=0, t=30, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="#8b949e"),
            title=dict(text="BTC/USDT - 15 Dakikalık Canlı Trend", x=0, font=dict(size=12, color="#888")),
            xaxis_rangeslider_visible=False
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Grafik verisi yüklenemedi.")

with g_sent:
    st.markdown("##### 🐋 Sentiment Savaşı")
    st.caption("Balina vs. Küçük Yatırımcı")
    
    # Balina Barı
    st.markdown(f"**Balinalar (Top)**: %{whale*100:.1f} Long")
    st.progress(whale)
    
    st.markdown("---")
    
    # Retail Barı
    st.markdown(f"**Retail (Global)**: %{retail*100:.1f} Long")
    st.progress(retail)
    
    # Yorum
    if whale > 0.6:
        st.success("✅ Balinalar Topluyor")
    elif whale < 0.4:
        st.error("🔻 Balinalar Satıyor")
    else:
        st.info("⚖️ Piyasa Kararsız")

# --- 5. SİMÜLATÖR (ALT PANEL) ---
st.divider()

# Yan yana girişler (Search destekli)
col_input1, col_input2, col_input3, col_input4 = st.columns(4)

analysts = sorted(list(engine.db['global'].keys()))
coins = sorted(list(set([k[1] for k in engine.db['coin'].keys()])))

sel_analyst = col_input1.selectbox("Analist Ara", analysts, index=0)
sel_coin = col_input2.selectbox("Coin Ara", coins, index=0)
sel_pos = col_input3.selectbox("Yön", ["long", "short"])

# Tarih/Saat Birleştirme
now = datetime.now()
sel_datetime = col_input4.text_input("Tarih/Saat (TRT)", value=now.strftime("%Y-%m-%d %H:%M"))

# Hesapla
try:
    current_dt = datetime.strptime(sel_datetime, "%Y-%m-%d %H:%M")
except:
    current_dt = now # Hata olursa şimdiki zaman

result = engine.predict_risk(
    analyst=sel_analyst,
    coin=sel_coin,
    trade_time_trt=current_dt,
    position=sel_pos,
    live_btc_change=change,
    whale_top_ratio=whale,
    whale_global_ratio=retail
)

score = result['score']
details = result['details']

# --- 6. SONUÇ EKRANI ---
col_res1, col_res2 = st.columns([1, 2])

with col_res1:
    # Renk Ayarı
    if score < 40: clr, lbl = "#FF4B4B", "RİSKLİ"
    elif score > 65: clr, lbl = "#00E096", "GÜVENLİ"
    else: clr, lbl = "#FFD166", "NÖTR"
    
    st.markdown(f"<div class='big-score' style='color:{clr}'>{score}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center; color:{clr}; font-weight:bold; letter-spacing:2px'>{lbl}</div>", unsafe_allow_html=True)

with col_res2:
    st.subheader("AI Karar Detayları")
    
    # Grid şeklinde detaylar
    d1, d2 = st.columns(2)
    
    # Uyarılar
    with d1:
        if details['trap_alert']: st.error(details['trap_alert'])
        else: st.success("✅ Zamanlama Güvenli (Kill-Zone Dışı)")
        
        if details['trend_alert']:
            if "TERSİ" in details['trend_alert']: st.warning(details['trend_alert'])
            else: st.success(details['trend_alert'])

    with d2:
        if details['whale_alert']:
            if "SMART" in details['whale_alert']: st.info(details['whale_alert'])
            else: st.error(details['whale_alert'])
        
        st.markdown(f"**Coin İstatistiği:** {details['base_stats']['coin']}")
