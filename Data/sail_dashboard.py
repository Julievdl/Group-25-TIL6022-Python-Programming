import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output
import json
import traceback # Nodig voor foutmeldingen

# === STAP 0: Sensor Locations (Extra Robuust) ===
df_sensors = pd.read_csv("sensor-location.csv", sep=";")
df_sensors.dropna(subset=["Lat/Long"], inplace=True)
df_sensors["Objectummer"] = df_sensors["Objectummer"].str.strip()
df_sensors["Locatienaam"] = df_sensors["Locatienaam"].str.replace("ri.", "to", regex=False).str.strip()

def split_lat_lon(lat_lon_str):
    try:
        parts = lat_lon_str.split(",")
        lat = float(parts[0].strip().replace(',', '.'))
        lon = float(parts[1].strip().replace(',', '.'))
        if not (52.0 < lat < 53.0 and 4.0 < lon < 5.5):
             return np.nan, np.nan
        return lat, lon
    except (ValueError, IndexError, AttributeError):
        return np.nan, np.nan

df_sensors[['latitude', 'longitude']] = df_sensors['Lat/Long'].apply(lambda x: pd.Series(split_lat_lon(x)))
df_sensors.dropna(subset=["latitude", "longitude"], inplace=True)
print(f"✅ Sensor locaties geladen. {len(df_sensors)} valide locaties gevonden.")

# === Sensor Locatie Lookup ===
sensor_locations = df_sensors.set_index('Objectummer')[['latitude', 'longitude', 'Locatienaam']].to_dict('index')

# === Flowdata ===
df_flow = pd.read_csv("SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")
df_flow["timestamp"] = pd.to_datetime(df_flow["timestamp"])

# === Transform to long format ===
df_long = df_flow.melt(id_vars=["timestamp"], var_name="sensor_dir", value_name="count")
df_long["sensor_base"] = df_long["sensor_dir"].str.split("_").str[0].str.strip()

# === Aggregeer de tellingen per sensor-basis ===
print("Aggregeren van sensor-richtingen...")
df_long_agg = df_long.groupby(['timestamp', 'sensor_base'])['count'].sum().reset_index()
print("✅ Richtingen geaggregeerd.")

# === Merge with sensor locations ===
merged = df_long_agg.merge(df_sensors, left_on="sensor_base", right_on="Objectummer", how="inner")
print(f"✅ Flow-data gemerged met locaties. {len(merged)} rijen over.")

# === Data Prep ===
merged["count"] = merged["count"].clip(lower=0)
# We berekenen count_norm niet meer, want die gebruiken we niet
# merged["count_norm"] = merged["count"] / merged["count"].max()

# === Sample time steps ===
unique_times_list = sorted(merged["timestamp"].unique())
sampled_times = unique_times_list[::5]
merged = merged[merged["timestamp"].isin(sampled_times)]

# === Verwijder tijdstippen zonder activiteit ===
print("Filteren op actieve tijdstippen...")
timestamp_activity = merged.groupby("timestamp")["count"].sum()
active_timestamps = timestamp_activity[timestamp_activity > 0].index
merged = merged[merged["timestamp"].isin(active_timestamps)]
print(f"✅ Zinloze tijdstippen verwijderd. Resterende stappen: {len(active_timestamps)}")

# === STEP 1: Define Thresholds (3 levels) ===
print("Calculating thresholds (Busy, Capacity, Quiet)...")
thresholds_busy = merged.groupby("sensor_base")["count"].quantile(0.90)
thresholds_capacity = merged.groupby("sensor_base")["count"].quantile(0.98)
thresholds_quiet = merged.groupby("sensor_base")["count"].quantile(0.50)

merged = merged.merge(thresholds_busy.rename("threshold_busy"), left_on="sensor_base", right_index=True, how="left")
merged = merged.merge(thresholds_capacity.rename("threshold_capacity"), left_on="sensor_base", right_index=True, how="left")
merged = merged.merge(thresholds_quiet.rename("threshold_quiet"), left_on="sensor_base", right_index=True, how="left")

# === Veilige standaardwaarden instellen voor NaN-drempels ===
merged['threshold_busy'].fillna(np.inf, inplace=True)
merged['threshold_capacity'].fillna(np.inf, inplace=True)
merged['threshold_quiet'].fillna(0, inplace=True)

