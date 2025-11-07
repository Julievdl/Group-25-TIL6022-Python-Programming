import pandas as pd
from dash import Dash, dcc, html, Input, Output
import numpy as np

from python_files.data_combining import df_long as flowdata

limit = 70
maxflow = flowdata['flow'].max()
#import data
csvdata = pd.read_csv("Data/SAIL2025_LVMA_data_3min_20August-25August2025_flow.csv")

#transform data
data = (
    csvdata
    .assign(timestamp=lambda data: pd.to_datetime(data["timestamp"], format="%Y-%m-%d %H:%M:%S%z"))
    .sort_values(by="timestamp")
)


#drop unneccessary columns
dropcols = ['hour', 'minute', 'day', 'month', 'weekday', 'is_weekend'] 

for i in dropcols:
    data = data.drop(i,axis=1)

#transform into longdata format for plotting(currently only)
longdata = pd.melt(
    data.iloc[:,:10],
    id_vars=["timestamp"],   # Columns to keep
    var_name="Sensor",       # Name of the new 'variable' column
    value_name="Count"       # Name of the new 'value' column
).sort_values(by=["timestamp","Sensor"])




#plot bar plot with animation over time
import plotly.express as px
flowdata=flowdata.head(3000)

fig = px.bar(
    flowdata,
    x="sensor_direction",              # X-axis
    y="flow", 
    color = "sensor_direction", # Y-axis
    animation_frame="timestamp",  # Convert datetime to string for animation
    animation_group = "sensor_direction",
    range_y=[0, flowdata.flow.max()]  # Y-axis range
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
            'args': [None, {'frame': {'duration': 4000, 'redraw': True},
                            'fromcurrent': True, 'transition': {'duration':3000, 'easing': 'linear'}}]
        }]
    }]
)

def flow_bar(data):
    fig = px.bar(
        data,
        x="sensor_direction",              # X-axis
        y="flow", 
        color = "sensor_direction", # Y-axis
        range_y=[0, maxflow]  # Y-axis range
    )
    fig.update_layout(
        barmode = 'group',
        xaxis=dict(
            tickangle=-45,     # optional: rotate labels
            tickfont=dict(size=10)  # smaller font size
        )
    )
    
    return fig

