-- GeoPackage schema for the SingleTree data model
--
-- This SQL file defines the core tables, relationships, and indexes
-- required to instantiate a new GeoPackage for the SingleTree project.
-- It follows the specification documented in SPEC.md and is intended
-- to be applied once when creating a new database.  Geometry columns
-- are declared using the standard SQLite BLOB type; implementers may
-- optionally register them with gpkg_geometry_columns if using a full
-- GeoPackage library.

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------------
-- Table: campaigns
-- Represents data acquisition campaigns (ALS/TLS/MLS/ULS flights, etc.)
-- -------------------------------------------------------------------
CREATE TABLE campaigns (
    campaign_uid             TEXT PRIMARY KEY,
    source_uid               TEXT,
    acquisition_date         DATE,
    area_uid                 TEXT,
    crs_epsg                 INTEGER,
    semantic_codebook_json   TEXT,
    dims_json                TEXT,
    footprint_geom           BLOB,
    notes                    TEXT
);

-- -------------------------------------------------------------------
-- Table: trees
-- Main tree index.  Stores core attributes and geometry.  Detailed
-- measurements reside in separate tables.
-- -------------------------------------------------------------------
CREATE TABLE trees (
    tree_uid                TEXT PRIMARY KEY,
    treeID                  TEXT,
    source                  TEXT,
    species_code            TEXT,
    status                  TEXT,
    height_m                REAL,
    dbh_cm                  REAL,
    crown_base_height_m     REAL,
    last_measurement_date   DATE,
    crs_epsg                INTEGER,
    geom                    BLOB,
    -- Flag indicating whether this tree is a temporary placeholder used
    -- when a measurement could not be confidently matched to an existing
    -- tree.  Temporary trees should be reviewed and resolved by a human
    -- operator.
    is_temporary           INTEGER DEFAULT 0
);

-- -------------------------------------------------------------------
-- Table: measurements
-- Represents a single measurement event on a tree.  Nested tables
-- reference measurement_uid.
-- -------------------------------------------------------------------
CREATE TABLE measurements (
    measurement_uid        TEXT PRIMARY KEY,
    tree_uid               TEXT NOT NULL,
    campaign_uid           TEXT,
    source_type            TEXT NOT NULL,
    measurement_date       DATE NOT NULL,
    height_m               REAL,
    dbh_cm                 REAL,
    crown_base_height_m    REAL,
    species_code           TEXT,
    age                    INTEGER,
    health                 TEXT,
    machine_id             TEXT,
    stand_id               TEXT,
    notes                  TEXT,
    -- Status of the matching between this measurement and a tree.  See SPEC.md
    -- for accepted values (e.g. 'auto', 'unmatched', 'manual').  When set to
    -- 'unmatched' the tree_uid refers to a temporary placeholder tree.
    match_status           TEXT DEFAULT 'unmatched',
    -- Suggested tree identifier when a measurement could match multiple
    -- candidates.  This field is informational and not enforced as a foreign
    -- key.  A human reviewer can later use this to decide whether to
    -- reassign the measurement to the candidate tree.
    candidate_tree_uid     TEXT,
    FOREIGN KEY (tree_uid)     REFERENCES trees(tree_uid)        ON DELETE CASCADE,
    FOREIGN KEY (campaign_uid) REFERENCES campaigns(campaign_uid) ON DELETE SET NULL
);

CREATE INDEX idx_measurements_tree_uid ON measurements(tree_uid);
CREATE INDEX idx_measurements_campaign_uid ON measurements(campaign_uid);

-- -------------------------------------------------------------------
-- Table: assets
-- Files or resources associated with trees or campaigns.
-- -------------------------------------------------------------------
CREATE TABLE assets (
    asset_uid     TEXT PRIMARY KEY,
    campaign_uid  TEXT,
    tree_uid      TEXT,
    scope         TEXT NOT NULL,
    pc_role       TEXT,
    asset_type    TEXT NOT NULL,
    format        TEXT NOT NULL,
    uri           TEXT NOT NULL,
    crs_epsg      INTEGER,
    point_count   INTEGER,
    bytes         INTEGER,
    hash          TEXT,
    created_at    DATETIME,
    notes         TEXT,
    FOREIGN KEY (campaign_uid) REFERENCES campaigns(campaign_uid) ON DELETE SET NULL,
    FOREIGN KEY (tree_uid)     REFERENCES trees(tree_uid)         ON DELETE SET NULL
);

CREATE INDEX idx_assets_campaign_uid ON assets(campaign_uid);
CREATE INDEX idx_assets_tree_uid ON assets(tree_uid);

-- -------------------------------------------------------------------
-- Nested measurement tables
-- Each of these tables references measurements.measurement_uid.
-- -------------------------------------------------------------------

