import pandas as pd
import math

# Veri setlerini yükleme
demand_df = pd.read_csv('match_station_offset_features.csv')
metro_df = pd.read_csv('istanbul_rayli_sistem_verileri_guncel.csv')

# 1. Negatif demand değişimlerini göz ardı et (sadece pozitif olanları toplayacağız)
demand_df['mean_change'] = demand_df['mean_change'].apply(lambda x: x if x > 0 else 0)

# 2. Takım ve hat bazında toplam (veya genel) fazladan demandi hesapla
grouped_demand = demand_df.groupby(['team', 'line'])['mean_change'].sum().reset_index()
grouped_demand.rename(columns={
    'team': 'takım adı', 
    'line': 'hat', 
    'mean_change': 'ortalama fazladan demand'
}, inplace=True)

# 3. Metro kapasitesi verileriyle birleştirme
merged_df = pd.merge(grouped_demand, metro_df[['Hat_Adi', 'Set_Kapasitesi_Yolcu']], left_on='hat', right_on='Hat_Adi', how='inner')

# 4. İhtiyaç duyulan sefer/tren sayısını hesaplama (Özel Yuvarlama Kuralı)
def custom_round(val):
    decimal_part = val % 1
    # Eğer küsurat 0.30 ve üzeriyse yukarı yuvarla, değilse aşağı yuvarla
    if decimal_part >= 0.30:
        return math.ceil(val)
    else:
        return math.floor(val)

# Toplam demandi kapasiteye bölüp custom_round fonksiyonunu uyguluyoruz
merged_df['kaç trene karşılık geldiği'] = (merged_df['ortalama fazladan demand'] / merged_df['Set_Kapasitesi_Yolcu']).apply(custom_round)

# 5. İstenen 4 kolonu seçme
final_df = merged_df[['takım adı', 'hat', 'ortalama fazladan demand', 'kaç trene karşılık geldiği']]

# Sonucu yeni bir CSV'ye kaydetme
final_df.to_csv('kompakt_demand_verisi.csv', index=False)

# İlk 5 satırı kontrol etmek isterseniz:
print(final_df.head())