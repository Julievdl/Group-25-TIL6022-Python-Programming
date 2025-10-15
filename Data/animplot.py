import pandas as pd
from dash import Dash, dcc, html, Input, Output
import numpy as np

limit = 70

csvdata = pd.read_csv("SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")
#sensorloc = pd.read_csv("sensor-location.csv", skiprows=1, sep=';'
#                        ,names=['Sensor','Location','LatLong','Width','EffWidth'])

data = (
    csvdata
    .assign(timestamp=lambda data: pd.to_datetime(data["timestamp"], format="%Y-%m-%d %H:%M:%S%z"))
    .sort_values(by="timestamp")
)
#data['x']=np.linspace(1,100,len(data.timestamp))#x location
#data['y']=np.linspace(1,100,len(data.timestamp))#y location
#data = data.iloc[:,70:]
data = data.head(100)

dropcols = ['hour', 'minute', 'day', 'month', 'weekday', 'is_weekend'] #drop columns

for i in dropcols:
    data = data.drop(i,axis=1)

longdata = pd.melt(
    data.iloc[:,:30],
    id_vars=["timestamp"],   # Columns to keep
    var_name="Sensor",       # Name of the new 'variable' column
    value_name="Count"       # Name of the new 'value' column
).sort_values(by=["timestamp","Sensor"])


#print(data)
print(longdata)

import plotly.express as px

fig = px.bar(
    longdata,
    x="Sensor",              # X-axis
    y="Count", 
    color = "Sensor", # Y-axis
    animation_frame="timestamp",  # Convert datetime to string for animation
    animation_group = "Sensor",
    range_y=[0, longdata.Count.max()]  # Y-axis range
)
fig.update_layout(
    barmode = 'group',
    xaxis=dict(
        tickangle=-45,     # optional: rotate labels
        tickfont=dict(size=10)  # smaller font size
    ),
    updatemenus=[{
        'type': 'buttons',
        'buttons': [{
            'method': 'animate',
            'args': [None, {'frame': {'duration': 5000, 'redraw': True},
                            'fromcurrent': True, 'transition': {'duration':3000, 'easing': 'linear'}}]
        }]
    }]
)


fig.show()