CREATE TABLE whorls (
    measurement_uid        TEXT NOT NULL,
    whorl_id               TEXT NOT NULL,
    height_from_base_m     REAL NOT NULL,
    "order"                INTEGER,
    PRIMARY KEY (measurement_uid, whorl_id),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE stem_taper (
    measurement_uid        TEXT NOT NULL,
    taper_id               TEXT NOT NULL,
    height_m               REAL NOT NULL,
    diameter_cm            REAL NOT NULL,
    PRIMARY KEY (measurement_uid, taper_id),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE defects (
    measurement_uid        TEXT NOT NULL,
    defect_id             TEXT NOT NULL,
    type                  TEXT,
    x                     REAL,
    y                     REAL,
    z                     REAL,
    description           TEXT,
    PRIMARY KEY (measurement_uid, defect_id),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE qsm_cylinders (
    measurement_uid        TEXT NOT NULL,
    qsm_id                TEXT NOT NULL,
    start_x               REAL,
    start_y               REAL,
    start_z               REAL,
    end_x                 REAL,
    end_y                 REAL,
    end_z                 REAL,
    radius                REAL,
    branch_id             TEXT,
    PRIMARY KEY (measurement_uid, qsm_id),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE crown_polygon (
    measurement_uid        TEXT NOT NULL,
    vertex_index          INTEGER NOT NULL,
    x                     REAL,
    y                     REAL,
    PRIMARY KEY (measurement_uid, vertex_index),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE harvester_logs (
    measurement_uid        TEXT NOT NULL,
    log_uid               TEXT NOT NULL,
    log_key               INTEGER,
    product_key           INTEGER,
    start_pos_cm          REAL,
    length_cm             REAL,
    top_diameter_cm       REAL,
    butt_diameter_cm      REAL,
    volume_m3             REAL,
    quality_grade         TEXT,
    PRIMARY KEY (measurement_uid, log_uid),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE stem_profile (
    measurement_uid        TEXT NOT NULL,
    profile_index         INTEGER NOT NULL,
    height_cm             REAL,
    diameter_mm           REAL,
    stem_grade            INTEGER,
    PRIMARY KEY (measurement_uid, profile_index),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE price_matrix (
    measurement_uid        TEXT NOT NULL,
    product_key           INTEGER NOT NULL,
    length_class_m        REAL NOT NULL,
    diameter_class_cm     REAL NOT NULL,
    price                 REAL,
    currency              TEXT,
    PRIMARY KEY (measurement_uid, product_key, length_class_m, diameter_class_cm),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE ct_metrics (
    measurement_uid        TEXT NOT NULL,
    metric_id             TEXT NOT NULL,
    knot_count            INTEGER,
    max_knot_diameter_cm  REAL,
    mean_ring_width_mm    REAL,
    density_kg_m3         REAL,
    description           TEXT,
    PRIMARY KEY (measurement_uid, metric_id),
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

CREATE TABLE log_quality (
    log_uid               TEXT NOT NULL,
    measurement_uid        TEXT NOT NULL,
    grading_date          DATE,
    quality_grade         TEXT,
    source                TEXT,
    notes                 TEXT,
    PRIMARY KEY (log_uid, measurement_uid),
    FOREIGN KEY (log_uid)        REFERENCES harvester_logs(log_uid)         ON DELETE CASCADE,
    FOREIGN KEY (measurement_uid) REFERENCES measurements(measurement_uid) ON DELETE CASCADE
);

-- -------------------------------------------------------------------
-- Harvester‑specific tables
-- These tables capture the structure of StanForD 2010 production files.
-- -------------------------------------------------------------------

CREATE TABLE harvester_stems (
    stem_uid              TEXT PRIMARY KEY,
    asset_uid             TEXT NOT NULL,
    stem_key             INTEGER,
    species_group_key     INTEGER,
    harvest_date          DATE,
    lat                  REAL,
    lon                  REAL,
    alt                  REAL,
    dbh_mm               REAL,
    m3sub                REAL,
    m3sob                REAL,
    computed_height_cm    REAL,
    FOREIGN KEY (asset_uid) REFERENCES assets(asset_uid) ON DELETE CASCADE
);

CREATE TABLE harvester_log (
    log_uid               TEXT PRIMARY KEY,
    stem_uid              TEXT NOT NULL,
    log_key               INTEGER,
    product_key           INTEGER,
    start_pos_cm          REAL,
    length_cm             REAL,
    butt_diameter_mm      REAL,
    mid_diameter_mm       REAL,
    top_diameter_mm       REAL,
    m3sub                 REAL,
    m3sob                 REAL,
    availability_flag     INTEGER,
    quality_grade         TEXT,
    FOREIGN KEY (stem_uid) REFERENCES harvester_stems(stem_uid) ON DELETE CASCADE
);

CREATE TABLE harvester_stem_profile (
    stem_uid              TEXT NOT NULL,
    profile_index         INTEGER NOT NULL,
    pos_cm               REAL,
    diameter_mm           REAL,
    stem_grade            INTEGER,
    PRIMARY KEY (stem_uid, profile_index),
    FOREIGN KEY (stem_uid) REFERENCES harvester_stems(stem_uid) ON DELETE CASCADE
);

CREATE TABLE harvester_price_matrix (
    asset_uid             TEXT NOT NULL,
    product_key           INTEGER NOT NULL,
    length_class_m        REAL NOT NULL,
    diameter_class_cm     REAL NOT NULL,
    price                 REAL,
    currency              TEXT,
    PRIMARY KEY (asset_uid, product_key, length_class_m, diameter_class_cm),
    FOREIGN KEY (asset_uid) REFERENCES assets(asset_uid) ON DELETE CASCADE
);

-- Indexes to improve lookup performance for harvester tables
CREATE INDEX idx_harvester_stems_asset_uid ON harvester_stems(asset_uid);
CREATE INDEX idx_harvester_log_stem_uid ON harvester_log(stem_uid);
CREATE INDEX idx_harvester_stem_profile_stem_uid ON harvester_stem_profile(stem_uid);
CREATE INDEX idx_harvester_price_matrix_asset_uid ON harvester_price_matrix(asset_uid);

-- End of schema