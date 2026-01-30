# SingleTree Data Model Specification

## Overview

The **SingleTree** project defines an open and extensible data model for managing and exchanging
tree‑level information throughout the forest value chain – from inventory and management
through harvesting and sawmill processing.  The goal is to standardise how single trees and their
derived measurements are represented, while remaining flexible enough to incorporate new
measurement modalities and nested data structures as they emerge.

This specification describes the **conceptual schema**, the **core entities** and their
relationships, and outlines how this schema is realised in a **GeoPackage** (SQLite) physical
database.  The model is intentionally designed to support both file‑based exchange bundles
(Option 1) and a single embedded database (Option 2).  The latter serves as the primary
canonical store for large data volumes and underpins the vector‑tiles server for web
visualisation.

### Design principles

* **Tree‑centric:** The model revolves around a single physical tree (`Tree` entity), which can
  have multiple measurements over time and from different sources.  All nested tables and
  assets ultimately link back to a tree.
* **Extensibility:** Measurement types and nested tables are open‑ended.  Partners can add
  new measurement types or additional fields without breaking existing data.
* **Separation of concerns:** High‑level tree metadata remains in a lightweight table to
  support efficient map rendering and spatial queries, while detailed measurement data and
  large point clouds are stored in separate tables/files.
* **Provenance and versioning:** Every record contains provenance fields (source, date, creator,
  algorithm version) to track lineage.  The dataset and schema carry version tags.
* **Unique identifiers:** Globally unique identifiers (UIDs) link trees, measurements,
  campaigns, assets, logs and other nested records.  UIDs are stable and human‑readable
  wherever possible.

### Coordinate reference systems (CRS)

Tree geometries are stored in a projected CRS appropriate for the region (e.g. ETRS89 / LAEA
Europe `EPSG:3035` or a national UTM zone).  A `crs_epsg` column accompanies each geometry
column.  When exporting to GeoJSON, coordinates may be reprojected to WGS84 (EPSG:4326) for
interoperability; however, the canonical storage in GeoPackage uses a projected CRS.

## Core entities

### 1. Tree

Represents a single physical tree, alive or harvested.  It is the root entity for all
information about that tree.

| Column          | Type      | Description |
|-----------------|-----------|-------------|
| `tree_uid`      | TEXT PK   | **Global unique identifier** for the tree.  Recommended format:
  `<site_code>_<local_tree_id>`, e.g. `SCAstand1_1`.  Immutable. |
| `treeID`        | TEXT      | Local tree number within a stand or inventory, as supplied by the
  original data source. |
| `source`        | TEXT      | Name or code of the inventory/stand/project that provided the tree.
  Often corresponds to a stand ID or data collection campaign. |
| `species_code`  | TEXT      | Species code, following the partner’s preferred taxonomy (e.g.
  `AbiAlb` for *Abies alba*).  Latin binomials or numeric codes may also be stored. |
| `status`        | TEXT      | Tree status (`alive`, `harvested`, `dead`, etc.). |
| `height_m`      | REAL      | Latest measured/estimated total height in metres (optional). |
| `dbh_cm`        | REAL      | Latest measured/estimated diameter at breast height in centimetres
  (optional). |
| `crown_base_height_m` | REAL | Latest measured crown base height (optional). |
| `geometry`      | POINT Z   | 3D point representing the tree’s location.  Stored in projected
  CRS. |
| `crs_epsg`      | INTEGER   | EPSG code of the geometry column. |
| `last_measurement_date` | DATE | Date of the most recent measurement event (optional). |

**Relationships:**

* One `Tree` can have **many** `Measurement` records.
* One `Tree` can have **many** `Asset` records (point clouds, images, etc.).

### 2. Campaign

Defines a data acquisition campaign (e.g. a mobile laser scanning survey, an ALS flight or a
drone mission) from which many tree measurements are derived.  Campaigns allow grouping
assets and measurements by a common sensor, date and area.

| Column              | Type     | Description |
|---------------------|----------|-------------|
| `campaign_uid`      | TEXT PK  | Unique identifier for the campaign (e.g.
  `MLS_VENDORX_2025-06-01_STAND123`). |
| `source_uid`        | TEXT     | Identifier of the platform/sensor used (e.g. `MLS_VENDORX`). |
| `acquisition_date`  | DATE     | Date of the data collection. |
| `area_uid`          | TEXT     | Identifier for the stand, tile, or region covered. |
| `crs_epsg`          | INTEGER  | EPSG code used for coordinates in this campaign. |
| `semantic_codebook_json` | TEXT | JSON mapping of semantic class codes to names (e.g.
  `{ "1": "ground", "2": "wood", "3": "leaf" }`). |
