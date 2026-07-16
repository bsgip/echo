from collections.abc import Callable
from enum import StrEnum, auto
from typing import Any

import networkx as nx
import plotly.graph_objects as go

DEFAULT_NODE_NAME = "node"
DEFAULT_NODE_SIZE = 15
DEFAULT_NODE_COLOR = "#888"
DEFAULT_NODE_HOVER_TEXT = ""
DEFAULT_EDGE_TEXT = ""
DEFAULT_EDGE_HOVER_TEXT = ""


class VizNodeType(StrEnum):
    Bus = auto()
    Line = auto()
    Grid = auto()
    Transformer = auto()
    Load = auto()
    Solar = auto()
    ElectricalLoad = auto()
    EV = auto()
    Battery = auto()
    Inverter = auto()
    ConnectionPoint = auto()
    HeatPump = auto()
    ParameterisedHeatPump = auto()
    Chiller = auto()
    ParameterisedChiller = auto()
    ThermalDistribution = auto()
    ThermalTellegen = auto()
    ThermalStorage = auto()
    HeatAggregationNode = auto()
    HeatingDemand = auto()
    CoolingDemand = auto()
    MultiCommodityBus = auto()
    PartitionedMultiCommodityBus = auto()
    GasGrid = auto()
    Boiler = auto()


COLOR_BY_NODE_TYPE = {
    VizNodeType.Bus: "darkslategrey",
    VizNodeType.Line: "darkslategrey",
    VizNodeType.Grid: "hotpink",
    VizNodeType.Transformer: "blueviolet",
    VizNodeType.Load: "forestgreen",
    VizNodeType.Solar: "orange",
    VizNodeType.EV: "orangered",
    VizNodeType.Battery: "lightblue",
    VizNodeType.Inverter: "lightgreen",
    VizNodeType.ConnectionPoint: "mediumblue",
    VizNodeType.HeatPump: "tomato",
    VizNodeType.ParameterisedHeatPump: "tomato",
    VizNodeType.Chiller: "cornflowerblue",
    VizNodeType.ParameterisedChiller: "cornflowerblue",
    VizNodeType.ThermalDistribution: "goldenrod",
    VizNodeType.ThermalTellegen: "chocolate",
    VizNodeType.ThermalStorage: "firebrick",
    VizNodeType.HeatAggregationNode: "firebrick",
    VizNodeType.HeatingDemand: "crimson",
    VizNodeType.CoolingDemand: "steelblue",
    VizNodeType.MultiCommodityBus: "darkblue",
    VizNodeType.PartitionedMultiCommodityBus: "lightseagreen",
    VizNodeType.GasGrid: "pink",
    VizNodeType.Boiler: "firebrick",
}

SIZE_BY_NODE_TYPE = {
    VizNodeType.Bus: 10,
    VizNodeType.Line: 10,
    VizNodeType.Grid: 30,
    VizNodeType.Transformer: 25,
    VizNodeType.Load: 15,
    VizNodeType.ElectricalLoad: 15,
    VizNodeType.Solar: 15,
    VizNodeType.EV: 15,
    VizNodeType.Battery: 15,
    VizNodeType.Inverter: 15,
    VizNodeType.ConnectionPoint: 20,
    VizNodeType.HeatPump: 15,
    VizNodeType.ParameterisedHeatPump: 15,
    VizNodeType.Chiller: 15,
    VizNodeType.ParameterisedChiller: 15,
    VizNodeType.ThermalDistribution: 15,
    VizNodeType.ThermalTellegen: 15,
    VizNodeType.ThermalStorage: 15,
    VizNodeType.HeatAggregationNode: 15,
    VizNodeType.HeatingDemand: 15,
    VizNodeType.CoolingDemand: 15,
    VizNodeType.MultiCommodityBus: 20,
    VizNodeType.PartitionedMultiCommodityBus: 20,
    VizNodeType.GasGrid: 30,
    VizNodeType.Boiler: 15,
}

ECHO_NODE_TO_VIZ_NODE = {
    "thermal_storage": VizNodeType.ThermalStorage,
    "thermal_load": VizNodeType.HeatingDemand,
    "thermal_supply": VizNodeType.ThermalDistribution,
    "conn_point": VizNodeType.ThermalTellegen,
}


