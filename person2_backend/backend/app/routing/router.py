"""
Part 11 -- Routing engine.

Loads the cached road graph once (module-level singleton) and exposes
find_route(origin_node, dest_node) -> route dict with distance, duration,
coordinates, and the node/edge path used.

Uses networkx's A* implementation with an admissible haversine-based time
heuristic: the heuristic estimates remaining travel time as
(straight_line_distance_km / MAX_PLAUSIBLE_SPEED_KPH) * 60, using the fastest
road class's speed as MAX_PLAUSIBLE_SPEED_KPH (80 km/h, the motorway default
from build_graph.py). Since no real edge can be traveled faster than that,
this heuristic never overestimates true remaining time -> A* stays optimal.

Falls back to Dijkstra (nx.shortest_path with weight='travel_time_min') if
A* fails to find a path (e.g. disconnected components) so the caller always
gets a clear "no route" result rather than a silent crash.
"""
import math
import os
import sys
import pickle
import time
import networkx as nx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'scripts'))
from paths import ROAD_GRAPH_PKL as GRAPH_PKL  # noqa: E402

MAX_PLAUSIBLE_SPEED_KPH = 80.0

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        t0 = time.time()
        if os.path.exists(GRAPH_PKL):
            with open(GRAPH_PKL, 'rb') as f:
                _graph = pickle.load(f)
            print(f"[routing] Loaded cached graph: {_graph.number_of_nodes()} nodes, "
                  f"{_graph.number_of_edges()} edges in {time.time()-t0:.1f}s")
        else:
            # Git-friendly fallback: the processed node/edge CSVs are portable
            # and regenerable; build_graph/cache_graph can also be run manually.
            # This keeps a clone functional even when the 138MB pickle is not
            # checked into source control.
            import csv
            from paths import ROAD_NODES_CSV, ROAD_EDGES_CSV
            print("[routing] Graph pickle missing; building NetworkX graph from processed CSVs...", flush=True)
            G = nx.DiGraph()
            with open(ROAD_NODES_CSV, encoding='utf-8') as f:
                reader = csv.reader(f); next(reader)
                for row in reader:
                    G.add_node(int(row[0]), lat=float(row[1]), lon=float(row[2]))
            with open(ROAD_EDGES_CSV, encoding='utf-8') as f:
                reader = csv.reader(f); next(reader)
                for row in reader:
                    G.add_edge(int(row[0]), int(row[1]), length_m=float(row[2]), speed_kph=float(row[3]),
                               travel_time_min=float(row[4]), highway=row[5], name=row[6],
                               way_id=row[7], oneway_flag=row[8])
            _graph = G
            print(f"[routing] Built graph: {_graph.number_of_nodes()} nodes, "
                  f"{_graph.number_of_edges()} edges in {time.time()-t0:.1f}s", flush=True)
    return _graph


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _time_heuristic(G):
    def h(u, v):
        lat1, lon1 = G.nodes[u]['lat'], G.nodes[u]['lon']
        lat2, lon2 = G.nodes[v]['lat'], G.nodes[v]['lon']
        dist_km = haversine_km(lat1, lon1, lat2, lon2)
        return (dist_km / MAX_PLAUSIBLE_SPEED_KPH) * 60.0  # minutes
    return h


def find_route(origin_node, dest_node, G=None):
    """
    Returns:
      {
        'found': bool,
        'distance_km': float,
        'duration_minutes': float,
        'coordinates': [[lon, lat], ...],
        'node_path': [node_id, ...],
        'edge_count': int,
        'origin_node': origin_node,
        'dest_node': dest_node,
      }
    """
    if G is None:
        G = get_graph()

    if origin_node == dest_node:
        lat, lon = G.nodes[origin_node]['lat'], G.nodes[origin_node]['lon']
        return {
            'found': True, 'distance_km': 0.0, 'duration_minutes': 0.0,
            'coordinates': [[lon, lat]], 'node_path': [origin_node],
            'edge_count': 0, 'origin_node': origin_node, 'dest_node': dest_node,
        }

    try:
        path = nx.astar_path(G, origin_node, dest_node,
                              heuristic=_time_heuristic(G), weight='travel_time_min')
    except nx.NetworkXNoPath:
        return {'found': False, 'distance_km': None, 'duration_minutes': None,
                'coordinates': [], 'node_path': [], 'edge_count': 0,
                'origin_node': origin_node, 'dest_node': dest_node}
    except nx.NodeNotFound as e:
        return {'found': False, 'error': str(e), 'distance_km': None,
                'duration_minutes': None, 'coordinates': [], 'node_path': [],
                'edge_count': 0, 'origin_node': origin_node, 'dest_node': dest_node}

    total_dist_km = 0.0
    total_time_min = 0.0
    coords = []
    for i in range(len(path)):
        n = path[i]
        coords.append([G.nodes[n]['lon'], G.nodes[n]['lat']])
        if i < len(path) - 1:
            edge = G[path[i]][path[i + 1]]
            total_dist_km += edge['length_m'] / 1000.0
            total_time_min += edge['travel_time_min']

    return {
        'found': True,
        'distance_km': round(total_dist_km, 3),
        'duration_minutes': round(total_time_min, 2),
        'coordinates': coords,
        'node_path': path,
        'edge_count': len(path) - 1,
        'origin_node': origin_node,
        'dest_node': dest_node,
    }


def find_route_excluding_edges(origin_node, dest_node, closed_edges, G=None):
    """
    Route while treating a set of (u, v) edges as closed (for Part 13/14
    dynamic re-routing around road closures). Builds a lightweight filtered
    view instead of mutating the shared cached graph.
    """
    if G is None:
        G = get_graph()

    def filter_edge(u, v):
        return (u, v) not in closed_edges

    view = nx.subgraph_view(G, filter_edge=filter_edge)
    return find_route(origin_node, dest_node, G=view)


if __name__ == '__main__':
    # Quick sanity test: route between two real graph nodes
    G = get_graph()
    nodes = list(G.nodes)[:2]
    import random
    random.seed(42)
    a, b = random.sample(list(G.nodes), 2)
    t0 = time.time()
    result = find_route(a, b, G=G)
    dt = time.time() - t0
    print(f"Test route {a} -> {b}: found={result['found']}, "
          f"dist={result['distance_km']}km, time={result['duration_minutes']}min, "
          f"edges={result['edge_count']}, computed in {dt*1000:.0f}ms")