# Bepaal de status voor elke meting
merged["is_capacity_exceeded"] = merged["count"] > merged["threshold_capacity"]
merged["is_busy"] = (merged["count"] > merged["threshold_busy"]) & ~merged["is_capacity_exceeded"]
merged["is_quiet"] = merged["count"] < merged["threshold_quiet"]

print("✅ Thresholds calculated.")

# === STEP 2: Neighbor Map ===
NEIGHBOR_MAP = {
    "GVCV-01": ["GVCV-03", "GVCV-04", "GASA-01-A1"], "GVCV-03": ["GVCV-01", "GVCV-04", "GASA-01-A1"],
    "GVCV-04": ["GVCV-01", "GVCV-03", "GASA-01-A1"], "GVCV-05-A": ["GVCV-05-B"], "GVCV-05-B": ["GVCV-05-A"],
    "GVCV-07": ["GVCV-08"], "GVCV-08": ["GVCV-07"], "GVCV-13": ["GVCV-14"], "GVCV-14": ["GVCV-13"],
    "GVCV-06": ["GASA-06"], "GASA-06": ["GVCV-06"], "GASA-01-A1": ["GASA-01-A2", "GASA-01-B", "GASA-01-C"],
    "GASA-01-A2": ["GASA-01-A1", "GASA-01-B", "GASA-01-C"], "GASA-01-B": ["GASA-01-A1", "GASA-01-A2", "GASA-01-C"],
    "GASA-01-C": ["GASA-01-A1", "GASA-01-A2", "GASA-01-B"], "GASA-02-01": ["GASA-02-02"], "GASA-02-02": ["GASA-02-01"],
    "GASA-05-O": ["GASA-05-W"], "GASA-05-W": ["GASA-05-O"], "GASA-03": ["GASA-04", "GASA-02-01"],
    "GASA-04": ["GASA-03", "GASA-01-A1"], "CMSA-GAWW-11": ["CMSA-GAWW-12", "CMSA-GAWW-14", "CMSA-GAWW-19", "CMSA-GAWW-20"],
    "CMSA-GAWW-12": ["CMSA-GAWW-11", "CMSA-GAWW-14", "CMSA-GAWW-15"], "CMSA-GAWW-13": ["CMSA-GAWW-15", "CMSA-GAWW-16", "CMSA-GAWW-17"],
    "CMSA-GAWW-14": ["CMSA-GAWW-11", "CMSA-GAWW-12", "CMSA-GAWW-15"], "CMSA-GAWW-15": ["CMSA-GAWW-12", "CMSA-GAWW-14", "CMSA-GAWW-16", "CMSA-GAWW-13"],
    "CMSA-GAWW-16": ["CMSA-GAWW-15", "CMSA-GAWW-13"], "CMSA-GAWW-17": ["CMSA-GAWW-13", "CMSA-GAWW-21"],
    "CMSA-GAWW-19": ["CMSA-GAWW-11", "CMSA-GAWW-23"], "CMSA-GAWW-20": ["CMSA-GAWW-11", "GACM-04"],
    "CMSA-GAWW-21": ["CMSA-GAWW-17", "CMSA-GAKH-01"], "CMSA-GAWW-23": ["CMSA-GAWW-19"],
    "CMSA-GAKH-01": ["CMSA-GAWW-21", "GACM-04"], "GACM-04": ["CMSA-GAKH-01", "CMSA-GAWW-20"],
}


# === STEP 3: Set up Dash Application ===
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

unique_times_slider = sorted(merged["timestamp"].unique())
slider_marks = {}
for i, t in enumerate(unique_times_slider):
    dt = pd.to_datetime(t)
    if dt.minute == 0 or dt.minute == 30:
        slider_marks[i] = dt.strftime('%d-%m %H:%M')

if len(unique_times_slider) > 0:
    slider_marks[0] = pd.to_datetime(unique_times_slider[0]).strftime('%d-%m %H:%M')
    slider_marks[len(unique_times_slider)-1] = pd.to_datetime(unique_times_slider[-1]).strftime('%d-%m %H:%M')
else:
    print("FATALE FOUT: Geen data overgebleven na filteren!")


