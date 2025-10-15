import pandas as pd
from dash import Dash, dcc, html
from animplot import fig as animfig

csvdata = pd.read_csv("SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")
print(csvdata.columns)
data = (
    csvdata
    .assign(timestamp=lambda data: pd.to_datetime(data["timestamp"], format="%Y-%m-%d %H:%M:%S%z"))
    .sort_values(by="timestamp")
)

Dataseries = []
for col in data.columns[1:]:
    Dataseries.append(col) 

app = Dash(__name__)

app.layout = html.Div(
    children=[
        html.H1(children="Pedestrian Analytics"),
        html.P(
            children=(
                "Pedestrians measured"
                " during SAIL 2025"
            ),
        ),
         html.Img(
            src="/assets/sensormap.png",  # path relative to the Dash server
            style={"width": "800px", "height": "auto"}  # optional styling
        ),
        dcc.Graph(
            figure={
                "data": [
                     {"x": data["timestamp"], "y": data[col], "type": "lines", "name": col} 
                for col in data.columns[1:]
                ],
                "layout": {"title": "Pedestrians across this sensor"},
            },
        ),
        dcc.Graph(
            figure={
                "data": [
                    {
                        "x": data["timestamp"],
                        "y": data["CMSA-GAKH-01_180"],
                        "type": "lines",
                    },
                ],
                "layout": {"title": "Pedestrian count"},
            },
        ),
        dcc.Graph(
            figure=animfig
        ),
    ]
)

if __name__ == "__main__":
    app.run_server(debug=True)