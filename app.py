import pandas as pd
from dash import Dash, dcc, html, callback, Output, Input
from animplot import fig as animfig
from Data.heat_map import figheat as heatmap
from datetime import datetime


#import data
csvdata = pd.read_csv("Data/SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")
#print(csvdata.columns)

#convert to datetime
data = (
    csvdata
    .assign(timestamp=lambda data: pd.to_datetime(data["timestamp"], format="%Y-%m-%d %H:%M:%S%z"))
    .sort_values(by="timestamp")
)

#column names
Dataseries = []
for col in data.columns[1:]:
    Dataseries.append(col) 

app = Dash(__name__)

app.layout = html.Div([
    
    #Container for main content and sidebar
    html.Div([
    
    #Sidebar
    html.Div([
        #Title
        html.H1('Traffic Dashboard'), 
        
        #Clock
        html.H2('Clock'),
        html.Div(id='live-time',style={"fontSize": "40px", "fontWeight": "bold"}),
        dcc.Interval(
        id='interval-component',
        interval=1000,  # 1000ms = 1 second
        n_intervals=0
            ),
        
        #Alerts section
            html.H3('Alerts:'),
            html.P("Some controls or summary info here"),
            dcc.Checklist(
                options=[
                    {"label": "Option 1", "value": 1},
                    {"label": "Option 2", "value": 2}
                ],
                value=[1]
            )
        ], 
             #Sidebar style
             style={
            "position": "sticky",
            "top": "20px",
            "width": "250px",
            "height": "100vh",
            "background-color": "#f8f9fa",
            "padding": "20px",
            "overflow": "auto"  # scroll inside sidebar if needed
        }),

    #Main content
    html.Div([
    dcc.Tabs(id="tabs-dash", value='area-overview', children=[
        dcc.Tab(label='Area Overview', value='area-overview', children=[
            html.Div([
            #html.H3('Area Overview'),
            html.Img(
            src="/assets/sensormap.png",  # path relative to the Dash server
            style={"width": "700px", "height": "auto"}  # optional styling
            )
            ],style={'padding':'20px'})
        ]),
        dcc.Tab(label='Pedestrian Overview', value='ped-overview', children=[
            html.Div([
            #html.H3('Pedestrian Traffic'),
            dcc.Graph(
            figure=heatmap
            ),
            dcc.Graph(
            figure=animfig
            )
            ],style={'padding':'20px'})
        ]),
        dcc.Tab(label='Car Traffic Overview (slow loading +/- 30s)', value='car-overview', children=[
            html.Div([
        html.Iframe(
        id='car-map',
        src="/assets/verkeerskaart_amsterdam_definitief.html",
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

@app.callback(
    Output('live-time', 'children'),
    Input('interval-component', 'n_intervals')
)
def update_time(n):
    now = datetime.now().strftime("%H:%M:%S")
    return f"{now}"

@app.callback(
    Output('car-map','style'),
    Input('tabs-dash','value')
)
def show_car_map(tab):
    if tab == 'car-overview':
        return {"width": "100%", "height": "600px", "border": "none", "display": "block"}
    return {"display":"none"}

if __name__ == "__main__":
    app.run_server(debug=True)