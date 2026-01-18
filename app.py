import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
from tradeguard_engine import TradeGuardAI
import plotly.graph_objects as go

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="TradeGuard AI v11", page_icon="🛡️", layout="wide")

# --- STİL (CSS) ---
st.markdown("""
    <style>
    .big-font { font-size:60px !important; font-weight: 800; color: #F3BA2F; }
    .risk-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. VERİ MOTORUNU BAŞLAT ---
@st.cache_resource
def load_engine():
    # CSV dosyasının github'da veya aynı klasörde olması lazım
    return TradeGuardAI("latest_setup.csv") 

try:
    engine = load_engine()
    st.sidebar.success("✅ AI Motoru Hazır (v11.0)")
except:
    st.error("CSV Dosyası Bulunamadı! Lütfen 'latest_setup.csv' dosyasını yükleyin.")
    uploaded_file = st.sidebar.file_uploader("CSV Yükle", type="csv")
    if uploaded_file:
        with open("latest_setup.csv", "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.experimental_rerun()
    st.stop()

# --- 2. CANLI VERİ ÇEK (BINANCE) ---
def get_live_data():
    try:
        # Spot Price
        res_spot = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT").json()
        price = float(res_spot['lastPrice'])
        change = float(res_spot['priceChangePercent'])
        
        # Futures Whale Data (Public API)
        res_top = requests.get("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1").json()
        whale_ratio = float(res_top[0]['longAccount']) if res_top else 0.5
        
        res_glob = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1").json()
        retail_ratio = float(res_glob[0]['longAccount']) if res_glob else 0.5
        
        return price, change, whale_ratio, retail_ratio
    except:
        return 0, 0, 0.5, 0.5

btc_price, btc_change, whale_long, retail_long = get_live_data()

# --- 3. ARAYÜZ (SIDEBAR) ---
st.sidebar.header("⚡ Simülatör Ayarları")

# Listeleri Doldur
analysts = sorted(list(engine.db['global'].keys()))
# Coin listesini güvenli çek
coins = []
if hasattr(engine.db['coin'], 'keys'):
    # Tuple keys (Analyst, Coin) -> Sadece Coinleri al
    coins = sorted(list(set([k[1] for k in engine.db['coin'].keys()])))

sel_analyst = st.sidebar.selectbox("Analist", analysts)
sel_coin = st.sidebar.selectbox("Coin", coins)
sel_pos = st.sidebar.selectbox("Yön", ["long", "short"])
sel_time = st.sidebar.time_input("İşlem Saati (TRT)", datetime.now().time())

# --- 4. ANA EKRAN ---
st.title("🛡️ BottomUP TradeGuard AI")
st.caption("Live Whale Data & Historical Machine Learning Engine")

# Üst Bilgi Kartları
col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC Fiyat", f"${btc_price:,.0f}", f"{btc_change:.2f}%")
col2.metric("Balina (Long)", f"%{whale_long*100:.1f}", delta_color="off")
col3.metric("Retail (Long)", f"%{retail_long*100:.1f}", delta_color="off")

# Hesaplama
current_dt = datetime.combine(datetime.today(), sel_time)
res = engine.predict_risk(
    analyst=sel_analyst,
    coin=sel_coin,
    trade_time_trt=current_dt,
    position=sel_pos,
    live_btc_change=btc_change,
    whale_top_ratio=whale_long,
    whale_global_ratio=retail_long
)

score = res['score']
details = res['details']

# Skor Gösterimi
st.markdown("---")
c_score, c_detail = st.columns([1, 2])

with c_score:
    st.markdown("<div style='text-align:center'>AI SKORU</div>", unsafe_allow_html=True)
    color = "#FF4B4B" if score < 40 else ("#00E096" if score > 65 else "#FFD166")
    st.markdown(f"<div class='big-font' style='text-align:center; color:{color}'>{score}</div>", unsafe_allow_html=True)
    
    lbl = "YÜKSEK RİSK" if score < 40 else ("GÜÇLÜ FIRSAT" if score > 65 else "NÖTR")
    st.markdown(f"<div style='text-align:center; background:{color}33; color:{color}; padding:5px; border-radius:5px;'><b>{lbl}</b></div>", unsafe_allow_html=True)

with c_detail:
    st.subheader("📝 AI Karar Detayları")
    
    if details['trap_alert']:
        st.error(f"🛑 {details['trap_alert']}")
    
    if details['trend_alert']:
        if "TERSİ" in details['trend_alert']: st.warning(details['trend_alert'])
        else: st.success(details['trend_alert'])
        
    if details['whale_alert']:
        if "SMART" in details['whale_alert']: st.info(details['whale_alert'])
        else: st.error(details['whale_alert'])
        
    st.write(f"**Geçmiş İstatistik:** Coin Başarısı {details['base_stats']['coin']} | Seans Başarısı {details['base_stats']['session']}")

# Grafik
st.markdown("---")
st.subheader("📊 Model Ağırlıkları (v11)")
labels = ['Coin Uyumu', 'Saat/Zaman', 'Analist', 'Gün', 'Trend/Balina (Live)']
values = [40, 30, 20, 10, 30] # Dinamik kısımlar ekstra puan ekler
fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.4)])
fig.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
st.plotly_chart(fig, use_container_width=True)