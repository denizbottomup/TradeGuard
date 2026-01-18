import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class TradeGuardAI:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.db = {
            'global': {},
            'session': {},
            'coin': {},
            'day': {}
        }
        self.market_data = {'loaded': False}
        self.load_and_train()

    def load_and_train(self):
        """CSV dosyasını okur, filtreler ve Bilgi Bankasını oluşturur."""
        # print("📂 Veri Seti Yükleniyor...") # Logları kapattık
        try:
            df = pd.read_csv(self.csv_file)
        except FileNotFoundError:
            df = pd.DataFrame(columns=['analysts', 'coin_name', 'Status', 'Close Date'])
            return

        # 1. TARİH FORMATLAMA
        df['Close Date'] = pd.to_datetime(df['Close Date'], format='%B %d, %Y, %I:%M %p', errors='coerce')
        df = df.dropna(subset=['Close Date']) # Tarihi bozuk olanları sil
        
        # 2. KRİTİK FİLTRE: SON 6 AY (180 GÜN)
        # Sadece piyasanın güncel nabzını tutanları istiyoruz.
        cutoff_date = datetime.now() - timedelta(days=180)
        original_count = len(df)
        df = df[df['Close Date'] >= cutoff_date]
        filtered_count = len(df)
        
        # Eğer filtre çok sıkıysa ve veri kalmazsa uyar (Konsolda görünür)
        if filtered_count == 0:
            print("UYARI: Son 6 ayda işlem bulunamadı! Filtre devre dışı bırakılıyor.")
            df = pd.read_csv(self.csv_file) # Geri yükle
            df['Close Date'] = pd.to_datetime(df['Close Date'], format='%B %d, %Y, %I:%M %p', errors='coerce')
        
        self.active_trader_count = df['analysts'].nunique()

        # 3. VERİ İŞLEME
        df['Status_Bool'] = (df['Status'] == 'success').astype(int)
        df['NY_Date'] = df['Close Date'] - timedelta(hours=8)
        df['Session'] = df['NY_Date'].apply(self._get_session)
        df['Day'] = df['Close Date'].dt.day_name()

        # 4. İSTATİSTİKLERİ OLUŞTUR
        self.db['global'] = df.groupby('analysts')['Status_Bool'].mean().to_dict()
        self.db['session'] = df.groupby(['analysts', 'Session'])['Status_Bool'].mean().to_dict()
        
        # Coin filtresi: En az 1 işlem yeterli (Search box olduğu için 3 şartını kaldırdım)
        coin_stats = df.groupby(['analysts', 'coin_name'])['Status_Bool'].agg(['mean', 'count'])
        self.db['coin'] = coin_stats['mean'].to_dict()
        
        self.db['day'] = df.groupby(['analysts', 'Day'])['Status_Bool'].mean().to_dict()

    def _get_session(self, dt):
        h = dt.hour
        m = dt.minute
        if (h > 9 or (h == 9 and m >= 30)) and h < 16: return 'New York'
        if h >= 2 and h < 9: return 'London'
        if (h == 9 and m < 30): return 'London'
        if h >= 18 or h < 2: return 'Asia'
        return 'Pacific'

    def predict_risk(self, analyst, coin, trade_time_trt, position='long', 
                     live_btc_change=0.0, whale_top_ratio=0.5, whale_global_ratio=0.5):
        
        if isinstance(trade_time_trt, str): dt = pd.to_datetime(trade_time_trt)
        else: dt = trade_time_trt
            
        h, m = dt.hour, dt.minute
        
        # A. KILL ZONES
        trap_score = 0; trap_msg = None
        if (h == 16 and m >= 30) or (h == 17 and m < 30):
            trap_score = -25; trap_msg = "🗽 NY TRAP: Likidasyon Tuzağı Saati!"
        elif h == 10:
            trap_score = -15; trap_msg = "💂 LONDON TRAP: Fake Hareket Riski!"
        elif h == 3:
            trap_score = -10; trap_msg = "🌏 DAILY RESET: Yüksek Spread Riski!"

        # B. GEÇMİŞ İSTATİSTİK
        ny_date = dt - timedelta(hours=8)
        session = self._get_session(ny_date)
        day_name = dt.strftime('%A')

        g_wr = self.db['global'].get(analyst, 0.50)
        s_wr = self.db['session'].get((analyst, session), g_wr)
        c_wr = self.db['coin'].get((analyst, coin), g_wr)
        d_wr = self.db['day'].get((analyst, day_name), g_wr)

        base_score = (c_wr * 0.40) + (s_wr * 0.30) + (g_wr * 0.20) + (d_wr * 0.10)
        final_score = base_score * 100

        # C. TREND (LIVE)
        trend_msg = None
        is_bull = live_btc_change > 1.5
        is_bear = live_btc_change < -1.5

        if position == 'long':
            if is_bear: final_score -= 15; trend_msg = f"📉 TREND TERSİ: BTC Düşüyor (%{live_btc_change})."
            elif is_bull: final_score += 10; trend_msg = f"🚀 TREND DOSTU: BTC Yükseliyor (%{live_btc_change})."
        else:
            if is_bull: final_score -= 15; trend_msg = f"📉 TREND TERSİ: BTC Yükseliyor (%{live_btc_change})."
            elif is_bear: final_score += 10; trend_msg = f"🚀 TREND DOSTU: BTC Düşüyor (%{live_btc_change})."

        # D. WHALE (LIVE)
        whale_msg = None
        if position == 'long':
            if whale_top_ratio > 0.60: final_score += 20; whale_msg = "🐋 SMART MONEY: Balinalar Long pozisyonda."
            elif whale_global_ratio > 0.70 and whale_top_ratio < 0.50: final_score -= 25; whale_msg = "🛑 RETAIL FOMO: Küçük yatırımcı terste."
        else:
            if whale_top_ratio < 0.40: final_score += 20; whale_msg = "🐋 SMART MONEY: Balinalar Short pozisyonda."
            elif whale_global_ratio < 0.30 and whale_top_ratio > 0.50: final_score -= 25; whale_msg = "🛑 RETAIL PANIC: Küçük yatırımcı panikte."

        final_score += trap_score
        final_score = max(0, min(100, round(final_score)))
        
        return {
            "score": final_score,
            "analyst": analyst,
            "coin": coin,
            "details": {
                "base_stats": {"coin": f"%{int(c_wr*100)}", "session": f"%{int(s_wr*100)}"},
                "trap_alert": trap_msg, "trend_alert": trend_msg, "whale_alert": whale_msg
            }
        }