| `dims_json`         | TEXT     | JSON describing how instance and semantic fields are mapped in
  point cloud files.  Contains keys: `instance_in`, `semantic_in`, `score_in`,
  `instance_std`, `semantic_std`, `score_std`. |
| `footprint_geom`    | POLYGON  | Optional polygon representing the spatial footprint of the
  campaign. |
| `notes`             | TEXT     | Additional information, such as processing software or operator. |

**Relationships:**

* One `Campaign` can produce **many** `Measurement` records.
* One `Campaign` can have **many** `Asset` records of type `tree_pack`, `ground_only`,
  `background_residual` or `full_scene`.

### 3. Measurement

Represents a data capture event or derived set of attributes for a single tree at a specific
time.  Measurements can come from field surveys, TLS/MLS/ALS/ULS scans, harvester logs,
sawmill CT scans, etc.

| Column              | Type      | Description |
|---------------------|-----------|-------------|
| `measurement_uid`   | TEXT PK   | Unique ID for this measurement, typically
  `tree_uid_source_type_date` (e.g. `SCAstand1_1_TLS_2019-06-04`). |
| `tree_uid`          | TEXT FK   | Identifier of the tree being measured. |
| `campaign_uid`      | TEXT FK   | Campaign from which this measurement originates (nullable). |
| `source_type`       | TEXT      | Type of measurement (`field`, `TLS`, `ALS`, `ULS`, `harvester`,
  `CT`, etc.). |
| `measurement_date`  | DATE      | Date (and optionally time) of measurement. |
| `height_m`          | REAL      | Tree height measured by this event (optional). |
| `dbh_cm`            | REAL      | DBH measured by this event (optional). |
| `crown_base_height_m` | REAL    | Crown base height measured by this event (optional). |
| `species_code`      | TEXT      | Species as determined by this measurement (optional). |
| `age`               | INTEGER   | Tree age (if available). |
| `health`            | TEXT      | Health status (e.g. `healthy`, `dead`). |
| `machine_id`        | TEXT      | For harvester measurements: ID of the machine. |
| `stand_id`          | TEXT      | Stand ID or plot ID (if applicable). |
| `notes`             | TEXT      | Additional notes, including algorithm version or operator. |

**Relationships:**

* One `Measurement` can have **many** nested table records, depending on its `source_type`.
* `measurement_uid` is referenced by nested tables such as `Whorl`, `StemTaper`, `Defect`,
  `QSMCylinder`, `CrownPolygon`, `HarvesterLog`, `StemProfile`, `PriceMatrix`, etc.

### 4. Asset

Represents a file or resource associated with a tree or campaign, such as point clouds,
photos, CT scans, or raw harvester XML files.  Assets are not stored directly in the
GeoPackage; instead, a `uri` points to the file on disk or on remote storage.

| Column          | Type     | Description |
|-----------------|----------|-------------|
| `asset_uid`     | TEXT PK  | Unique identifier for the asset. |
| `campaign_uid`  | TEXT FK  | Campaign that produced the asset (nullable for tree‑level assets). |
| `tree_uid`      | TEXT FK  | Tree to which this asset relates (nullable for campaign‑level). |
| `scope`         | TEXT     | Context of the asset: `campaign`, `tile`, `tree`, `area`. |
| `pc_role`       | TEXT     | Role of the point cloud: `tree_pack`, `ground_only`,
  `background_residual`, `full_scene`, `merged`, `tree_subset`, etc.  Non‑point cloud assets
  can set this to `none` or `other`. |
| `asset_type`    | TEXT     | Type of data: `pointcloud`, `image`, `scan`, `hpr`, `report`, etc. |
| `format`        | TEXT     | File format (`LAZ`, `LAS`, `E57`, `PLY`, `JPG`, etc.). |
| `uri`           | TEXT     | Path or URL to the file.  If relative, it is relative to the
  dataset bundle root. |
| `crs_epsg`      | INTEGER  | CRS of coordinates in the asset (for point clouds). |
| `point_count`   | INTEGER  | Number of points (for point clouds). |
| `bytes`         | INTEGER  | File size in bytes. |
| `hash`          | TEXT     | File checksum (e.g. MD5 or SHA256) for integrity. |
| `created_at`    | DATETIME | Timestamp when the asset record was created. |
| `notes`         | TEXT     | Additional metadata (sensor, acquisition time, etc.). |

**Relationships:**

