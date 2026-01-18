import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import os
from tradeguard_engine import TradeGuardAI

# --- SAYFA YAPISI ---
st.set_page_config(
    page_title="TradeGuard Live", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS (CANLI GÖRÜNÜM & ANİMASYON) ---
st.markdown("""
    <style>
    /* Canlı İndikatörü */
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .live-indicator { color: #00E096; font-weight: bold; animation: blink 2s infinite; display: inline-block; margin-right: 10px; }
    
    /* Skor Kartları */
    .big-score { font-size: 80px !important; font-weight: 900; line-height: 1; text-align: center; }
    .metric-card { background: #0E1117; padding: 15px; border-radius: 10px; border: 1px solid #333; text-align: center; }
    .metric-val { font-size: 24px; font-weight: bold; color: #fff; }
    .metric-label { font-size: 12px; color: #888; text-transform: uppercase; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. MOTORU BAŞLAT ---
@st.cache_resource
def load_engine():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Olası isimleri tara
    for name in ["latest_setup.csv", "data.csv"]:
        path = os.path.join(current_dir, name)
        if os.path.exists(path):
            return TradeGuardAI(path)
    return None

engine = load_engine()

if engine is None:
    st.error("⚠️ Veri Bulunamadı! GitHub'a 'latest_setup.csv' yükleyin.")
    st.stop()

# --- 2. CANLI VERİ ÇEK (TÜM DATALAR) ---
def get_live_metrics():
    try:
        # Spot Fiyat
        res_spot = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=2).json()
        price = float(res_spot['lastPrice'])
        change = float(res_spot['priceChangePercent'])
        
        # Vadeli (Whale/Retail)
        try:
            res_top = requests.get("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            whale = float(res_top[0]['longAccount'])
            
            res_glob = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=2).json()
            retail = float(res_glob[0]['longAccount'])
        except:
            whale, retail = 0.5, 0.5 # Veri gelmezse nötr
            
        return price, change, whale, retail
    except:
        return 0, 0, 0.5, 0.5

# Verileri çek
btc_price, btc_change, whale_ratio, retail_ratio = get_live_metrics()

# --- 3. BAŞLIK & CANLI DATA PANELI ---
st.markdown(f"""
    ## <span class='live-indicator'>●</span> BottomUP TradeGuard <span style='font-size:14px; color:#666; font-weight:normal'>| Canlı Piyasa Bağlantısı Aktif</span>
""", unsafe_allow_html=True)

# 4'lü Canlı Veri Paneli
col1, col2, col3, col4 = st.columns(4)

def metric_box(col, label, value, color="#fff"):
    col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-val" style="color:{color}">{value}</div>
        </div>
    """, unsafe_allow_html=True)

# Renk Ayarları
p_color = "#00E096" if btc_change > 0 else "#FF4B4B"
metric_box(col1, "BTC Fiyat", f"${btc_price:,.0f}", p_color)
metric_box(col2, "24s Değişim", f"%{btc_change:.2f}", p_color)
metric_box(col3, "Balina (Top Trader)", f"%{whale_ratio*100:.1f} Long", "#7C3AED") # Mor
metric_box(col4, "Retail (Global)", f"%{retail_ratio*100:.1f} Long", "#F3BA2F") # Sarı

st.markdown("---")

# --- 4. SİMÜLATÖR (SIDEBAR) ---
st.sidebar.header("🔍 Analiz Filtreleri")
st.sidebar.info(f"Son 6 ayda aktif olan **{engine.active_trader_count}** trader listeleniyor.")

# Arama Özellikli Kutular (Selectbox native olarak aramayı destekler)
analysts = sorted(list(engine.db['global'].keys()))
# Coinleri temizle ve sırala
coins = sorted(list(set([k[1] for k in engine.db['coin'].keys()])))

sel_analyst = st.sidebar.selectbox("Analist Ara/Seç", analysts, index=0, placeholder="Yazmaya başlayın...")
sel_coin = st.sidebar.selectbox("Coin Ara/Seç", coins, index=0, placeholder="Yazmaya başlayın...")
sel_pos = st.sidebar.selectbox("Yön", ["long", "short"], format_func=lambda x: "LONG 📈" if x=="long" else "SHORT 📉")

st.sidebar.markdown("---")
sel_date = st.sidebar.date_input("Tarih", datetime.now())
sel_time = st.sidebar.time_input("Saat", datetime.now().time())
current_dt = datetime.combine(sel_date, sel_time)

# --- 5. HESAPLAMA MOTORU ---
result = engine.predict_risk(
    analyst=sel_analyst,
    coin=sel_coin,
    trade_time_trt=current_dt,
    position=sel_pos,
    live_btc_change=btc_change,
    whale_top_ratio=whale_ratio,
    whale_global_ratio=retail_ratio
)

score = result['score']
details = result['details']

# --- 6. SONUÇ EKRANI ---
c_score, c_detay = st.columns([1, 2])

with c_score:
    st.markdown("<div style='text-align:center; color:#666; letter-spacing:1px; margin-bottom:10px'>BAŞARI OLASILIĞI</div>", unsafe_allow_html=True)
    
    if score < 40:
        clr = "#FF4B4B"; lbl = "YÜKSEK RİSK ⛔"
    elif score > 65:
        clr = "#00E096"; lbl = "GÜÇLÜ FIRSAT 🚀"
    else:
        clr = "#FFD166"; lbl = "NÖTR / İZLE ⚠️"
        
    st.markdown(f"<div class='big-score' style='color:{clr}'>{score}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center; background:{clr}22; color:{clr}; padding:8px; border-radius:8px; font-weight:bold; margin-top:10px'>{lbl}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center; font-size:11px; color:#555; margin-top:20px'>Son Güncelleme: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

with c_detay:
    st.subheader("📋 Yapay Zeka Raporu")
    
    # Uyarılar
    if details['trap_alert']: st.error(details['trap_alert'])
    else: st.success("✅ Zamanlama Güvenli (Likidasyon Bölgesi Dışı)")

    if details['trend_alert']:
        if "TERSİ" in details['trend_alert']: st.warning(details['trend_alert'])
        else: st.success(details['trend_alert'])

    if details['whale_alert']:
        if "SMART" in details['whale_alert']: st.info(details['whale_alert'])
        else: st.error(details['whale_alert'])

    st.markdown("---")
    # İstatistikler
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Geçmiş Coin Başarısı", details['base_stats']['coin'])
    col_s2.metric("Geçmiş Seans Başarısı", details['base_stats']['session'])

# --- 7. GRAFİK ---
st.markdown("---")
fig = go.Figure(data=[go.Pie(
    labels=['Coin Uyumu (%40)', 'Zamanlama (%30)', 'Analist (%20)', 'Gün (%10)', 'Canlı Sinyaller'],
    values=[40, 30, 20, 10, 25],
    hole=.6,
    marker_colors=['#2DE1FC', '#FF4B4B', '#F3BA2F', '#A0A0A0', '#7C3AED']
)])
fig.update_layout(height=200, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', font_color='#888', showlegend=False)
st.plotly_chart(fig, use_container_width=True)
