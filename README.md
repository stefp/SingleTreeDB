# 😊 SingleTree Project

Welcome to **SingleTree** – a practical, extensible database and Python API for working with tree‑level forest data.  This project provides tools to ingest, manage and analyse single‑tree measurements from a variety of sources (field inventories, terrestrial and airborne LiDAR, harvesters, CT scanners, etc.) and exchange them as self‑contained data bundles.

## 🌲 Overview

The core of SingleTree is a set of **schemas** (see `SPEC.md`) that formalise how trees, measurements, campaigns and assets are stored in a GeoPackage database.  The accompanying Python package (`singletree/`) implements:

- **Importers** for LiDAR (`lidar.py`), StanForD harvester files (`harvester_hpr.py`) and generic measurements (`measurement.py`) with matching logic to link new measurements to existing trees (or create temporary tree IDs when ambiguous).
- **Spatial queries** to select trees by bounding box or polygon.
- **Point‑cloud handling** for “Mode A2” tree packs, including import and campaign‑wide merging.
- **Harvester integration** using your Python port of *optBuck* to extract stems, logs, stem profiles and price matrices.

To help you get started quickly, a **demo dataset** generator script (`create_demo_data.py`) and several **Jupyter notebooks** are provided under the `notebooks/` directory.  These notebooks showcase typical workflows: importing data, matching measurements, querying by polygon, merging point clouds and retrieving nested tables.

## ⚙️ Installation & Setup

1. **Clone** this repository and navigate into it:

   ```bash
   git clone <repository-url>
   cd singletree
   ```

2. Create a Python environment (Python 3.10 or later recommended) and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   > **Note:** the project depends on [laspy](https://laspy.readthedocs.io) for LAS/LAZ point‑cloud operations and [sqlite3](https://docs.python.org/3/library/sqlite3.html) for database access.  To read StanForD 2010 harvest data you’ll also need your Python *optBuck* package available on `PYTHONPATH`.

3. **Generate a dataset** (optional).  To create the demonstration GeoPackage and dummy point clouds, run the script:

   ```bash
   python create_demo_data.py
   ```

   This will populate `notebooks/demo_data.gpkg` and write example tree packs in `notebooks/demo_pointclouds/`.

4. **Open the notebooks**.  The notebooks live in `notebooks/` and can be run with Jupyter Lab or VSCode.  To launch Jupyter Lab:

   ```bash
   pip install jupyterlab
   jupyter lab
   ```

## 📓 Example Notebooks

Three notebooks illustrate key SingleTree features:

| Notebook | Description |
|---|---|
| [`01_import_data.ipynb`]({{file:file-KSGZsNmMmYXtVE41L3AwPs}}) | Generates a demo dataset, previews basic tables, imports LiDAR and harvester data and shows how to attach CT measurements. |
| [`02_matching_and_query.ipynb`]({{file:file-3UdSGHB9vRfkEb7Pg2Mwgd}}) | Demonstrates measurement matching using tree attributes and coordinates, then shows how to query trees by measurement type or spatial polygon. |
| [`03_merge_and_retrieve.ipynb`]({{file:file-BVcJWwebj5zKSTW9tQNcQE}}) | Explains campaign‑wide tree‑pack merging (conceptually) and retrieves nested tables like whorls and CT metrics. |

The demo notebooks include synthetic data and decorative images to make them visually appealing.  Feel free to adapt them for your own datasets.

## 🧑‍💻 Basic Usage

Below is a short example using the Python API.  See the notebooks for more comprehensive walkthroughs.

```python
from singletree import ingest, query, pointcloud, matching

# 1. Load or create a SingleTree dataset (GeoPackage)
dataset_path = "notebooks/demo_data.gpkg"

# 2. Import a new measurement (field inventory) and match to existing trees
raw_measurement = {
    "tree_uid": None,
    "measurement_uid": "FI_2026-01-01_Example",
    "source_type": "Field",
    "date": "2026-01-01",
    "dbh_cm": 30.5,
    "height_m": 25.0,
    "species": "Picea abies",
    "pos_x": 478100.0,
    "pos_y": 5429110.0,
}

# Using MatchConfig to set tolerances
config = matching.MatchConfig(distance_threshold=2.0,
                              dbh_tolerance=5.0,
                              height_tolerance=2.0,
                              species_required=True)

measurement_record, temp_tree_record = ingest.measurement.import_measurement(
    raw_measurement, existing_trees=[...], config=config
)

# 3. Query trees by polygon
polygon = [(478068.0, 5429105.0), (478090.0, 5429105.0), (478090.0, 5429120.0), (478068.0, 5429120.0)]
trees_in_poly = query.query_trees_by_polygon(dataset_path, polygon)

# 4. Merge tree packs for a campaign (tree-only and optionally ground points)
asset_metadata = pointcloud.merge.merge_campaign_tree_packs(
    campaign_root="notebooks/demo_pointclouds",
    campaign_uid="ExampleCampaign",
    include_ground=True
)

print(asset_metadata)
```

For more advanced operations—such as importing StanForD harvester files or retrieving nested tables like whorls, logs and CT metrics—see the provided notebooks and the API docs in the source code.

## 🙏 Contributing & License

This project is an open, collaborative effort.  Issues and pull requests are welcome!  Please see the `CONTRIBUTING.md` file for guidelines.  SingleTree is released under the MIT License.

Enjoy your tree data journey! 🌳