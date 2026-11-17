"""Summarise the DataVic fire history download: fields, CRS, size, key values."""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "data" / "historical" / "fire_history"

files = sorted(list(FOLDER.rglob("*.shp")) + list(FOLDER.rglob("*.gpkg")))
print("Map files found:", [str(f.relative_to(FOLDER)) for f in files])
path = next(f for f in files if "FIRE" in f.name.upper()) if any("FIRE" in f.name.upper() for f in files) else files[0]
print("Reading:", path.relative_to(FOLDER))

gdf = gpd.read_file(path)
print(f"\nRows: {len(gdf):,}   CRS: {gdf.crs}")
print("\nColumns and types:")
print(gdf.dtypes.to_string())

pd.set_option("display.width", 200)
print("\nFirst 3 rows:")
print(gdf.drop(columns="geometry").head(3).to_string())

print("\nColumns with few distinct values:")
for col in gdf.columns.drop("geometry"):
    n = gdf[col].nunique(dropna=False)
    if 1 < n <= 15:
        print(f"\n  {col}:")
        print("   " + gdf[col].value_counts(dropna=False).to_string().replace("\n", "\n   "))
