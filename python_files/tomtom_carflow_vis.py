import pandas as pd
import geopandas as gpd
import folium
import pyarrow.parquet as pq
import os
import json
from io import StringIO
import branca.colormap as cm

# ===
# definitieve verkeerskaart! nu met folium dus interactief :))
# ====

# --- Configuratie ---
TOMTOM_FILE_PATH = os.path.join('Data', '20250820163000_stream.tomtom.analyze-sail.parquet')
SHAPEFILE_PATH = r'C:\Users\gerri\Downloads\01-12-2024\01-12-2024\Wegvakken\Wegvakken.shp'
SAMPLE_FRACTION = 0.1
SHAPEFILE_ID_COL = 'WVK_ID'


def parse_tomtom_data(value_string):
    """Verwerkt de data uit de '_value' kolom."""
    try:
        start_index = value_string.find('{')
        if start_index == -1: return None
        data = json.loads(value_string[start_index:])
        if 'data' in data and isinstance(data['data'], str):
            return pd.read_csv(StringIO(data['data']))
    except (json.JSONDecodeError, KeyError):
        return None
    return None

def create_traffic_map():
    """Voert het volledige proces uit van data laden tot het maken van een Folium kaart."""
    try:
        # --- 1. Data Laden, Verwerken en Koppelen (Bewezen Stabiel) ---
        print(f"Laden van {SAMPLE_FRACTION*100}% sample uit {TOMTOM_FILE_PATH}...")
        df_raw = pd.read_parquet(TOMTOM_FILE_PATH).sample(frac=SAMPLE_FRACTION, random_state=1)
        
        print("Verwerken van verkeersdata...")
        parsed_dfs = df_raw['_value'].apply(parse_tomtom_data)
        df_traffic = pd.concat(parsed_dfs.dropna().tolist(), ignore_index=True)
        
        print("Aggregeren van verkeersdata...")
        df_traffic_agg = df_traffic.groupby('id')['traffic_level'].mean().reset_index()
        
        print(f"\nLaden van kaartdata: {SHAPEFILE_PATH}...")
        gdf = gpd.read_file(SHAPEFILE_PATH)
        
        print("Coördinatensysteem omzetten...")
        gdf = gdf.to_crs(epsg=4326)
        
        print("Filteren op Amsterdam...")
        min_lon, min_lat, max_lon, max_lat = 4.72, 52.28, 5.08, 52.43
        gdf_amsterdam = gdf.cx[min_lon:max_lon, min_lat:max_lat].copy()
        
        print("\nKoppelen van data...")
        gdf_amsterdam[SHAPEFILE_ID_COL] = gdf_amsterdam[SHAPEFILE_ID_COL].astype(str)
        df_traffic_agg['id'] = df_traffic_agg['id'].astype(str)
        
        merged_gdf = gdf_amsterdam.merge(df_traffic_agg, left_on=SHAPEFILE_ID_COL, right_on='id', how='left')
        print(f"Succesvol {len(merged_gdf):,} totale wegvakken voorbereid voor de kaart.")
        
        # --- 2. Visualisatie met Folium  ---
        print("Genereren van de Folium verkeerskaart...")
        
        # * Converteer alle datumkolommen naar strings**
        # Dit voorkomt de "JSON not serializable" fout.
        for col in merged_gdf.columns:
            if pd.api.types.is_datetime64_any_dtype(merged_gdf[col]):
                print(f"Datumkolom '{col}' wordt omgezet naar string...")
                merged_gdf[col] = merged_gdf[col].astype(str)

        amsterdam_location = [52.3676, 4.9041]
        sw = [52.370, 4.885] #southwest corner
        ne = [52.405, 4.995] #northeast corner
        m = folium.Map(location=amsterdam_location, zoom_start=12, tiles="CartoDB positron", max_bounds=True)
        
        m.fit_bounds([sw,ne])
        
        # Maak een kleurenschaal van groen naar rood
        colormap = cm.LinearColormap(colors=['green', 'yellow', 'red'], vmin=0, vmax=1)
        colormap.caption = 'Gemiddelde Verkeersdrukte'

        # Definieer de style functie die voor ELK wegvak de kleur bepaalt
        def style_function(feature):
            traffic = feature['properties']['traffic_level']
            return {
                'fillOpacity': 0.7,
                'weight': 1.5,
                # Als er geen data is, maak het transparant, anders gebruik de colormap
                'fillColor': '#d3d3d3' if pd.isna(traffic) else colormap(traffic),
                'color': '#d3d3d3' if pd.isna(traffic) else colormap(traffic)
            }

        # Maak een GeoJson laag met de tooltip en de style functie
        folium.GeoJson(
            merged_gdf,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(
                fields=[SHAPEFILE_ID_COL, 'STT_NAAM', 'traffic_level'],
                aliases=['Wegvak ID:', 'Straat:', 'Verkeersdrukte:'],
                sticky=True
            )
        ).add_to(m)
        
        # Voeg de legenda toe aan de kaart
        m.add_child(colormap)
        
        print("\n--- SUCCES! ---")
        print("De kaart is aangemaakt en zou nu moeten verschijnen.")
        
        m.save("verkeerskaart_amsterdam_definitief.html")
        print("Een kopie is opgeslagen als 'verkeerskaart_amsterdam_definitief.html'")
        
        return m

    except Exception as e:
        print(f"Er is een onverwachte fout opgetreden: {e}")
        return None

# Voer het script uit en toon de kaart
traffic_map = create_traffic_map()
traffic_map
