"""Query utilities for the SingleTree dataset.

This module provides helper functions to query trees by spatial
criteria.  Because SingleTree stores tree points as WKB geometries
within a GeoPackage, these helpers open the underlying SQLite
database, decode the point coordinates from the geometry blob and
apply simple spatial tests.  Two common operations are supported:

1. Querying trees within an axis‑aligned bounding box (extent).
2. Querying trees within an arbitrary polygon (ring) defined by a
   sequence of (x, y) coordinates.

The functions return a list of dictionaries representing tree records
matching the spatial criteria.  Geometry parsing is minimalistic and
does not depend on external GIS libraries; the first two coordinates
(x, y) are extracted from the WKB Point regardless of the presence of
additional dimensions (Z or M).

**Note:** These helpers assume that the polygon and bounding box
coordinates are expressed in the same coordinate reference system
(CRS) as the dataset (specified by the ``crs_epsg`` field in the
``trees`` table).  No coordinate transformations are performed.
"""

from __future__ import annotations

import sqlite3
import struct
from typing import Iterable, List, Tuple, Dict, Optional


def _parse_point_geom(blob: bytes) -> Optional[Tuple[float, float]]:
    """Extract the X and Y coordinates from a WKB Point geometry.

    The GeoPackage stores geometries as WKB (well‑known binary)
    blobs.  This helper reads the first two doubles after the byte
    order and geometry type.  It supports both little and big
    endian encodings.  Additional dimensions (Z or M) are ignored.

    :param blob: WKB geometry blob from the ``geom`` column.
    :returns: ``(x, y)`` or ``None`` if the blob is missing or
        malformed.
    """
    if not blob or len(blob) < 21:
        return None
    # Determine byte order: 0 = big endian, 1 = little endian
    byte_order_flag = blob[0]
    byte_order = "<" if byte_order_flag == 1 else ">"
    try:
        # Skip the endianness byte and geometry type (4 bytes)
        # Read two doubles (8 bytes each) for X and Y
        x = struct.unpack(f"{byte_order}d", blob[5:13])[0]
        y = struct.unpack(f"{byte_order}d", blob[13:21])[0]
        return (x, y)
    except Exception:
        return None


def _point_in_polygon(x: float, y: float, polygon: Iterable[Tuple[float, float]]) -> bool:
    """Check whether a point lies inside a polygon using the ray casting algorithm.

    :param x: X coordinate of the point.
    :param y: Y coordinate of the point.
    :param polygon: Iterable of (x, y) tuples representing the polygon
        vertices.  The polygon can be open or closed; the algorithm
        treats the last and first points as connected.
    :returns: True if the point is inside the polygon, False otherwise.
    """
    inside = False
    if not polygon:
        return False
    pts = list(polygon)
    n = len(pts)
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[(i + 1) % n]
        # Check if the point is on an edge; treat as inside
        # Compute cross product to check collinearity
        # But we ignore this for simplicity; collinear points are rare
        # Ray casting: consider edges crossing the horizontal ray at y
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersects:
            inside = not inside
    return inside


def query_trees_by_bbox(
    db_path: str,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
) -> List[Dict[str, object]]:
    """Return all tree records whose coordinates fall within a bounding box.

    :param db_path: Path to the GeoPackage (.gpkg) file.
    :param xmin: Minimum X coordinate (left).
    :param ymin: Minimum Y coordinate (bottom).
    :param xmax: Maximum X coordinate (right).
    :param ymax: Maximum Y coordinate (top).
    :returns: List of dictionaries representing the matching tree
        records, including their parsed coordinates.
    """
    results: List[Dict[str, object]] = []
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        # Retrieve relevant fields from the trees table
        cursor.execute(
            "SELECT tree_uid, treeID, source, species_code, status, height_m, dbh_cm, "
            "crown_base_height_m, last_measurement_date, crs_epsg, geom, is_temporary "
            "FROM trees"
        )
        for (
            tree_uid,
            treeID,
            source,
            species_code,
            status,
            height_m,
            dbh_cm,
            crown_base_height_m,
            last_measurement_date,
            crs_epsg,
            geom,
            is_temporary,
        ) in cursor.fetchall():
            pt = _parse_point_geom(geom)
            if pt is None:
                continue
            x, y = pt
            if (xmin <= x <= xmax) and (ymin <= y <= ymax):
                results.append(
                    {
                        "tree_uid": tree_uid,
                        "treeID": treeID,
                        "source": source,
                        "species_code": species_code,
                        "status": status,
                        "height_m": height_m,
                        "dbh_cm": dbh_cm,
                        "crown_base_height_m": crown_base_height_m,
                        "last_measurement_date": last_measurement_date,
                        "crs_epsg": crs_epsg,
                        "x": x,
                        "y": y,
                        "is_temporary": bool(is_temporary),
                    }
                )
    finally:
        conn.close()
    return results


def query_trees_by_polygon(
    db_path: str,
    polygon: Iterable[Tuple[float, float]],
    bounding_box: Optional[Tuple[float, float, float, float]] = None,
) -> List[Dict[str, object]]:
    """Return all tree records whose coordinates lie within a polygon.

    This function first optionally restricts the search to a bounding
    box to reduce the number of candidate trees, then applies a
    point‑in‑polygon test.  The polygon vertices should be provided
    in order (clockwise or counter‑clockwise).  The polygon can be
    open or closed; the algorithm will close it automatically.

    :param db_path: Path to the GeoPackage (.gpkg) file.
    :param polygon: Iterable of (x, y) coordinates defining the
        polygon.  At least three points are required.
    :param bounding_box: Optional pre‑computed bounding box
        ``(xmin, ymin, xmax, ymax)`` for the polygon.  If not
        provided, it will be computed automatically.
    :returns: List of tree records inside the polygon, including
        their parsed coordinates.
    """
    pts = list(polygon)
    if len(pts) < 3:
        raise ValueError("Polygon must have at least three vertices")
    # Compute bounding box if not provided
    if bounding_box is None:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))
    else:
        bbox = bounding_box
    # First filter by bounding box
    candidates = query_trees_by_bbox(db_path, *bbox)
    # Then apply point‑in‑polygon test
    inside: List[Dict[str, object]] = []
    for rec in candidates:
        if _point_in_polygon(rec["x"], rec["y"], pts):
            inside.append(rec)
    return inside


__all__ = ["query_trees_by_bbox", "query_trees_by_polygon"]