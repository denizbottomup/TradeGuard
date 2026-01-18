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
    page_title="TradeGuard AI Chat", 
    page_icon="🤖", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS ---
st.markdown("""
    <style>
    .metric-container { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px; text-align: center; }
    .metric-value { font-size: 20px; font-weight: 700; color: #f0f6fc; }
    .metric-label { font-size: 11px; color: #8b949e; text-transform: uppercase; }
    .chat-user { background-color: #2b3137; padding: 10px; border-radius: 10px; margin-bottom: 10px; text-align: right; }
    .chat-ai { background-color: #0d1117; padding: 15px; border-radius: 10px; border-left: 4px solid #00E096; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- MOTORU YÜKLE ---
@st.cache_resource
def load_engine():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ["latest_setup.csv", "data.csv"]:
        path = os.path.join(current_dir, name)
        if os.path.exists(path): return TradeGuardAI(path)
    return None

engine = load_engine()
if not engine: st.error("CSV Dosyası Yok! Lütfen GitHub'a 'latest_setup.csv' yükleyin."); st.stop()

# --- NLP PARSER ---
def parse_user_prompt(prompt, available_coins):
    prompt = prompt.lower()
    position = "long"
    if "short" in prompt or "düşer" in prompt or "satış" in prompt: position = "short"
    
    selected_coin = "BTC/USDT"
    coin_map = {"btc": "BTC/USDT", "bitcoin": "BTC/USDT", "eth": "ETH/USDT", "ethereum": "ETH/USDT", "sol": "SOL/USDT"}
    
    for k, v in coin_map.items():
        if k in prompt: selected_coin = v; break
    
    for c in available_coins:
        if c.split("/")[0].lower() in prompt: selected_coin = c; break

    return selected_coin, position

# --- CANLI VERİ (ABD SUNUCUSU UYUMLU) ---
def get_live_metrics():
    """
    Streamlit Cloud (US) uyumlu veri çekme fonksiyonu.
    Binance Global US IP'lerini engellediği için alternatif endpointler dener.
    """
    price, change, whale = 0, 0, 0.5
    debug_log = []

    # 1. FİYAT VE TREND (Binance US Kullan - ABD Dostu)
    try:
        # Not: Binance US'de parite BTCUSD olarak geçer (USDT değil)
        url = "https://api.binance.us/api/v3/ticker/24hr?symbol=BTCUSDT" 
        res = requests.get(url, timeout=3)
        
        if res.status_code == 200:
            data = res.json()
            price = float(data['lastPrice'])
            change = float(data['priceChangePercent'])
        else:
            debug_log.append(f"Spot API Hatası: {res.status_code}")
            # Yedek: CoinGecko (Çok daha güvenli ama yavaş)
            url_cg = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
            res_cg = requests.get(url_cg, timeout=3).json()
            price = res_cg['bitcoin']['usd']
            change = res_cg['bitcoin']['usd_24h_change']

    except Exception as e:
        debug_log.append(f"Fiyat Çekilemedi: {str(e)}")

    # 2. BALİNA VERİSİ (Binance Futures)
    # ABD sunucuları fapi.binance.com'a erişemez.
    # Bu yüzden veri gelmezse Nötr (0.5) dönüp kullanıcıyı yanıltmayız.
    try:
        url_fut = "https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol=BTCUSDT&period=5m&limit=1"
        res_fut = requests.get(url_fut, timeout=2)
        if res_fut.status_code == 200:
            whale = float(res_fut.json()[0]['longAccount'])
        else:
            debug_log.append("Futures API Bloklandı (US IP)")
            whale = 0.5 # Nötr Varsay
    except Exception as e:
        debug_log.append(f"Whale Data Hatası: {str(e)}")
        whale = 0.5

    return price, change, whale, debug_log

# Verileri Çek
btc_price, btc_change, whale_ratio, logs = get_live_metrics()

# --- UI BAŞLANGIÇ ---
st.title("🤖 BottomUP TradeGuard AI")

# DEBUG PANELİ (Eğer veri 0 geliyorsa burayı açıp hatayı görebilirsiniz)
with st.expander("🔌 Bağlantı Durumu & Debug Logları"):
    if btc_price > 0:
        st.success(f"✅ Fiyat Verisi Başarıyla Alındı: ${btc_price}")
    else:
        st.error("❌ Fiyat Verisi Alınamadı!")
    
    if logs:
        st.write("Hata Günlüğü:", logs)
    else:
        st.write("Sistem sorunsuz çalışıyor.")

# Üst Bilgi Barı
c1, c2, c3, c4 = st.columns(4)
def mini_card(col, lbl, val, clr="#fff"):
    col.markdown(f"<div class='metric-container'><div class='metric-label'>{lbl}</div><div class='metric-value' style='color:{clr}'>{val}</div></div>", unsafe_allow_html=True)

p_clr = "#00E096" if btc_change > 0 else "#FF4B4B"
mini_card(c1, "BTC Fiyat", f"${btc_price:,.0f}", p_clr)
mini_card(c2, "Trend (24s)", f"%{btc_change:.2f}", p_clr)
mini_card(c3, "Balina Sentiment", f"%{whale_ratio*100:.1f} Long", "#7C3AED")
mini_card(c4, "AI Modeli", "v11.0 Active", "#F3BA2F")

st.markdown("---")

# --- SIDEBAR ---
st.sidebar.header("👤 Trader Profili")
analysts = sorted(list(engine.db['global'].keys()))
active_analyst = st.sidebar.selectbox("Sen Kimsin?", analysts)
st.sidebar.info(f"Hoşgeldin {active_analyst}, senin geçmiş verilerini yükledim.")

# --- CHAT ARAYÜZÜ ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- KULLANICI GİRİŞİ ---
prompt = st.chat_input("AI'ya sor: Örn: 'Şu an BTC Long açsam başarılı olur muyum?'")

if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner(f'{active_analyst} verileri analiz ediliyor...'):
        time.sleep(0.5)
        
        # NLP & HESAPLAMA
        # Coin listesini temizle
        clean_coins = list(set([k[1] for k in engine.db['coin'].keys()]))
        target_coin, target_pos = parse_user_prompt(prompt, clean_coins)
        
        res = engine.predict_risk(
            analyst=active_analyst,
            coin=target_coin,
            trade_time_trt=datetime.now(),
            position=target_pos,
            live_btc_change=btc_change,
            whale_top_ratio=whale_ratio
        )
        
        score = res['score']
        dets = res['details']

        # CEVAP OLUŞTURMA
        if score > 65:
            intro = f"🚀 **Evet {active_analyst}, şartlar {target_pos.upper()} işlemi için harika!**"
            color = "green"
        elif score < 40:
            intro = f"⛔ **Hayır, şu an beklemeni öneririm {active_analyst}.**"
            color = "red"
        else:
            intro = f"⚠️ **Durum nötr.** İşlem açabilirsin ama riskli."
            color = "orange"
            
        analysis_text = f"""
        Bu işlem için **Başarı Skorun: :{color}[{score}/100]**.
        
        **Neden bu puan?**
        1. **Geçmiş İstatistik:** {target_coin} paritesindeki başarın **{dets['base_stats']['coin']}**.
        2. **Zamanlama:** {dets['trap_alert'] if dets['trap_alert'] else "Şu an güvenli bir saat dilimi."}
        3. **Piyasa:** {dets['trend_alert'] if dets['trend_alert'] else "Trend yatay seyrediyor."}
        """

    with st.chat_message("assistant"):
        st.markdown(intro)
        st.markdown(analysis_text)
    
    st.session_state.messages.append({"role": "assistant", "content": intro + "\n" + analysis_text})
