import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import holidays  # YENİ KÜTÜPHANE

class TradeGuardAI:
    def __init__(self, csv_file):
        self.csv_file = csv_file
        self.db = {'global': {}, 'session': {}, 'coin': {}, 'day': {}}
        self.active_trader_count = 0
        
        # TATİL VERİTABANI (2024-2030)
        self.us_holidays = holidays.US() # New York için
        self.uk_holidays = holidays.UK() # Londra için
        
        self.load_and_train()

    def load_and_train(self):
        try:
            df = pd.read_csv(self.csv_file)
        except FileNotFoundError:
            df = pd.DataFrame(columns=['analysts', 'coin_name', 'Status', 'Close Date'])
            return

        # Tarih İşleme & Filtreleme (Son 6 Ay)
        df['Close Date'] = pd.to_datetime(df['Close Date'], format='%B %d, %Y, %I:%M %p', errors='coerce')
        df = df.dropna(subset=['Close Date'])
        
        cutoff_date = datetime.now() - timedelta(days=180)
        df = df[df['Close Date'] >= cutoff_date]
        
        if len(df) == 0: # Eğer filtre çok sıkıysa ve veri kalmazsa yedeği yükle
             df = pd.read_csv(self.csv_file)
             df['Close Date'] = pd.to_datetime(df['Close Date'], format='%B %d, %Y, %I:%M %p', errors='coerce')

        self.active_trader_count = df['analysts'].nunique()
        df['Status_Bool'] = (df['Status'] == 'success').astype(int)
        
        # Session Logic
        df['NY_Date'] = df['Close Date'] - timedelta(hours=8)
        df['Session'] = df['NY_Date'].apply(self._get_session)
        df['Day'] = df['Close Date'].dt.day_name()

        # Stats
        self.db['global'] = df.groupby('analysts')['Status_Bool'].mean().to_dict()
        self.db['session'] = df.groupby(['analysts', 'Session'])['Status_Bool'].mean().to_dict()
        self.db['coin'] = df.groupby(['analysts', 'coin_name'])['Status_Bool'].mean().to_dict()
        self.db['day'] = df.groupby(['analysts', 'Day'])['Status_Bool'].mean().to_dict()

    def _get_session(self, dt):
        h = dt.hour; m = dt.minute
        if (h > 9 or (h == 9 and m >= 30)) and h < 16: return 'New York'
        if h >= 2 and h < 9: return 'London'
        if (h == 9 and m < 30): return 'London'
        if h >= 18 or h < 2: return 'Asia'
        return 'Pacific'

    def check_market_status(self, trade_dt):
        """
        O günün borsa tatili olup olmadığını kontrol eder.
        trade_dt: datetime objesi
        """
        date_str = trade_dt.strftime('%Y-%m-%d')
        
        status = "OPEN"
        message = None
        
        # Hafta Sonu Kontrolü
        if trade_dt.weekday() >= 5: # 5=Cmt, 6=Paz
            return "WEEKEND", "Haftasonu: Düşük Hacim / Bot Manipülasyonu Riski"

        # Resmi Tatil Kontrolü
        if date_str in self.us_holidays:
            holiday_name = self.us_holidays.get(date_str)
            return "HOLIDAY_US", f"ABD Borsaları Kapalı ({holiday_name}). NY Tuzağı Çalışmaz ama Hacim Çok Düşük Olur."
            
        if date_str in self.uk_holidays:
            holiday_name = self.uk_holidays.get(date_str)
            return "HOLIDAY_UK", f"Londra Borsaları Kapalı ({holiday_name})."
            
        return "OPEN", "Piyasalar Açık"

    def predict_risk(self, analyst, coin, trade_time_trt, position='long', 
                     live_btc_change=0.0, whale_top_ratio=0.5, whale_global_ratio=0.5):
        
        if isinstance(trade_time_trt, str): dt = pd.to_datetime(trade_time_trt)
        else: dt = trade_time_trt
            
        h, m = dt.hour, dt.minute
        
        # 1. MARKET STATUS CHECK (TATİL Mİ?)
        market_code, market_msg = self.check_market_status(dt)
        
        # 2. KILL ZONES (Eğer tatil değilse çalışır)
        trap_score = 0; trap_msg = None
        
        if market_code == "OPEN":
            # Standart Tuzaklar
            if (h == 16 and m >= 30) or (h == 17 and m < 30):
                trap_score = -25; trap_msg = "🗽 NY TRAP: Likidasyon Tuzağı Saati!"
            elif h == 10:
                trap_score = -15; trap_msg = "💂 LONDON TRAP: Fake Hareket Riski!"
            elif h == 3:
                trap_score = -10; trap_msg = "🌏 DAILY RESET: Yüksek Spread Riski!"
        elif market_code == "WEEKEND":
            trap_score = -15 # Haftasonu genel ceza
            trap_msg = market_msg
        else: # HOLIDAY
            trap_score = -20 # Tatil belirsizlik cezası
            trap_msg = f"⚠️ {market_msg}"

        # 3. İSTATİSTİK
        ny_date = dt - timedelta(hours=8)
        session = self._get_session(ny_date)
        day_name = dt.strftime('%A')

        g_wr = self.db['global'].get(analyst, 0.50)
        s_wr = self.db['session'].get((analyst, session), g_wr)
        c_wr = self.db['coin'].get((analyst, coin), g_wr)
        d_wr = self.db['day'].get((analyst, day_name), g_wr)

        base_score = (c_wr * 0.40) + (s_wr * 0.30) + (g_wr * 0.20) + (d_wr * 0.10)
        final_score = base_score * 100

        # 4. TREND (LIVE)
        trend_msg = None
        is_bull = live_btc_change > 1.5; is_bear = live_btc_change < -1.5

        if position == 'long':
            if is_bear: final_score -= 15; trend_msg = f"📉 TREND TERSİ: BTC Düşüyor (%{live_btc_change})."
            elif is_bull: final_score += 10; trend_msg = f"🚀 TREND DOSTU: BTC Yükseliyor."
        else:
            if is_bull: final_score -= 15; trend_msg = f"📉 TREND TERSİ: BTC Yükseliyor."
            elif is_bear: final_score += 10; trend_msg = f"🚀 TREND DOSTU: BTC Düşüyor."

        # 5. WHALE (LIVE)
        whale_msg = None
        if position == 'long':
            if whale_top_ratio > 0.60: final_score += 20; whale_msg = "🐋 SMART MONEY: Balinalar Long."
            elif whale_global_ratio > 0.70 and whale_top_ratio < 0.50: final_score -= 25; whale_msg = "🛑 RETAIL FOMO: Küçük yatırımcı terste."
        else:
            if whale_top_ratio < 0.40: final_score += 20; whale_msg = "🐋 SMART MONEY: Balinalar Short."
            elif whale_global_ratio < 0.30 and whale_top_ratio > 0.50: final_score -= 25; whale_msg = "🛑 RETAIL PANIC: Küçük yatırımcı panikte."

        final_score += trap_score
        final_score = max(0, min(100, round(final_score)))
        
        return {
            "score": final_score,
            "analyst": analyst,
            "details": {
                "market_status": market_msg, # Yeni Bilgi
                "base_stats": {"coin": f"%{int(c_wr*100)}", "session": f"%{int(s_wr*100)}"},
                "trap_alert": trap_msg, "trend_alert": trend_msg, "whale_alert": whale_msg
            }
        }
