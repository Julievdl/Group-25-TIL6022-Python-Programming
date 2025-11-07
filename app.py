import pandas as pd
from dash import Dash, dcc, html, callback, Output, Input
from datetime import datetime, timedelta
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from python_files.animplot import fig as animfig, flow_bar
from python_files.data_combining import df_long as flowdata
from python_files.heat_map import figheat as heatmap, unique_times, merged as heatdata, heatmap_fig
from python_files.vesselpositions import MapOnTime as shipmap, gdf as shipdata

flowdata=flowdata.sort_values(by=['sensor_direction','timestamp'])


#ALERT SYSTEM PREP-----
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output
import json
import traceback # Nodig voor foutmeldingen

TIME_OFFSET = 260

# === STAP 0: Sensor Locations (Extra Robuust) ===
df_sensors = pd.read_csv("Data/sensor-location.csv", sep=";")
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
df_flow = pd.read_csv("Data/SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")
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
#sampled_times = unique_times_list[::5]
#merged = merged[merged["timestamp"].isin(sampled_times)]

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




#Clock speed indicator (1000 = 1s)
CLOCK_SPEED = 7000


app = Dash(__name__)

app.layout = html.Div([
    
    #Container for main content and sidebar
    html.Div([
    
    #Sidebar
    html.Div([
        
        #Top section: title + clock
        html.Div([ 
        html.Div(id='live-time',style={"fontSize": "30px", "fontWeight": "bold"}),
        dcc.Interval(id='interval-component', interval=CLOCK_SPEED,n_intervals=0),
        ],style={"padding-bottom": "20px"}),
        
        
        #Alerts section
        html.Div([
            dcc.Store(id='alert-history', data=[]), #save previous alerts
            
            # Updating of graphs (synching of alerts, heatmap and flow )
            # Multiplied by 3 as we have data only once every 3 min. 
            dcc.Interval(id='graph-update-interval', interval=CLOCK_SPEED * 3, n_intervals=0),
            html.H4("Alerts & Rerouting Advice", className="text-secondary"),
            html.Hr(),
            html.Div(id="alert-panel-status"),
            dbc.ListGroup(id="alert-list-group", flush=True),
            ],style={"padding-bottom": "20px","height":"200 px","flexDirection": "column-reverse","overflowY": "auto",}),
        
        #Graph
        html.Div([
            dcc.Graph(id="map-graph")
        ],style={"height":"60vh"})
        
    ], 
            #Sidebar style
            style={
        "position": "sticky",
        "top": "0",
        "width": "50vw",
        "height": "100vh",
        "background-color": "#f8f9fa",
        "display": "flex",
        "flex-direction": "column"
    }),

    #Main content
    html.Div([
        
        
        dcc.Tabs(id="tabs-dash", value='ped-overview', children=[
            
        #Area overview tab
        dcc.Tab(label='Area Overview', value='area-overview', children=[
            html.Div([
        html.Iframe(
        id='sensor-map',
        src="/assets/interactive_sensor_map.html",
        style={"width": "100%", "height": "600px", "border": "none"}  # hidden initially
            )
            ],style={'padding':'20px'})
        ]),
        
        #Area overview tab
        dcc.Tab(label='Vessel Overview', value='vessel-overview', children=[
            html.Div([
            #html.H3('Area Overview'),
            dcc.Graph(
            figure=px.scatter_mapbox(lat=[], lon=[]),
            id='vesselmap',style={"height":"500 px"}
            ),
            html.Img(
            src="/assets/sensormap.png",  # path relative to the Dash server
            style={"width": "500px", "height": "auto"}  # optional styling
            ),
            ],style={'padding':'20px'})
        ]),
        
        #Pedestrian overview tab
        dcc.Tab(label='Pedestrian Overview', value='ped-overview', id='ped-overview', children=[
            html.Div([
            #html.H3('Pedestrian Traffic'),
            
            dcc.Graph(
            figure=heatmap,
            id='heatmap',style={"height":"100 px"}
            ),
            
            html.H3('Plotted timestamp:'),
            html.H3(id='plottime'),
            dcc.Graph(
            figure=animfig,
            id='animfig',style={"flex":"1"}
            ),
            
            html.H3('History'),
            #static figures
            dcc.Graph(
            figure=heatmap,

            ),
            
            dcc.Graph(
            figure=animfig,

            ),          
            ],style={'padding':'20px'})
        ]),
        
        
        #Car traffic overview tab
        dcc.Tab(label='Car Traffic Overview', value='car-overview', children=[
            html.Div([
        html.Iframe(
        id='car-map',
        src="/assets/verkeerskaart_amsterdam_wegen_in_out_styled.html",
        style={"width": "100%", "height": "600px", "border": "none", "display": "none"}  # hidden initially
            )
            ],style={'padding':'20px'})
        ]),
        
        ],
            #  Style for main content
             style={
            "position": "sticky",
            "top": "0",
            "backgroundColor": "white",
            "zIndex": 1000  # make sure it’s on top
        }),
    
    ],style={"flex": "1", "padding": "20px"})
    
    ], style={"display": "flex"}),
    
    html.Div(id='tabs-information')
])









