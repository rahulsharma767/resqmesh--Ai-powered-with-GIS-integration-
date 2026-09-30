"""
Dynamic road-closure state for ResQMesh.

Road closures are stored as directed graph edges (u, v).
The underlying cached graph is never modified.
"""

from router import find_route_excluding_edges


_closed_edges = set()


def close_edge(u, v):
    """Close a directed road edge."""
    edge = (int(u), int(v))
    _closed_edges.add(edge)
    return edge


def reopen_edge(u, v):
    """Reopen a previously closed directed road edge."""
    edge = (int(u), int(v))
    _closed_edges.discard(edge)
    return edge


def list_closed_edges():
    """Return all currently closed directed edges."""
    return sorted(_closed_edges)


def clear_closures():
    """Remove all active road closures."""
    _closed_edges.clear()


def reroute(origin_node, destination_node):
    """
    Find a route while avoiding all currently closed edges.
    """
    return find_route_excluding_edges(
        int(origin_node),
        int(destination_node),
        _closed_edges,
    )