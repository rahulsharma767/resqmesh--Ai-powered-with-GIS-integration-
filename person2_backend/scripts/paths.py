"""
Central path configuration. Every script imports from here instead of
hardcoding absolute paths, so the project runs correctly wherever it's
unzipped -- not just in the original sandbox.

Layout expected under PROJECT_ROOT (create data/raw/ yourself and drop the
3 original source files in it -- they're too large to ship in the zip):

  resqmesh/
    data/
      raw/
        hospital_directory.csv
        western-zone-260822.osm.pbf
        mumbai_ward_boundary.geojson.json
      processed/      (created by the pipeline)
      simulation/      (created by the pipeline)
      cache/           (created by the pipeline)
    scripts/
    backend/
    tests/
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAW_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw')
PROCESSED_DIR = os.path.join(PROJECT_ROOT, 'data', 'processed')
SIMULATION_DIR = os.path.join(PROJECT_ROOT, 'data', 'simulation')
CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'cache')

# Raw source files (place your 3 original uploads here)
HOSPITAL_CSV_RAW = os.path.join(RAW_DIR, 'hospital_directory.csv')
WARD_BOUNDARY_RAW = os.path.join(RAW_DIR, 'mumbai_ward_boundary.geojson.json')
OSM_PBF_RAW = os.path.join(RAW_DIR, 'western-zone-260822.osm.pbf')

# Cache (intermediate, regeneratable)
NODES_BBOX_CACHE = os.path.join(CACHE_DIR, 'mumbai_bbox_nodes.csv')
WAYS_CACHE = os.path.join(CACHE_DIR, 'mumbai_ways.csv')
MISSING_NODE_IDS_CACHE = os.path.join(CACHE_DIR, 'missing_node_ids.txt')

# Processed (final clean outputs)
MUMBAI_WARDS_GEOJSON = os.path.join(PROCESSED_DIR, 'mumbai_wards.geojson')
MUMBAI_BOUNDARY_GEOJSON = os.path.join(PROCESSED_DIR, 'mumbai_boundary.geojson')
MUMBAI_HOSPITALS_CSV = os.path.join(PROCESSED_DIR, 'mumbai_hospitals.csv')
MUMBAI_HOSPITALS_REPORT = os.path.join(PROCESSED_DIR, 'mumbai_hospitals_report.txt')
ROAD_NODES_CSV = os.path.join(PROCESSED_DIR, 'mumbai_road_nodes.csv')
ROAD_EDGES_CSV = os.path.join(PROCESSED_DIR, 'mumbai_road_edges.csv')
ROAD_GRAPH_PKL = os.path.join(PROCESSED_DIR, 'mumbai_road_graph.pkl')
HOSPITAL_NEAREST_NODE_CSV = os.path.join(PROCESSED_DIR, 'hospital_nearest_node.csv')

# Simulation (synthetic, clearly labeled)
AMBULANCES_CSV = os.path.join(SIMULATION_DIR, 'ambulances.csv')
HOSPITAL_STATE_CSV = os.path.join(SIMULATION_DIR, 'hospital_state.csv')


def ensure_dirs():
    for d in (RAW_DIR, PROCESSED_DIR, SIMULATION_DIR, CACHE_DIR):
        os.makedirs(d, exist_ok=True)
