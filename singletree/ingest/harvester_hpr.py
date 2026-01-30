"""Harvester (StanForD 2010) import routines for SingleTree.

This module provides functions to ingest harvester production files
written in the StanForD 2010 XML format (typically with a ``.hpr``
extension).  It relies on the Python port of the *optBuck* library
provided by the user to parse the XML into pandas data frames.  The
ingestor converts these data frames into plain Python dictionaries
that match the tables defined in the SingleTree specification.  It
also records the raw HPR file as an asset so that the original data
can be retained for provenance and reprocessing.

The primary entry point is :func:`import_harvester_hpr`, which
returns a dictionary containing the asset metadata and lists of
records for the `harvester_stems`, `harvester_logs`,
`harvester_stem_profile` and `harvester_price_matrix` tables.  It
does not insert anything into the database; callers are responsible
for writing these records into the GeoPackage or other store.

Example usage::

    from singletree.ingest.harvester_hpr import import_harvester_hpr

    result = import_harvester_hpr(
        hpr_path="/data/raw/harvester_2025-03-15.hpr",
        campaign_uid="Harvester_2025-03-15",
        output_root="/data/SingleTree/assets",
    )
    hpr_asset = result["asset_record"]
    stems = result["stems"]
    logs = result["logs"]
    profile = result["stem_profile"]
    price_matrix = result["price_matrix"]

The returned records can then be inserted into the appropriate tables.
"""

from __future__ import annotations

import os
import uuid
import datetime
from typing import Dict, List, Optional

try:
    # Attempt to import the optbuck library.  This module is
    # provided by the user as a Python port of the optBuck R
    # package.  It must be installed or available on the Python
    # path for this importer to work.  If the import fails, a
    # descriptive ImportError will be raised when ingest functions
    # are called.
    import optbuck  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    optbuck = None  # type: ignore


def _ensure_optbuck() -> None:
    """Ensure that the optbuck library is available.

    This helper raises an ImportError with a helpful message if
    ``optbuck`` could not be imported.  It is called at the start
    of each ingestion function.
    """

    if optbuck is None:
        raise ImportError(
            "The optbuck library is required for harvester ingestion. "
            "Please install the Python port of optBuck or ensure that it "
            "is available on the Python path."
        )


def _make_asset_uid() -> str:
    """Generate a unique asset identifier using UUID4."""
    return str(uuid.uuid4())


def _file_metadata(path: str) -> Dict[str, object]:
    """Gather basic file metadata for a given path.

    :param path: Path to a file on disk.
    :returns: Dictionary with size in bytes and SHA256 checksum.
    """
    import hashlib

    buf_size = 65536
    sha256 = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            data = f.read(buf_size)
            if not data:
                break
            size += len(data)
            sha256.update(data)
    return {"bytes": size, "hash": sha256.hexdigest()}


def _normalize_date(date_str: Optional[str]) -> Optional[str]:
    """Normalize date strings from the harvester file.

    The ``get_stems`` function returns a ``Date`` column which may
    contain the literal string ``"vasket"`` or other non-date
    values.  This helper attempts to parse ISO date strings and
    returns them in ``YYYY-MM-DD`` format.  If parsing fails or the
    input is not a valid date, ``None`` is returned.

    :param date_str: Raw date string from optbuck.
    :returns: Normalised date string or None.
    """
    if not date_str:
        return None
    # Some HPR files use the Norwegian term "vasket" (meaning
    # "washed") in place of a date.  Treat this as missing.
    if date_str.strip().lower() == "vasket":
        return None
    try:
        # Try ISO format first (YYYY-MM-DD)
        dt = datetime.date.fromisoformat(date_str)
        return dt.isoformat()
    except Exception:
        # Try alternative formats (e.g. DD.MM.YYYY)
        try:
            dt = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
            return dt.isoformat()
        except Exception:
            return None