#Live clock
@app.callback(
    Output('live-time', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_time(n):
    start = datetime(year=2025,month=8,day=20,hour=13,minute=0,second=0)
    now = start + timedelta(minutes=n)
    now = now.strftime("%H:%M")
    print('timeprint', now)
    return f"SAIL 2025 Crowd Management Dashboard - {now}"

#Hopefully improve loading for car map
@app.callback(
    Output('car-map','style'),
    Input('tabs-dash','value')
)
def show_car_map(tab):
    if tab == 'car-overview':
        return {"width": "100%", "height": "600px", "border": "none", "display": "block"}
    return {"display":"none"}

#Alert system callback
@app.callback(
    Output("alert-panel-status", "children"),
    Output("alert-list-group", "children"),
    Output("alert-history","data"),
    Output("map-graph", "figure"),
    Input("graph-update-interval", "n_intervals"),
    Input('alert-history', 'data')
)
def update_alerts_and_map(slider_index,history):
    
    # history = list of previous alert ListGroupItems
    history = history or []
    
    # --- Voorbereiding ---
    current_time = unique_times[TIME_OFFSET + slider_index % len(unique_times)]
    current_time_str = pd.to_datetime(current_time).strftime('%A %d-%m-%Y %H:%M')
    fig = go.Figure() # Begin ALTIJD met een lege figuur
    print(f"slider_index={slider_index}, current_time={current_time}")


    
    try:
        # Base map layout (always present)
        # fig.update_layout(
        #     margin={"r":0,"t":50,"l":0,"b":0},
        #     title=f"Alerts at: {current_time_str}",
        #     map_style="carto-positron",
        #     map_center=dict(lat=52.373, lon=4.9),
        #     map_zoom=12.5,
        #     showlegend=False
        # )
        
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
        
        timestamp_header = dbc.ListGroupItem(
        f"--- {current_time} ---", color="secondary", className="text-center")
        
        alert_list_items = alert_list_items + history
        
        print(f"--- DEBUG: Tijd: {current_time_str} --- Rood:{len(lats_red)} Geel:{len(lats_yellow)} Groen:{len(lats_green)} ---")
        print('red',len(lats_red))
        print('yellow',len(lats_yellow))
        print('green',len(lats_green))
        # Aparte add_trace voor elke kleur
        if len(lats_red) > 0:
            fig.add_trace(go.Scattermap(
                lat=lats_red, lon=lons_red, mode='markers+text',
                marker=dict(color='red', symbol='circle', size=18, allowoverlap=True),
                text=texts_red, textposition='bottom right',
                textfont=dict(size=14, color='black'), hoverinfo='text', name='Capacity Alert'
            ))
            

        if len(lats_yellow) > 0:
            print('yellowprint')
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
            
        # Hack to make sure the map doesn't dissapear lmaoooo
        fig.add_trace(go.Scattermap(
            lat=[5], lon=[60], mode='markers+text',
            marker=dict(color='white', symbol='circle', size=1, allowoverlap=True),
            text=texts_green, textposition='bottom right',
            textfont=dict(size=14, color='black'), hoverinfo='text', name='Solution Location'
        ))

        history = [timestamp_header] + alert_list_items + history
        history = history[:20] #trim to 20 most recent entries
        
        # --- 6. Return alle outputs ---
        return alert_status_message, alert_list_items, history, fig

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

#Ped graph updater
@app.callback(
    [Output('heatmap','figure'),Output('animfig','figure'),Output('plottime', 'children'),Output('vesselmap','figure')],
    Input('graph-update-interval','n_intervals')
)
def update_ped_fig(n):
    nextstep = unique_times[TIME_OFFSET + n % len(unique_times)]
    #print(n,nextstep)
    nextflowdata = flowdata[flowdata['timestamp']==nextstep]
    nextheatdata = heatdata[heatdata['timestamp']==nextstep]
    
    heatfig = heatmap_fig(nextheatdata)
    flowfig = flow_bar(nextflowdata)

    nextshipdata = shipdata[shipdata['upload-timestamp']==nextstep]
    vesselmap = shipmap(nextstep)
    
    return heatfig, flowfig, f"{nextstep}", vesselmap



if __name__ == "__main__":
    app.run_server(debug=False)