app.layout = dbc.Container([
    html.H1("SAIL 2025 Crowd Management Dashboard", className="my-4 text-primary"),
    dbc.Row([
        dbc.Col(
            dcc.Graph(id="map-graph", style={"height": "75vh"}),
            width=8
        ),
        dbc.Col(
            [
                html.H4("Alerts & Rerouting Advice", className="text-secondary"),
                html.Hr(),
                html.Div(id="alert-panel-status"),
                dbc.ListGroup(id="alert-list-group", flush=True)
            ],
            width=4,
            style={"background-color": "#f8f9fa", "padding": "20px", "border-radius": "5px", "height": "75vh", "overflow-y": "auto"}
        )
    ]),
    dbc.Row([
        dbc.Col(
            [
                html.Label("Select Timestamp:", className="mt-3"),
                dcc.Slider(
                    id="time-slider",
                    min=0,
                    max=len(unique_times_slider) - 1,
                    value=0,
                    marks=slider_marks,
                    step=1
                )
            ],
            width=12
        )
    ])
], fluid=True)

# === [GEWIJZIGD] STEP 4: De Enige Callback ===
# Met try-except blok en veiligere buur-lookup
@app.callback(
    Output("alert-panel-status", "children"),
    Output("alert-list-group", "children"),
    Output("map-graph", "figure"),
    Input("time-slider", "value"),
)
def update_alerts_and_map(slider_index):
    # --- Voorbereiding ---
    current_time = unique_times_slider[slider_index]
    current_time_str = pd.to_datetime(current_time).strftime('%A %d-%m-%Y %H:%M')
    fig = go.Figure() # Begin ALTIJD met een lege figuur

    try:
        # --- 1. Data Ophalen ---
        data_at_time = merged[merged["timestamp"] == current_time].copy()
        data_at_time.dropna(subset=['latitude', 'longitude'], inplace=True)

        if data_at_time.empty:
             print(f"--- WAARSCHUWING: Geen valide data gevonden voor {current_time_str} ---")
             fig.update_layout(title=f"No Valid Data at: {current_time_str}", map_style="carto-positron", map_center=dict(lat=52.373, lon=4.9), map_zoom=12.5)
             return html.P("No valid sensor data for this time."), [], fig

        status_lookup = data_at_time.set_index('sensor_base')
        capacity_alerts = data_at_time[data_at_time["is_capacity_exceeded"] == True]
        busy_alerts = data_at_time[data_at_time["is_busy"] == True]

        # --- 2. Variabelen Initialiseren ---
        alert_status_message = dbc.Alert("✅ Normal density. No immediate action required.", color="success", className="mt-3")
        alert_list_items = []
        lats_red, lons_red, texts_red = [], [], []
        lats_yellow, lons_yellow, texts_yellow = [], [], []
        lats_green, lons_green, texts_green = [], [], []

        if not capacity_alerts.empty or not busy_alerts.empty:
            alert_status_message = html.H6("⚠️ Alerts Detected:", className="mt-3 text-danger")

            # --- 3. Verwerk Rode Alerts (Capacity) + Groene Oplossingen ---
            for _, row in capacity_alerts.iterrows():
                sensor_id = row['sensor_base']
                location_name = row.get('Locatienaam', sensor_id)
                advice_text = ""

                if pd.notna(row['latitude']) and pd.notna(row['longitude']):
                    lats_red.append(row['latitude'])
                    lons_red.append(row['longitude'])
                    texts_red.append(f"PROBLEM: {location_name} ({sensor_id})")
                else:
                    print(f"--- DEBUG: RODE pin OVERGESLAGEN (NaN Coördinaten): {location_name} ({sensor_id}) ---")

                neighbors = NEIGHBOR_MAP.get(sensor_id, [])
                found_quiet_neighbor = False
                for neighbor_id in neighbors:
                    # [NIEUWE VEILIGHEIDSCHECK] Bestaat de buur in de data van DIT moment?
                    if neighbor_id in status_lookup.index:
                        neighbor_row = status_lookup.loc[neighbor_id]
                        if neighbor_row['is_quiet']:
                            neighbor_name = neighbor_row.get('Locatienaam', neighbor_id)
                            advice_text = f"ADVICE: Reroute people to {neighbor_name}."
                            if pd.notna(neighbor_row['latitude']) and pd.notna(neighbor_row['longitude']):
                                lats_green.append(neighbor_row['latitude'])
                                lons_green.append(neighbor_row['longitude'])
                                texts_green.append(f"SOLUTION: {neighbor_name} ({neighbor_id})")
                                found_quiet_neighbor = True
                                break
                            else:
                                 print(f"--- DEBUG: GROENE pin OVERGESLAGEN (NaN Coördinaten): {neighbor_name} ({neighbor_id}) ---")
                    # else: # Optioneel: printen als buur niet gevonden wordt
                    #     print(f"--- DEBUG: Buur {neighbor_id} niet gevonden in data voor {current_time_str} ---")


                if not found_quiet_neighbor and advice_text == "":
                    advice_text = "ADVICE: All nearby routes are also busy. Monitor situation!"

                item_content = [
                    html.H6(f"CAPACITY EXCEEDED: {location_name} ({sensor_id})", className="mb-1"),
                    html.Small(f"Current count: {int(row['count'])}", className="text-muted"),
                    html.P(advice_text, className="mb-1 mt-2"),
                ]
                alert_list_items.append(dbc.ListGroupItem(item_content, color="danger", className="mb-2"))

            # --- 4. Verwerk Gele Alerts (Busy) ---
            for _, row in busy_alerts.iterrows():
                sensor_id = row['sensor_base']
                location_name = row.get('Locatienaam', sensor_id)
                advice_text = "ADVICE: High traffic. Monitor situation."

                if pd.notna(row['latitude']) and pd.notna(row['longitude']):
                    lats_yellow.append(row['latitude'])
                    lons_yellow.append(row['longitude'])
                    texts_yellow.append(f"BUSY: {location_name} ({sensor_id})")
                else:
                     print(f"--- DEBUG: GELE pin OVERGESLAGEN (NaN Coördinaten): {location_name} ({sensor_id}) ---")

                item_content = [
                    html.H6(f"HIGH TRAFFIC: {location_name} ({sensor_id})", className="mb-1"),
                    html.Small(f"Current count: {int(row['count'])}", className="text-muted"),
                    html.P(advice_text, className="mb-1 mt-2"),
                ]
                alert_list_items.append(dbc.ListGroupItem(item_content, color="warning", className="mb-2"))

        # --- 5. Maak de Kaart Figuur ---
        fig.update_layout(
            margin={"r": 0, "t": 50, "l": 0, "b": 0},
            title=f"Alerts at: {current_time_str}",
            map_style="carto-positron",
            map_center=dict(lat=52.373, lon=4.9),
            map_zoom=12.5,
            showlegend=False
        )

        print(f"--- DEBUG: Tijd: {current_time_str} --- Rood:{len(lats_red)} Geel:{len(lats_yellow)} Groen:{len(lats_green)} ---")

        # Aparte add_trace voor elke kleur
        if len(lats_red) > 0:
            fig.add_trace(go.Scattermap(
                lat=lats_red, lon=lons_red, mode='markers+text',
                marker=dict(color='red', symbol='circle', size=18, allowoverlap=True),
                text=texts_red, textposition='bottom right',
                textfont=dict(size=14, color='black'), hoverinfo='text', name='Capacity Alert'
            ))

        if len(lats_yellow) > 0:
            fig.add_trace(go.Scattermap(
                lat=lats_yellow, lon=lons_yellow, mode='markers+text',
                marker=dict(color='yellow', symbol='circle', size=18, allowoverlap=True),
                text=texts_yellow, textposition='bottom right',
                textfont=dict(size=14, color='black'), hoverinfo='text', name='Busy Alert'
            ))

        if len(lats_green) > 0:
            fig.add_trace(go.Scattermap(
                lat=lats_green, lon=lons_green, mode='markers+text',
                marker=dict(color='green', symbol='circle', size=18, allowoverlap=True),
                text=texts_green, textposition='bottom right',
                textfont=dict(size=14, color='black'), hoverinfo='text', name='Solution Location'
            ))

        # --- 6. Return alle outputs ---
        return alert_status_message, alert_list_items, fig

    except Exception as e:
        # [NIEUW] Vang de fout op!
        print(f"!!! FOUT GEVANGEN op tijdstip {current_time_str} !!!")
        print(traceback.format_exc()) # Print de volledige foutmelding in de terminal
        
        # Maak een lege kaart met een foutmelding
        fig = go.Figure()
        fig.update_layout(title=f"ERROR processing data at: {current_time_str}", map_style="carto-positron", map_center=dict(lat=52.373, lon=4.9), map_zoom=12.5)
        
        # Geef een foutmelding terug voor de alerts
        error_message = dbc.Alert(f"An error occurred processing data for {current_time_str}. Check terminal for details.", color="danger")
        return error_message, [], fig


# === STEP 7: Run the Application ===
if __name__ == "__main__":
    print("Starting Dash app... Go to http://127.0.0.1:8050/ in your browser.")
    app.run(debug=True, port=8050)