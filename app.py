import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import os
from tradeguard_engine import TradeGuardAI

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="TradeGuard AI v11", 
    page_icon="🛡️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS STİL (GÖRSELLEŞTİRME) ---
st.markdown("""
    <style>
    .big-score { font-size: 70px !important; font-weight: 900; line-height: 1; }
    .score-label { font-size: 14px; letter-spacing: 2px; color: #888; margin-bottom: 5px; }
    .badge { padding: 8px 16px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block; margin-top: 10px; }
    .stMetric { background-color: #0E1117; padding: 10px; border-radius: 10px; border: 1px solid #262730; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. DOSYA YOLU VE MOTOR BAŞLATMA ---
@st.cache_resource
def load_engine():
    # Dosya ismini standartlaştırıyoruz: "latest_setup.csv"
    # Bu kod, app.py ile aynı klasördeki dosyayı arar.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Olası dosya isimlerini kontrol et
    possible_names = ["latest_setup.csv", "data.csv"]
    csv_path = None
    
    for name in possible_names:
        temp_path = os.path.join(current_dir, name)
        if os.path.exists(temp_path):
            csv_path = temp_path
            break
            
    if csv_path:
        return TradeGuardAI(csv_path)
    return None

# Motoru Yükle
engine = load_engine()

# --- HATA YÖNETİMİ (DOSYA YOKSA) ---
if engine is None:
    st.error("⚠️ CSV Dosyası Bulunamadı!")
    st.info("Lütfen GitHub'a yüklediğiniz CSV dosyasının adını **'latest_setup.csv'** olarak değiştirin.")
    
    # Geçici Yükleme Ekranı (Debug için)
    uploaded_file = st.file_uploader("Veya buradan manuel yükleyin:", type="csv")
    if uploaded_file:
        with open("latest_setup.csv", "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.rerun()
    st.stop()
else:
    st.sidebar.success(f"✅ Sistem Aktif (v11.0)")

# --- 2. CANLI VERİ (BINANCE) ---
def get_live_data():
    try:
        # Spot Price
        res_spot = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5).json()
        price = float(res_spot['lastPrice'])
        change = float(res_spot['priceChangePercent'])
        
        # Futures Whale Data (Public API)
        # Not: Public API bazen veri vermeyebilir, bu durumda nötr (0.5) döneriz.
        try:
            res_top = requests.get("https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=5).json()
            whale_ratio = float(res_top[0]['longAccount'])
            
            res_glob = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1", timeout=5).json()
            retail_ratio = float(res_glob[0]['longAccount'])
        except:
            whale_ratio, retail_ratio = 0.5, 0.5 # Veri yoksa Nötr
            
        return price, change, whale_ratio, retail_ratio
    except:
        return 0, 0, 0.5, 0.5

btc_price, btc_change, whale_long, retail_long = get_live_data()

# --- 3. SIDEBAR (KULLANICI GİRİŞLERİ) ---
st.sidebar.header("⚡ Simülatör")

analysts = sorted(list(engine.db['global'].keys()))
# Coin listesini temizle
coins = sorted(list(set([k[1] for k in engine.db['coin'].keys()])))

sel_analyst = st.sidebar.selectbox("Analist Seç", analysts)
sel_coin = st.sidebar.selectbox("Coin Paritesi", coins)
sel_pos = st.sidebar.selectbox("İşlem Yönü", ["long", "short"], format_func=lambda x: "LONG (Yükseliş)" if x=="long" else "SHORT (Düşüş)")
sel_time = st.sidebar.time_input("İşlem Saati (TRT)", datetime.now().time())

# --- 4. ANA EKRAN ---
st.title("🛡️ BottomUP TradeGuard")
st.markdown(f"**Live Engine Status:** Connected to Binance | **Model:** AI-Driven v11.0")

# Metrik Kartları
c1, c2, c3, c4 = st.columns(4)
c1.metric("BTC Fiyat", f"${btc_price:,.0f}", f"{btc_change:.2f}%")
c2.metric("Balina (Long)", f"%{whale_long*100:.1f}", delta_color="off")
c3.metric("Retail (Long)", f"%{retail_long*100:.1f}", delta_color="off")
c4.metric("Model Verisi", f"{len(engine.db['global'])} Analist")

# --- 5. RİSK HESAPLAMA ---
current_dt = datetime.combine(datetime.today(), sel_time)

# Engine'i çağır
result = engine.predict_risk(
    analyst=sel_analyst,
    coin=sel_coin,
    trade_time_trt=current_dt,
    position=sel_pos,
    live_btc_change=btc_change,
    whale_top_ratio=whale_long,
    whale_global_ratio=retail_long
)

score = result['score']
details = result['details']

# --- 6. SONUÇ GÖRSELLEŞTİRME ---
st.markdown("---")

col_score, col_details = st.columns([1, 2])

with col_score:
    st.markdown("<div style='text-align:center' class='score-label'>BAŞARI OLASILIĞI</div>", unsafe_allow_html=True)
    
    # Renk Kodları
    if score < 40:
        color = "#FF4B4B" # Kırmızı
        bg_color = "rgba(255, 75, 75, 0.1)"
        label = "YÜKSEK RİSK"
    elif score > 65:
        color = "#00E096" # Yeşil
        bg_color = "rgba(0, 224, 150, 0.1)"
        label = "GÜÇLÜ FIRSAT"
    else:
        color = "#FFD166" # Sarı
        bg_color = "rgba(255, 209, 102, 0.1)"
        label = "NÖTR / İZLE"

    st.markdown(f"<div style='text-align:center; color:{color}' class='big-score'>{score}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='text-align:center'><span class='badge' style='background:{bg_color}; color:{color}'>{label}</span></div>", unsafe_allow_html=True)

with col_details:
    st.subheader("🧠 Yapay Zeka Analiz Raporu")
    
    # Uyarılar
    if details['trap_alert']:
        st.error(f"🕰️ {details['trap_alert']}")
    
    if details['trend_alert']:
        if "TERSİ" in details['trend_alert']: st.warning(f"📉 {details['trend_alert']}")
        else: st.success(f"🚀 {details['trend_alert']}")
        
    if details['whale_alert']:
        if "SMART" in details['whale_alert']: st.info(f"🐋 {details['whale_alert']}")
        else: st.error(f"⚠️ {details['whale_alert']}")
        
    st.markdown("---")
    # İstatistik Detayı
    s1, s2 = st.columns(2)
    s1.info(f"**Coin Uyumu:** {details['base_stats']['coin']}")
    s2.info(f"**Seans Uyumu:** {details['base_stats']['session']}")

# --- 7. GRAFİK ---
st.markdown("---")
st.caption("Model Karar Ağırlıkları (Backtest Optimize)")

labels = ['Coin Uyumu (%40)', 'Zamanlama (%30)', 'Analist (%20)', 'Gün (%10)', 'Canlı Sinyaller (Dynamic)']
values = [40, 30, 20, 10, 25] # Dinamik sinyaller ekstra etki eder

fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.5, marker_colors=['#2DE1FC', '#FF4B4B', '#F3BA2F', '#A0A0A0', '#7C3AED'])])
fig.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', font_color='#888')
st.plotly_chart(fig, use_container_width=True)
