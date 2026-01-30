"""Create a small demo dataset for the SingleTree project.

This script initialises a new GeoPackage using the provided schema,
then populates it with a handful of trees, campaigns, measurements
and nested records.  It also generates simple CSV files to serve
as stand‑in point cloud assets (tree packs and ground points).

The resulting database will live in the ``notebooks`` directory
alongside the Jupyter notebooks that demonstrate the library’s
functionality.  You can run this script from the project root
via ``python create_demo_data.py``.  It is idempotent: any
existing demo database will be overwritten.
"""

import json
import os
import sqlite3
import struct
from datetime import datetime


def wkb_point(x: float, y: float) -> bytes:
    """Return a little‑endian WKB Point blob with X and Y coordinates.

    The format is:
    * 1 byte: endianness flag (1 = little endian)
    * 4 bytes: geometry type (1 = 2D Point)
    * 8 bytes: X coordinate as double
    * 8 bytes: Y coordinate as double

    :param x: X coordinate
    :param y: Y coordinate
    :returns: Binary blob suitable for insertion into the ``geom`` column.
    """
    return struct.pack("<BIdd", 1, 1, float(x), float(y))


def main() -> None:
    root_dir = os.path.dirname(os.path.abspath(__file__))
    notebooks_dir = os.path.join(root_dir, "notebooks")
    pc_dir = os.path.join(notebooks_dir, "demo_pointclouds")
    os.makedirs(pc_dir, exist_ok=True)

    # Path to the new GeoPackage
    db_path = os.path.join(notebooks_dir, "demo_data.gpkg")
    # Remove existing file if present
    if os.path.exists(db_path):
        os.remove(db_path)

    # Load schema
    schema_file = os.path.join(root_dir, "geopackage_schema.sql")
    with open(schema_file, "r", encoding="utf-8") as f:
        ddl = f.read()

    # Initialise database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(ddl)

    # Insert campaigns
    campaigns = [
        {
            "campaign_uid": "CAM_FI_2025-01-01_AREA1",
            "source_uid": "FI",
            "acquisition_date": "2025-01-01",
            "area_uid": "Area1",
            "crs_epsg": 3035,
            "semantic_codebook_json": json.dumps({}),
            "dims_json": json.dumps({}),
            "footprint_geom": None,
            "notes": "Field inventory campaign",
        },
        {
            "campaign_uid": "CAM_ULS_2025-01-02_AREA1",
            "source_uid": "ULS",
            "acquisition_date": "2025-01-02",
            "area_uid": "Area1",
            "crs_epsg": 3035,
            "semantic_codebook_json": json.dumps({"1": "ground", "2": "wood", "3": "leaf"}),
            "dims_json": json.dumps({
                "instance_in": "instance_pred",
                "semantic_in": "semantic_pred",
                "score_in": "score",
                "instance_std": "ST_INSTANCE",
                "semantic_std": "ST_SEMANTIC",
                "score_std": "ST_SCORE",
            }),
            "footprint_geom": None,
            "notes": "Uncrewed laser scanning (drone) campaign",
        },
        {
            "campaign_uid": "CAM_HPR_2025-01-03_AREA1",
            "source_uid": "HPR",
            "acquisition_date": "2025-01-03",
            "area_uid": "Area1",
            "crs_epsg": None,
            "semantic_codebook_json": json.dumps({}),
            "dims_json": json.dumps({}),
            "footprint_geom": None,
            "notes": "Harvester production file",
        },
        {
            "campaign_uid": "CAM_CT_2025-01-05_AREA1",
            "source_uid": "CT",
            "acquisition_date": "2025-01-05",
            "area_uid": "Area1",
            "crs_epsg": None,
            "semantic_codebook_json": json.dumps({}),
            "dims_json": json.dumps({}),
            "footprint_geom": None,
            "notes": "CT scanning at sawmill",
        },
    ]
    for camp in campaigns:
        cur.execute(
            "INSERT INTO campaigns (campaign_uid, source_uid, acquisition_date, area_uid, crs_epsg,"
            " semantic_codebook_json, dims_json, footprint_geom, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                camp["campaign_uid"],
                camp["source_uid"],
                camp["acquisition_date"],
                camp["area_uid"],
                camp["crs_epsg"],
                camp["semantic_codebook_json"],
                camp["dims_json"],
                camp["footprint_geom"],
                camp["notes"],
            ),
        )

    # Define some tree positions and attributes
    tree_specs = [
        (
            "T001",
            "1",
            "Area1",
            "PinSyl",
            "alive",
            22.0,
            28.0,
            6.0,
            "2025-01-02",
            3035,
            wkb_point(0.0, 0.0),
            0,
        ),
        (
            "T002",
            "2",
            "Area1",
            "AbiAlb",
            "alive",
            18.0,
            25.0,
            5.0,
            "2025-01-02",
            3035,
            wkb_point(10.0, 0.0),
            0,
        ),
        (
            "T003",
            "3",
            "Area1",
            "PiceAb",
            "alive",
            20.0,
            27.0,
            5.5,
            "2025-01-05",
            3035,
            wkb_point(0.0, 10.0),
            0,
        ),
        (
            "T004",
            "4",
            "Area1",
            "AbiAlb",
            "alive",
            23.0,
            30.0,
            6.2,
            "2025-01-05",
            3035,
            wkb_point(10.0, 10.0),
            0,
        ),
    ]
    cur.executemany(
        "INSERT INTO trees (tree_uid, treeID, source, species_code, status, height_m, dbh_cm,"
        " crown_base_height_m, last_measurement_date, crs_epsg, geom, is_temporary)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tree_specs,
    )

    # Insert measurements for each tree
    measurements = []
    # Field inventory measurement (campaign 1)
    for tree_uid, idx in [("T001", 1), ("T002", 2), ("T003", 3), ("T004", 4)]:
        measurements.append(
            {
                "measurement_uid": f"{tree_uid}_field_2025-01-01",
                "tree_uid": tree_uid,
                "campaign_uid": "CAM_FI_2025-01-01_AREA1",
                "source_type": "field",
                "measurement_date": "2025-01-01",
                "height_m": 20.0 + idx - 1,  # vary height slightly
                "dbh_cm": 25.0 + idx - 1,
                "crown_base_height_m": 5.0 + 0.2 * idx,
                "species_code": tree_specs[idx - 1][3],
                "age": 50 + idx,
                "health": "healthy",
                "machine_id": None,
                "stand_id": "StandA",
                "notes": "Initial field measurement",
                "match_status": "auto",
                "candidate_tree_uid": None,
            }
        )
    # ULS measurement (campaign 2)
    for tree_uid, idx in [("T001", 1), ("T002", 2), ("T003", 3), ("T004", 4)]:
        measurements.append(
            {
                "measurement_uid": f"{tree_uid}_ULS_2025-01-02",
                "tree_uid": tree_uid,
                "campaign_uid": "CAM_ULS_2025-01-02_AREA1",
                "source_type": "ULS",
                "measurement_date": "2025-01-02",
                "height_m": 21.0 + idx - 1,
                "dbh_cm": 26.0 + idx - 1,
                "crown_base_height_m": 5.2 + 0.2 * idx,
                "species_code": tree_specs[idx - 1][3],
                "age": None,
                "health": None,
                "machine_id": None,
                "stand_id": None,
                "notes": "Drone scan",
                "match_status": "auto",
                "candidate_tree_uid": None,
            }
        )
    # CT measurement for T003 (campaign 4)
    measurements.append(
        {
            "measurement_uid": "T003_CT_2025-01-05",
            "tree_uid": "T003",
            "campaign_uid": "CAM_CT_2025-01-05_AREA1",
            "source_type": "CT",
            "measurement_date": "2025-01-05",
            "height_m": None,
            "dbh_cm": None,
            "crown_base_height_m": None,
            "species_code": "PiceAb",
            "age": None,
            "health": None,
            "machine_id": None,
            "stand_id": None,
            "notes": "Sawmill CT scan",
            "match_status": "auto",
            "candidate_tree_uid": None,
        }
    )
    # Insert measurements
    cur.executemany(
        "INSERT INTO measurements (measurement_uid, tree_uid, campaign_uid, source_type,"
        " measurement_date, height_m, dbh_cm, crown_base_height_m, species_code, age, health,"
        " machine_id, stand_id, notes, match_status, candidate_tree_uid)"
        " VALUES (:measurement_uid, :tree_uid, :campaign_uid, :source_type, :measurement_date,"
        " :height_m, :dbh_cm, :crown_base_height_m, :species_code, :age, :health, :machine_id,"
        " :stand_id, :notes, :match_status, :candidate_tree_uid)",
        measurements,
    )

    # Insert nested tables: whorls for field measurement of T001 and T002
    whorls = [
        {"measurement_uid": "T001_field_2025-01-01", "whorl_id": "W1", "height_from_base": 2.0},
        {"measurement_uid": "T001_field_2025-01-01", "whorl_id": "W2", "height_from_base": 4.5},
        {"measurement_uid": "T002_field_2025-01-01", "whorl_id": "W1", "height_from_base": 1.8},
        {"measurement_uid": "T002_field_2025-01-01", "whorl_id": "W2", "height_from_base": 3.5},
    ]
    # Table names in the GeoPackage schema are lower‑case (whorls), so use the correct case
    cur.executemany(
        "INSERT INTO whorls (measurement_uid, whorl_id, height_from_base_m) VALUES (?, ?, ?)",
        [(r["measurement_uid"], r["whorl_id"], r["height_from_base"]) for r in whorls],
    )

    # Insert CT metrics for CT measurement of T003
    ct_metrics = [
        {
            "measurement_uid": "T003_CT_2025-01-05",
            "metric_id": "m1",
            "knot_count": 5,
            "max_knot_diameter_cm": 4.0,
            "mean_ring_width_mm": 1.8,
            "density_kg_m3": 550.0,
            "description": "Example CT metrics",
        }
    ]
    # Table names in the GeoPackage schema are lower‑case (ct_metrics), so use the correct case
    cur.executemany(
        "INSERT INTO ct_metrics (measurement_uid, metric_id, knot_count, max_knot_diameter_cm,"
        " mean_ring_width_mm, density_kg_m3, description)"
        " VALUES (:measurement_uid, :metric_id, :knot_count, :max_knot_diameter_cm,"
        " :mean_ring_width_mm, :density_kg_m3, :description)",
        ct_metrics,
    )

    # Create simple point cloud CSVs
    # Tree pack: a few points around each tree (x,y,z)
    tree_pack_path = os.path.join(pc_dir, "tree_pack_tile1.csv")
    with open(tree_pack_path, "w", encoding="utf-8") as f:
        f.write("x,y,z,tree_uid\n")
        for uid, (x, y) in [("T001", (0.0, 0.0)), ("T002", (10.0, 0.0)), ("T003", (0.0, 10.0)), ("T004", (10.0, 10.0))]:
            for i in range(5):
                f.write(f"{x + 0.2 * i},{y + 0.2 * i},{1.0 + i}," + uid + "\n")

    # Ground-only: grid of ground points
    ground_path = os.path.join(pc_dir, "ground_only_tile1.csv")
    with open(ground_path, "w", encoding="utf-8") as f:
        f.write("x,y,z\n")
        for x in range(-1, 12, 2):
            for y in range(-1, 12, 2):
                f.write(f"{float(x)},{float(y)},0.0\n")

    # Register assets for the ULS campaign
    assets = [
        {
            "asset_uid": "pc_CAM_ULS_2025-01-02_AREA1_tile1_tree_pack",
            "campaign_uid": "CAM_ULS_2025-01-02_AREA1",
            "tree_uid": None,
            "scope": "tile",
            "pc_role": "tree_pack",
            "asset_type": "pointcloud",
            "format": "CSV",
            "uri": os.path.relpath(tree_pack_path, notebooks_dir),
            "crs_epsg": 3035,
            "point_count": 20,  # 4 trees * 5 points each
            "bytes": os.path.getsize(tree_pack_path),
            "hash": None,
            "created_at": datetime.utcnow().isoformat(),
            "notes": "Demo tree pack CSV",
        },
        {
            "asset_uid": "pc_CAM_ULS_2025-01-02_AREA1_tile1_ground_only",
            "campaign_uid": "CAM_ULS_2025-01-02_AREA1",
            "tree_uid": None,
            "scope": "tile",
            "pc_role": "ground_only",
            "asset_type": "pointcloud",
            "format": "CSV",
            "uri": os.path.relpath(ground_path, notebooks_dir),
            "crs_epsg": 3035,
            "point_count": 36,  # grid 6x6
            "bytes": os.path.getsize(ground_path),
            "hash": None,
            "created_at": datetime.utcnow().isoformat(),
            "notes": "Demo ground points CSV",
        },
    ]
    cur.executemany(
        "INSERT INTO assets (asset_uid, campaign_uid, tree_uid, scope, pc_role, asset_type, format, uri,"
        " crs_epsg, point_count, bytes, hash, created_at, notes)"
        " VALUES (:asset_uid, :campaign_uid, :tree_uid, :scope, :pc_role, :asset_type, :format, :uri,"
        " :crs_epsg, :point_count, :bytes, :hash, :created_at, :notes)",
        assets,
    )

    # Commit and close
    conn.commit()
    conn.close()
    print(f"Demo database created at {db_path}")
    print(f"Tree pack CSV: {tree_pack_path}")
    print(f"Ground points CSV: {ground_path}")


if __name__ == "__main__":
    main()