def echo_node_color(node: str, *args) -> str:  # noqa ANN002
    if node in ECHO_NODE_TO_VIZ_NODE:
        return COLOR_BY_NODE_TYPE[ECHO_NODE_TO_VIZ_NODE[node]]
    return DEFAULT_NODE_COLOR


def echo_node_size(node: str, *args) -> int:  # noqa ANN002
    if node in ECHO_NODE_TO_VIZ_NODE:
        return SIZE_BY_NODE_TYPE[ECHO_NODE_TO_VIZ_NODE[node]]
    return DEFAULT_NODE_SIZE


def echo_node_text(node: str, *args) -> str:  # noqa ANN002
    return node


def echo_edge_text(edge: tuple, *args) -> str:  # noqa ANN002
    return str(edge)


class PlotlyGraph:
    @staticmethod
    def plot(
        graph: nx.graph.Graph,
        positions: dict,
        node_text: Callable[[Any, Any], str] | None = lambda *args: DEFAULT_NODE_NAME,
        node_size: Callable[[Any, Any], int] = lambda *args: DEFAULT_NODE_SIZE,
        node_color: Callable[[Any, Any], str] = lambda *args: DEFAULT_NODE_COLOR,
        node_hover_text: Callable[[Any, Any], str] | None = lambda *args: DEFAULT_NODE_HOVER_TEXT,
        edge_text: Callable[[Any], str] | None = lambda *args: DEFAULT_EDGE_TEXT,
        edge_hover_text: Callable[[Any], str] | None = lambda *args: DEFAULT_EDGE_HOVER_TEXT,
        title: str | None = None,
        add_legend: bool = False,
        show_node_names: bool = False,
        color_connection_point_type: bool = False,
        template: str = "plotly_white",
    ) -> go.Figure:

        # Build edge trace
        edge_x = []
        edge_y = []
        mid_edge_x = []
        mid_edge_y = []
        _edge_hover_text = []
        _edge_text = []
        for edge in graph.edges():
            x0, y0 = positions[edge[0]]
            x1, y1 = positions[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            mid_edge_x.append((x0 + x1) / 2)
            mid_edge_y.append((y0 + y1) / 2)
            if edge_hover_text:
                _edge_hover_text.append(edge_hover_text(edge))
            if edge_text:
                _edge_text.append(edge_text(edge))

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            line=dict(width=0.5, color="#888"),
            hoverinfo="none",
            mode="lines",
            showlegend=False,
        )

        mid_edge_trace = go.Scatter(
            x=mid_edge_x,
            y=mid_edge_y,
            mode="markers+text" if _edge_text else "markers",
            hoverinfo="text" if _edge_hover_text else "none",
            hovertext=_edge_hover_text,
            text=_edge_text,
            showlegend=False,
            # marker=dict(size=DEFAULT_NODE_SIZE, opacity=0),
            marker=dict(size=DEFAULT_NODE_SIZE, color=DEFAULT_NODE_COLOR),
        )

        # Build node trace
        node_x = []
        node_y = []
        _node_text = []
        node_sizes = []
        node_colors = []
        _node_hover_text = []
        for node, val in graph.nodes.items():
            x, y = positions[node]
            node_x.append(x)
            node_y.append(y)
            if node_text:
                _node_text.append(node_text(node, val))
            if node_hover_text:
                _node_hover_text.append(node_hover_text(node, val))
            node_colors.append(node_color(node, val))
            node_sizes.append(node_size(node, val))
        node_trace = go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text" if _node_text else "markers",
            hoverinfo="text" if _node_hover_text else "none",
            hovertext=_node_hover_text,
            text=_node_text,
            showlegend=False,
            marker=dict(reversescale=True, color=node_colors, size=node_sizes, line_width=2),
        )

        trace_data = [edge_trace, mid_edge_trace, node_trace]
        fig = go.Figure(
            data=trace_data,
            layout=go.Layout(
                title=graph.name,
                titlefont_size=28,
                showlegend=True,
                hovermode="closest",
                margin=dict(b=20, l=5, r=5, t=40),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                template=template,
            ),
        )
        if title:
            fig.update_layout(title=dict(text=title, font=dict(size=20)))
        return fig
