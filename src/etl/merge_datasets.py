import pandas as pd

# Read existing data (6,184 products)
df_existing = pd.read_csv('/home/augusto/Desktop/Vademecum/vademecum_productos.csv')
print(f"Existing products: {len(df_existing)}")

# Read newly scraped missing data (2,261 products)
df_missing = pd.read_csv('/home/augusto/Desktop/Vademecum/vademecum_productos_missing.csv')
print(f"Missing products scraped: {len(df_missing)}")

# Concatenate
df_combined = pd.concat([df_existing, df_missing], ignore_index=True)
print(f"Combined (before dedup): {len(df_combined)}")

# Drop duplicates by URL (most reliable identifier)
if 'url' in df_combined.columns:
    df_dedup = df_combined.drop_duplicates(subset=['url'], keep='first')
    print(f"After URL dedup: {len(df_dedup)}")
else:
    # Fallback: dedup by all columns
    df_dedup = df_combined.drop_duplicates(keep='first')
    print(f"After full-row dedup: {len(df_dedup)}")

# Save merged file
df_dedup.to_csv('/home/augusto/Desktop/Vademecum/vademecum_productos_complete.csv', index=False)
print(f"\nFinal merged file saved: vademecum_productos_complete.csv")
print(f"Total unique products: {len(df_dedup)}")