* An `Asset` can be linked to a `Tree` or a `Campaign` or both.  Campaign‑level assets
  include tree packs, ground-only clouds and residual clouds; tree‑level assets include
  per‑tree extractions, CT scans, photographs, etc.

### 5. Nested measurement tables

Nested tables capture detailed, often repetitive measurements associated with a single
measurement event.  Each record references the parent `measurement_uid`.

The specification defines the following nested tables.  Partners may introduce additional
tables following the same pattern.

| Table         | Key columns               | Description |
|---------------|---------------------------|-------------|
| `Whorl`       | `(measurement_uid, whorl_id)` | Branch whorl positions.  Columns: `whorl_id` (TEXT),
  `height_from_base_m` (REAL), optional `order` (INTEGER). |
| `StemTaper`   | `(measurement_uid, taper_id)` | Diameters along the stem.  Columns: `taper_id` (TEXT),
  `height_m` (REAL), `diameter_cm` (REAL). |
| `Defect`      | `(measurement_uid, defect_id)` | Stem defects.  Columns: `defect_id` (TEXT), `type`
  (TEXT), `x`, `y`, `z` (REAL), `description` (TEXT). |
| `QSMCylinder` | `(measurement_uid, qsm_id)` | Cylinders from a quantitative structure model.  Columns:
  `qsm_id` (TEXT), `start_x`, `start_y`, `start_z` (REAL), `end_x`, `end_y`, `end_z` (REAL),
  `radius` (REAL), `branch_id` (TEXT). |
| `CrownPolygon`| `(measurement_uid, vertex_index)` | Vertices of the crown projection polygon.
  Columns: `vertex_index` (INTEGER), `x`, `y` (REAL).  Optionally store as a single POLYGON
  geometry instead. |
| `HarvesterLog`| `(measurement_uid, log_uid)` | Logs produced by a harvester.  Columns: `log_uid`
  (TEXT), `log_key` (INTEGER), `product_key` (TEXT), `start_pos_cm`, `length_cm` (REAL),
  `top_diameter_cm` (REAL), `butt_diameter_cm` (REAL), `volume_m3` (REAL), `quality_grade` (TEXT).
  Each `log_uid` is globally unique; recommended format: `tree_uid_LogX`. |
| `StemProfile` | `(measurement_uid, profile_index)` | Continuous stem profile derived from logs.
  Columns: `profile_index` (INTEGER), `height_cm` (REAL), `diameter_mm` (REAL), `stem_grade`
  (INTEGER). |
| `PriceMatrix` | `(measurement_uid, product_key, length_class, diameter_class)` | Price tables
  used in harvester optimisation.  Columns: `product_key`, `length_class_m` (REAL),
  `diameter_class_cm` (REAL), `price` (REAL), `currency` (TEXT).  The combination of
  `(measurement_uid, product_key, length_class_m, diameter_class_cm)` is unique. |
| `CTMetrics`   | `(measurement_uid, metric_id)` | Metrics derived from CT scans.  Columns include
  `metric_id` (TEXT), `knot_count`, `max_knot_diameter_cm`, `mean_ring_width_mm`,
  `density_kg_m3`, `description`. |
| `LogQuality`  | `(log_uid, measurement_uid)` | Quality grading of logs from sawmill or scanner.
  Columns: `grading_date` (DATE), `quality_grade` (TEXT), `source` (TEXT), `notes`. |

Additional nested tables may be added following the same pattern: primary key includes
`measurement_uid` (or `log_uid` for log‑level tables); columns store domain‑specific
attributes; foreign keys enforce linkage to the parent measurement or log.

### 6. Harvester‑specific entities

SingleTree uses a dedicated set of tables to store harvested stem and log information
extracted from StanForD 2010 harvester production files via the `optbuck` parser.  These
tables are separate from the general nested tables above to accommodate the structure of
harvester data.

| Table               | Key columns                     | Description |
|---------------------|---------------------------------|-------------|
| `HarvesterStem`     | `stem_uid` (PK)                 | Each row represents a felled stem.  Columns include
  `asset_uid` (FK to the harvester .hpr file), `stem_key` (INT), `species_group_key` (INT),
  `harvest_date` (DATE), `lat`, `lon`, `alt` (REAL), `dbh_mm` (REAL), `m3sub` (REAL),
  `m3sob` (REAL), `computed_height_cm` (REAL), etc. |
| `HarvesterLog`      | `log_uid` (PK), `stem_uid` (FK) | Each log cut from a stem.  Columns include
  `log_key` (INT), `product_key` (INT), `start_pos_cm`, `length_cm`, `m3sub`, `m3sob`,
  diameters at butt/mid/top in mm, `availability_flag`, etc. |
