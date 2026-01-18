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
        df['Day'] =