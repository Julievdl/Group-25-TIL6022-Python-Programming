import pandas as pd
import glob

# Match all the split files (adjust pattern if needed)
files = sorted(glob.glob("Data/vesseldata/vesselpositions_part_*.csv"))

# Read and combine all files
df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)

print(df.shape)  # Check rows/columns

df["upload-timestamp"] = pd.to_datetime(df["upload-timestamp"], utc=True, errors='coerce')

import seaborn as sns
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
import contextily as ctx
from datetime import datetime, timedelta
import plotly.express as px

# 1️⃣ Convert DataFrame to GeoDataFrame
gdf = gpd.GeoDataFrame(
    df,
    geometry=[Point(xy) for xy in zip(df["lon"], df["lat"])],
    crs="EPSG:4326"
)
gdf["timestamp_3min"] = gdf["upload-timestamp"].dt.floor("3min")
#print(gdf)

ids = gdf["radar-length-cm"].unique()
palette = px.colors.qualitative.Dark24  # 24 colors
color_map = {id_: palette[i % len(palette)] for i, id_ in enumerate(ids)}
gdf["color"] = gdf["radar-length-cm"].map(color_map)

def MapOnTime(end_time):
    """
    Create an interactive Plotly map for vessels within a 3-minute window.

    Parameters:
        gdf (GeoDataFrame): vessel positions with 'geometry' and 'upload-timestamp'
        end_time (pd.Timestamp): end of 3-minute window

    Returns:
        fig (plotly.graph_objects.Figure)
    """
    # Ensure timezone aware
    end_time_utc = end_time.tz_convert('UTC')
    
    #print(end_time)
    #print(end_time_utc)
    
    # Define 3-minute window
    start_time = end_time_utc - pd.Timedelta(minutes=3)
    #print(gdf['id'].unique().shape)
    # Filter by range instead of exact match
    gdf_filtered = gdf[
        (gdf["upload-timestamp"] >= start_time) &
        (gdf["upload-timestamp"] <= end_time_utc)
    ]
    
    gdf_filtered = gdf_filtered.copy()
    gdf_filtered.loc[:, "time_diff"] = (end_time_utc - gdf_filtered["upload-timestamp"]).abs()
    gdf_filtered = gdf_filtered.sort_values("time_diff").drop_duplicates(subset="id", keep="first")
    
    #print(gdf_filtered)
    # Extract lon/lat and compute length in meters
   
    gdf_filtered["lon"] = gdf_filtered.geometry.x
    gdf_filtered["lat"] = gdf_filtered.geometry.y
    gdf_filtered["length_m"] = gdf_filtered["radar-length-cm"] / 100

    # Create Plotly map
    fig = px.scatter_mapbox(
        gdf_filtered,
        lat="lat",
        lon="lon",
        size="length_m",
        color="length_m",
        color_discrete_map=color_map,
        hover_name="id",
        hover_data={"length_m": True, "upload-timestamp": True},
        size_max=20,      
        center=dict(lat=52.373, lon=4.9),
        zoom=12,
        mapbox_style="carto-positron",
        height=600
    )

    fig.update_layout(
        mapbox_style="carto-positron",
        title=f"Vessels > 45m at {end_time.strftime('%b %d, %Y %H:%M')}",
        margin={"r":0,"t":50,"l":0,"b":0},
        showlegend=False
    )

    if gdf_filtered.empty:
        # Return empty interactive figure
        print('Empty ship pos fig')
        return px.scatter_mapbox(lat=[], lon=[])
    else:
        return fig

