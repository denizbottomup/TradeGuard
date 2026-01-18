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
        """CSV dosyasını okur ve Bilgi Bankasını (Knowledge Base) oluşturur."""
        print("📂 Veri Seti Yükleniyor...")
        try:
            df = pd.read_csv(self.csv_file)
        except FileNotFoundError:
            print("❌ Hata: CSV dosyası bulunamadı! (Lütfen 'latest_setup.csv' dosyasını yükleyin)")
            # Hata durumunda boş dataframe oluştur ki sistem çökmesin
            df = pd.DataFrame(columns=['analysts', 'coin_name', 'Status', 'Close Date'])
            return

        # Tarih Formatlama
        # Hata yönetimi: Tarih formatı bozuksa o satırları atla
        df['Close Date'] = pd.to_datetime(df['Close Date'], format='%B %d, %Y, %I:%M %p', errors='coerce')
        df = df.dropna(subset=['Close Date']) # Tarihi bozuk olanları sil
        
        # Başarı Durumu (Success/Fail -> 1/0)
        df['Status_Bool'] = (df['Status'] == 'success').astype(int)

        # Feature Engineering (Türetilmiş Veriler)
        # TRT -> NY Saati Dönüşümü (-8 Saat varsayımı)
        df['NY_Date'] = df['Close Date'] - timedelta(hours=8)
        df['Session'] = df['NY_Date'].apply(self._get_session)
        df['Day'] = df['Close Date'].dt.day_name()

        # İstatistikleri Hesapla (Knowledge Base)
        # 1. Global (Analist Başarısı)
        self.db['global'] = df.groupby('analysts')['Status_Bool'].mean().to_dict()
        
        # 2. Session (Analist + Seans)
        self.db['session'] = df.groupby(['analysts', 'Session'])['Status_Bool'].mean().to_dict()
        
        # 3. Coin (Analist + Coin) - En az 3 işlem şartı
        # Az işlem yapılan coinlerde istatistik yanıltıcı olabilir
        coin_stats = df.groupby(['analysts', 'coin_name'])['Status_Bool'].agg(['mean', 'count'])
        valid_coins = coin_stats[coin_stats['count'] >= 3]['mean']
        self.db['coin'] = valid_coins.to_dict()
        
        # 4. Day (Analist + Gün)
        self.db['day'] = df.groupby(['analysts', 'Day'])['Status_Bool'].mean().to_dict()
        
        print("✅ TradeGuard Motoru Başarıyla Hazırlandı (v11.0)")

    def _get_session(self, dt):
        """NY Saatine göre seans belirler"""
        h = dt.hour
        m = dt.minute
        if (h > 9 or (h == 9 and m >= 30)) and h < 16: return 'New York'
        if h >= 2 and h < 9: return 'London'
        if (h == 9 and m < 30): return 'London'
        if h >= 18 or h < 2: return 'Asia'
        return 'Pacific'

    def predict_risk(self, analyst, coin, trade_time_trt, position='long', 
                     live_btc_change=0.0, whale_top_ratio=0.5, whale_global_ratio=0.5):
        """
        Canlı verilerle harmanlanmış Nihai Risk Skoru hesaplar.
        """
        
        # 1. Zaman Analizi (TRT)
        # Streamlit'ten gelen datetime objesi kullanılır
        if isinstance(trade_time_trt, str):
            dt = pd.to_datetime(trade_time_trt)
        else:
            dt = trade_time_trt
            
        h, m = dt.hour, dt.minute
        
        # A. KILL ZONES (Likidasyon Tuzakları - TRT Saatiyle)
        trap_score = 0
        trap_msg = None
        
        # NY Open (16:30 - 17:30)
        if (h == 16 and m >= 30) or (h == 17 and m < 30):
            trap_score = -25
            trap_msg = "🗽 NY TRAP: Likidasyon Tuzağı Saati!"
        # London Open
        elif h == 10:
            trap_score = -15
            trap_msg = "💂 LONDON TRAP: Fake Hareket Riski!"
        # Daily Reset
        elif h == 3:
            trap_score = -10
            trap_msg = "🌏 DAILY RESET: Yüksek Spread Riski!"

        # B. GEÇMİŞ İSTATİSTİK (Ağırlıklı Ortalama)
        ny_date = dt - timedelta(hours=8)
        session = self._get_session(ny_date)
        day_name = dt.strftime('%A')

        # Veritabanından çek (Veri yoksa %50 nötr varsay)
        g_wr = self.db['global'].get(analyst, 0.50)
        s_wr = self.db['session'].get((analyst, session), g_wr)
        c_wr = self.db['coin'].get((analyst, coin), g_wr)
        d_wr = self.db['day'].get((analyst, day_name), g_wr)

        # --- YENİ FORMÜL (AI Backtest Sonuçlarına Göre Optimize) ---
        # Coin (%40) | Saat (%30) | Analist (%20) | Gün (%10)
        base_score = (c_wr * 0.40) + (s_wr * 0.30) + (g_wr * 0.20) + (d_wr * 0.10)
        final_score = base_score * 100

        # C. TREND ANALİZİ (Canlı Veri)
        trend_msg = None
        # %1.5 üzeri değişimler trend kabul edilir
        is_bull = live_btc_change > 1.5
        is_bear = live_btc_change < -1.5

        if position == 'long':
            if is_bear:
                final_score -= 15
                trend_msg = f"📉 TREND TERSİ: BTC Düşüyor (%{live_btc_change})."
            elif is_bull:
                final_score += 10
                trend_msg = f"🚀 TREND DOSTU: BTC Yükseliyor (%{live_btc_change})."
        else: # Short
            if is_bull:
                final_score -= 15
                trend_msg = f"📉 TREND TERSİ: BTC Yükseliyor (%{live_btc_change})."
            elif is_bear:
                final_score += 10
                trend_msg = f"🚀 TREND DOSTU: BTC Düşüyor (%{live_btc_change})."

        # D. BALİNA RADARI (Canlı Veri)
        whale_msg = None
        
        if position == 'long':
            # Balinalar Long (%60+) ise destekle
            if whale_top_ratio > 0.60:
                final_score += 20
                whale_msg = "🐋 SMART MONEY: Balinalar Long pozisyonda."
            # Retail Long (%70+), Balina Short (%50-) ise uyar (FOMO Tuzağı)
            elif whale_global_ratio > 0.70 and whale_top_ratio < 0.50:
                final_score -= 25
                whale_msg = "🛑 RETAIL FOMO: Küçük yatırımcı terste kalabilir."
        else: # Short
            # Balinalar Short (%40-) ise destekle
            if whale_top_ratio < 0.40:
                final_score += 20
                whale_msg = "🐋 SMART MONEY: Balinalar Short pozisyonda."
            # Retail Short (%30-), Balina Long (%50+) ise uyar (Panic Tuzağı)
            elif whale_global_ratio < 0.30 and whale_top_ratio > 0.50:
                final_score -= 25
                whale_msg = "🛑 RETAIL PANIC: Küçük yatırımcı panik satışında."

        # E. SONUÇ
        final_score += trap_score
        # Skoru 0-100 arasına sıkıştır
        final_score = max(0, min(100, round(final_score)))
        
        return {
            "score": final_score,
            "analyst": analyst,
            "coin": coin,
            "details": {
                "base_stats": {"coin": f"%{int(c_wr*100)}", "session": f"%{int(s_wr*100)}"},
                "trap_alert": trap_msg,
                "trend_alert": trend_msg,
                "whale_alert": whale_msg
            }
        }
