import pandas as pd
import numpy as np

# 1. Veri setlerini yükleyelim
df_rayli = pd.read_csv('istanbul_rayli_sistem_verileri_guncel.csv')
df_match = pd.read_csv('match_station_offset_features.csv')

# 2. Hat kapasitelerini maç veri setine eklemek için birleştirme (merge) yapalım
df_merged = df_match.merge(
    df_rayli[['Hat_Adi', 'Set_Kapasitesi_Yolcu']], 
    left_on='line', 
    right_on='Hat_Adi', 
    how='left'
)

# 3. Talebin tren kapasitesinin kaç katı olduğunu hesaplayalım
df_merged['tren_kat_orani'] = df_merged['mean_change'] / df_merged['Set_Kapasitesi_Yolcu']

# 4. İstediğiniz özel yuvarlama kuralını uygulayan fonksiyon
def hesapla_ek_tren(oran):
    if pd.isna(oran):
        return np.nan
    if oran <= 0:
        return 0  # Talep artışı yoksa veya negatifse ek trene ihtiyaç yoktur
    
    tam_kisim = np.floor(oran)
    kesir_kismi = oran - tam_kisim
    
    # 0.30 ve üzeri ise üste, değilse alta yuvarlama
    if kesir_kismi >= 0.30:
        return int(tam_kisim + 1)
    else:
        return int(tam_kisim)

# 5. Yeni kolonu ("ek_tren_sayisi") oluşturalım
df_merged['ek_tren_sayisi'] = df_merged['tren_kat_orani'].apply(hesapla_ek_tren)

# 6. Ara işlemlerde kullandığımız geçici kolonları temizleyelim
df_final = df_merged.drop(columns=['Hat_Adi', 'Set_Kapasitesi_Yolcu', 'tren_kat_orani'])

# 7. Yeni veri setini kaydedelim
df_final.to_csv('match_station_offset_with_trains.csv', index=False)
print("Yeni veri seti 'match_station_offset_with_trains.csv' olarak başarıyla kaydedildi.")