def import_harvester_hpr(
    *,
    hpr_path: str,
    campaign_uid: str,
    output_root: str = "assets/harvester",  # default subdir for raw HPR files
    currency: str = "EUR",
) -> Dict[str, object]:
    """Import a StanForD 2010 harvester production file (HPR).

    This function parses the given HPR file using the optbuck library
    and converts the resulting data frames into records suitable for
    insertion into the SingleTree database.  It also copies the raw
    HPR file into the dataset’s asset directory and returns metadata
    for that asset.

    Note that this function does **not** create Measurement records
    directly; it only produces the nested tables defined for
    harvester data (stems, logs, stem profiles and price matrices) as
    well as an asset record for the raw file.  Mapping the harvested
    stems to existing trees must be handled by the caller.

    :param hpr_path: Path to the .hpr file on disk.
    :param campaign_uid: Identifier for the campaign from which this
        file originates.  The same campaign UID should be used
        consistently across tree measurements and assets.
    :param output_root: Directory under which to store the raw HPR
        file relative to the dataset bundle.  Defaults to
        ``"assets/harvester"``.  The final path will be
        ``{output_root}/{campaign_uid}/{filename}``.
    :param currency: Currency code to assign to price matrix records.
    :returns: A dictionary with the following keys:
        ``asset_record`` (metadata for the raw HPR file), ``stems``
        (list of harvester_stems records), ``logs`` (list of
        harvester_logs records), ``stem_profile`` (list of
        harvester_stem_profile records) and ``price_matrix`` (list of
        harvester_price_matrix records).
    """

    _ensure_optbuck()

    if not os.path.isfile(hpr_path):
        raise FileNotFoundError(f"Harvester file does not exist: {hpr_path}")

    # Prepare destination for the raw HPR asset
    filename = os.path.basename(hpr_path)
    dest_dir = os.path.join(output_root, campaign_uid)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    # Copy the file into the dataset bundle if it doesn’t already exist
    if not os.path.abspath(hpr_path) == os.path.abspath(dest_path):
        # Copy file contents
        with open(hpr_path, "rb") as src, open(dest_path, "wb") as dst:
            while True:
                buf = src.read(65536)
                if not buf:
                    break
                dst.write(buf)

    # Generate asset UID and gather metadata
    asset_uid = _make_asset_uid()
    meta = _file_metadata(dest_path)
    asset_record = {
        "asset_uid": asset_uid,
        "campaign_uid": campaign_uid,
        "tree_uid": None,
        "scope": "campaign",
        "pc_role": None,
        "asset_type": "hpr",
        "format": os.path.splitext(filename)[1].lstrip(".").upper(),
        "uri": os.path.relpath(dest_path, start=output_root).replace(os.sep, "/"),
        "crs_epsg": None,
        "point_count": None,
        "bytes": meta["bytes"],
        "hash": meta["hash"],
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "notes": None,
    }

    # Parse the HPR file using optbuck
    xml_root = optbuck.get_xml_node(hpr_path)
    stems_df = optbuck.get_stems(xml_root)
    logs_df = optbuck.get_logs(xml_root)
    stemprof_df = optbuck.get_stemprofile(xml_root, logs_df)
    price_matrices = optbuck.get_price_matrices(xml_root)

    # Convert stems DataFrame into records
    stems: List[Dict[str, object]] = []
    for _, row in stems_df.iterrows():
        stem_key = int(row["StemKey"])
        stem_uid = f"{campaign_uid}_stem_{stem_key}"

        # Coordinates: if latitude/longitude are present, use them
        lat = row.get("Latitude")
        lon = row.get("Longitude")
        alt = row.get("Altitude")
        position_lat = float(lat) if lat is not None else None
        position_lon = float(lon) if lon is not None else None
        # Altitude is likely centimetres; convert to metres if numeric
        if alt is not None and not (alt != alt):  # check for NaN
            try:
                # Some HPR files store altitude as mm or cm; scale to m
                alt_val = float(alt)
                # If altitude is implausibly large (>500), assume cm and divide by 100
                position_alt = alt_val / 100.0 if alt_val > 500.0 else alt_val / 1000.0
            except Exception:
                position_alt = None
        else:
            position_alt = None

        # DBH in data is in mm; convert to centimetres
        dbh_raw = row.get("DBH")
        dbh_cm = float(dbh_raw) / 10.0 if dbh_raw is not None else None

        # Computed height (ComHeight) appears to be centimetres; convert to metres
        com_height = row.get("ComHeight")
        height_m = float(com_height) / 100.0 if com_height is not None else None

        stems.append(
            {
                "stem_uid": stem_uid,
                "asset_uid": asset_uid,
                "stem_key": stem_key,
                "species_group_key": int(row.get("SpeciesGroupKey"))
                if row.get("SpeciesGroupKey") == row.get("SpeciesGroupKey")
                else None,
                "harvest_date": _normalize_date(row.get("Date")),
                "position_lat": position_lat,
                "position_lon": position_lon,
                "altitude_m": position_alt,
                "dbh_cm": dbh_cm,
                "volume_m3_sub": float(row.get("m3sub")) if row.get("m3sub") == row.get("m3sub") else None,
                "volume_m3_sob": float(row.get("m3sob")) if row.get("m3sob") == row.get("m3sob") else None,
                "computed_height_m": height_m,
            }
        )

    # Convert logs DataFrame into records
    logs: List[Dict[str, object]] = []
    for _, row in logs_df.iterrows():
        stem_key = int(row["StemKey"])
        log_key = int(row["LogKey"])
        stem_uid = f"{campaign_uid}_stem_{stem_key}"
        log_uid = f"{stem_uid}_log_{log_key}"

        # StartPos and LogLength appear to be centimetres; leave as cm
        start_pos_cm = float(row.get("StartPos")) if row.get("StartPos") == row.get("StartPos") else None
        length_cm = float(row.get("LogLength")) if row.get("LogLength") == row.get("LogLength") else None
        # Diameters are in millimetres; convert to centimetres
        butt_cm = float(row.get("Butt_ob")) / 10.0 if row.get("Butt_ob") == row.get("Butt_ob") else None
        top_cm = float(row.get("Top_ob")) / 10.0 if row.get("Top_ob") == row.get("Top_ob") else None
        volume_m3 = float(row.get("m3sub")) if row.get("m3sub") == row.get("m3sub") else None

        logs.append(
            {
                "log_uid": log_uid,
                "stem_uid": stem_uid,
                "log_key": log_key,
                "product_key": int(row.get("ProductKey"))
                if row.get("ProductKey") == row.get("ProductKey")
                else None,
                "start_pos_cm": start_pos_cm,
                "length_cm": length_cm,
                "butt_diameter_cm": butt_cm,
                "top_diameter_cm": top_cm,
                "volume_m3": volume_m3,
                "quality_grade": None,
            }
        )

    # Convert stem profile DataFrame into records
    stem_profile: List[Dict[str, object]] = []
    # Group by StemKey to assign profile_index sequentially
    profile_groups = stemprof_df.groupby("StemKey")
    for stem_key, group in profile_groups:
        stem_uid = f"{campaign_uid}_stem_{int(stem_key)}"
        for idx, (_, row) in enumerate(group.iterrows(), start=1):
            # diameterPosition appears to be in centimetres or decimetres; assume centimetres
            pos_cm = float(row.get("diameterPosition")) if row.get("diameterPosition") == row.get("diameterPosition") else None
            # DiameterValue is in millimetres
            diam_mm = float(row.get("DiameterValue")) if row.get("DiameterValue") == row.get("DiameterValue") else None
            grade_val = int(row.get("StemGrade")) if row.get("StemGrade") == row.get("StemGrade") else None
            stem_profile.append(
                {
                    "stem_uid": stem_uid,
                    "profile_index": idx,
                    "height_cm": pos_cm,
                    "diameter_mm": diam_mm,
                    "stem_grade": grade_val,
                }
            )

    # Convert price matrices into records
    price_matrix: List[Dict[str, object]] = []
    for product_key, df in price_matrices.items():
        # Skip waste key (usually 999999) because it contains default values
        try:
            pk_int = int(product_key)
        except Exception:
            continue
        # Flatten the pivot table: index lCLL (length lower limit), columns dCLL
        for lcll, row in df.iterrows():
            for dcll, price in row.items():
                if price != price:  # skip NaN
                    continue
                # lCLL appears to be millimetres; convert to metres
                length_m = float(lcll) / 100.0
                # dCLL appears to be millimetres; convert to centimetres
                diameter_cm = float(dcll) / 10.0
                price_matrix.append(
                    {
                        "asset_uid": asset_uid,
                        "product_key": pk_int,
                        "length_class_m": length_m,
                        "diameter_class_cm": diameter_cm,
                        "price": float(price),
                        "currency": currency,
                    }
                )

    return {
        "asset_record": asset_record,
        "stems": stems,
        "logs": logs,
        "stem_profile": stem_profile,
        "price_matrix": price_matrix,
    }
