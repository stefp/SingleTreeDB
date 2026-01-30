-- DDL script for campaigns, measurements and assets tables
-- This script defines only the tables campaigns, measurements and assets
-- along with the relevant indexes and foreign key constraints.  Use
-- this script when initialising a GeoPackage with the minimal schema
-- required for storing campaign metadata, measurement events and
-- associated assets.

PRAGMA foreign_keys = ON;

-- Table: campaigns
-- Represents data acquisition campaigns (ALS/TLS/MLS/ULS flights, etc.)
CREATE TABLE IF NOT EXISTS campaigns (
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

-- Table: trees
-- The tree table is referenced by measurements.  It is not
-- included here because this script focuses on campaigns, measurements
-- and assets.  Ensure the trees table is created separately.

-- Table: measurements
-- Represents a single measurement event for a tree.  Each
-- measurement references a tree and optionally a campaign.
CREATE TABLE IF NOT EXISTS measurements (
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

CREATE INDEX IF NOT EXISTS idx_measurements_tree_uid ON measurements(tree_uid);
CREATE INDEX IF NOT EXISTS idx_measurements_campaign_uid ON measurements(campaign_uid);

-- Table: assets
-- Stores files and resources linked to campaigns or trees.  URIs can
-- be relative or absolute.  Point cloud roles (`pc_role`) include
-- tree_pack, ground_only, background_residual, merged, etc.
CREATE TABLE IF NOT EXISTS assets (
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

CREATE INDEX IF NOT EXISTS idx_assets_campaign_uid ON assets(campaign_uid);
CREATE INDEX IF NOT EXISTS idx_assets_tree_uid ON assets(tree_uid);

-- End of DDL for campaigns, measurements and assets