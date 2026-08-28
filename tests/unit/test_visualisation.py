import networkx as nx
import plotly.graph_objects as go

from echo.visualization import PlotlyGraph


def test_plotlygraph_plot():
    # Arrange
    graph = nx.balanced_tree(3, 3)
    positions = nx.spring_layout(graph)

    # Act
    figure = PlotlyGraph.plot(graph=graph, positions=positions)

    # Assert
    assert isinstance(figure, go.Figure)