| `HarvesterStemProfile` | `stem_uid`, `profile_index` | Derived continuous stem profile.  Columns:
  `pos_cm` (REAL), `diameter_mm` (REAL), `stem_grade` (INT). |
| `HarvesterPriceMatrix` | `asset_uid`, `product_key`, `length_class_m`, `diameter_class_cm` | Price
  matrix extracted from the StanForD file.  Columns: `price` (REAL), `currency` (TEXT). |

### 7. Identifier rules

To ensure that all entities can be unambiguously referenced across files and partners, the
following identifier conventions are mandated:

1. **Tree UID:** Must be globally unique within the dataset.  Compose it from the site or
   stand code and the local tree number, separated by an underscore (e.g. `SCAstand1_1`).
2. **Measurement UID:** Combine `tree_uid`, `source_type`, and `measurement_date` in ISO
   format, separated by underscores.  If multiple measurements of the same type occur on
   the same date, append an index (e.g. `SCAstand1_1_TLS_2019-06-04_1`).
3. **Campaign UID:** Concatenate the sensor/platform name, acquisition date and area ID,
   separated by underscores (e.g. `MLS_VENDORX_2025-06-01_STAND123`).
4. **Asset UID:** Use a prefix indicating the type (e.g. `pc` for point cloud), followed by
   `campaign_uid` or `tree_uid` and other qualifiers.  For example:
   `pc_MLS_VENDORX_2025-06-01_STAND123_tile_001_tree_pack`.
5. **Log UID:** Combine `tree_uid` (or `stem_uid`) with a log index, e.g. `SCAstand1_1_Log1`.
   For logs coming directly from harvester data, use `hpr:<asset_uid>:stem:<StemKey>:log:<LogKey>`.
6. **Stem UID (harvester):** Use `hpr:<asset_uid>:stem:<StemKey>`.

Identifiers must remain stable once assigned and may not be reused for different objects.

### 8. Provenance and versioning

Every table includes fields that capture provenance and version information:

* `created_at` – timestamp when the record was created.
* `created_by` – user, organisation or process that created the record.
* `processing_pipeline` – software and version used (e.g. `TreeQSM 2.4.1`, `optbuck_py 0.3.0`).
* `notes` – free‑text comments for any additional context.

The overall dataset should carry a `schema_version` (e.g. `1.0.0`) and a dataset‐level
`dataset_version` (e.g. `2025-09-15` for each release).  Schema evolution must be managed
carefully: new tables and columns may be added in minor versions; breaking changes
(e.g. altering primary keys) require a major version bump.

## Physical schema: GeoPackage

The physical implementation uses **GeoPackage** (an SQLite database with spatial
extensions) for portability and GIS interoperability.  The GeoPackage file contains all
tables described above, stored with appropriate data types and constraints.  The geometry
columns are defined with dimension `XY` or `XYZ` and include an EPSG code.  Spatial
indices (RTree) should be created on geometry columns to accelerate spatial queries.

An accompanying SQL file (`geopackage_schema.sql`) defines the DDL statements needed to
initialise a fresh GeoPackage with the required tables, columns, primary keys, foreign
keys, and indexes.  Partners implementing the schema should apply this DDL once when
creating a new database.  The schema file is versioned alongside this specification.

### Vector tiles

For web visualisation of millions of trees, a separate process generates vector tiles
(`.mvt` files) from the `trees` table and selected attributes (species, status, summary
metrics).  These tiles are not stored inside the GeoPackage but are derived from it.

### Export formats

* **GeoJSON:** Suitable for sharing small subsets of trees.  GeoJSON features should
  include only essential attributes and geometry; large nested tables and assets should
  remain external.
* **CSV/Parquet:** Nested tables can be exported as CSV or Parquet for analysis.  The
  column names and types must follow this specification.
* **LAS/LAZ/E57/PLY:** All point clouds are stored externally, referenced via `uri` in the
  `Asset` table.  LAZ is preferred for efficiency; LAS is acceptable where compression
  backends are unavailable.

## Conclusion

This specification defines a robust, extensible framework for single‑tree data management
and exchange.  By combining a simple tree index with relational tables for detailed
measurements and campaign metadata, and by linking external assets via URIs, SingleTree
achieves both human readability and machine efficiency.  Implementers should follow this
specification closely, using the provided GeoPackage schema as a baseline.  Additional
tables and fields may be added to address partner‑specific needs, provided that they
maintain the core relationships and identifier conventions described herein.