"""LiDAR import routines for SingleTree.

This module implements functions to process LiDAR point clouds using
`laspy` and write tree pack, ground-only and residual point clouds
according to the Mode A2 strategy described in the SingleTree
specification.  The importer assumes that input point clouds contain
per‑point instance and semantic labels (and optionally confidence
scores) in ExtraBytes dimensions.  Users can supply the names of
these dimensions at run time.

The primary entry point is :func:`import_campaign_tree_packs`, which
takes one or more input LAS/LAZ files and produces per‑tile tree
packs and ground/residual clouds on disk.  It returns a list of
metadata dictionaries describing the generated assets; callers are
responsible for inserting these records into the database.

Example usage::

    from singletree.ingest.lidar import import_campaign_tree_packs

    assets = import_campaign_tree_packs(
        campaign_uid="MLS_2025-06-01_STAND123",
        input_paths=["/data/raw/MLS_2025-06-01_tile1.laz"],
        instance_dim="instance_pred",
        semantic_dim="semantic_pred",
        score_dim="score",
        ground_classes=[1],
        tree_classes=[2, 3],
        output_root="/data/SingleTree/pointclouds/campaigns"
    )

    for asset in assets:
        print(asset)

The function does not modify the database directly; instead it returns
records that the caller can use to populate the ``assets`` table.
"""

from __future__ import annotations

import os
from typing import List, Dict, Optional, Iterable

try:
    import numpy as np
    import laspy
except ImportError:
    # laspy and numpy are required for this module but may not be
    # installed in all environments.  Consumers of this function should
    # ensure these dependencies are available.
    np = None  # type: ignore
    laspy = None  # type: ignore


def _derive_tile_id(path: str, index: int) -> str:
    """Derive a tile identifier from the input filename.

    If the filename contains a substring like ``tile_##`` or
    ``tile_##.laz``, that token is used.  Otherwise the index is
    formatted as ``tile_{index:04d}``.

    :param path: Path to the input LAS/LAZ file.
    :param index: Zero‑based index of the file in the import list.
    :returns: Tile ID string.
    """
    basename = os.path.basename(path)
    stem, _ = os.path.splitext(basename)
    # Find token starting with "tile" (case insensitive)
    parts = stem.lower().split("_")
    for part in parts:
        if part.startswith("tile"):
            return stem  # use the full stem to preserve numbering
    return f"tile_{index:04d}"


def import_campaign_tree_packs(
    campaign_uid: str,
    input_paths: Iterable[str],
    *,
    instance_dim: str = "instance_pred",
    semantic_dim: str = "semantic_pred",
    score_dim: Optional[str] = "score",
    ground_classes: Iterable[int] = (1,),
    tree_classes: Iterable[int] = (2, 3),
    include_residual: bool = True,
    output_root: str = "pointclouds/campaigns",
    chunk_size: int = 1_000_000,
) -> List[Dict[str, object]]:
    """Import a set of LAS/LAZ files as tree packs for a campaign.

    This function reads one or more input point cloud files, splits
    points into **tree** (semantic class in ``tree_classes``),
    **ground** (semantic class in ``ground_classes``) and optionally
    **residual** points (semantic class in ``tree_classes`` but no
    valid instance ID), and writes each subset to its own LAZ file.

    The output directory structure follows the SingleTree convention:

    ``{output_root}/{campaign_uid}/tiles/{tile_id}_tree_pack.laz``

    ``{output_root}/{campaign_uid}/tiles/{tile_id}_ground_only.laz``

    ``{output_root}/{campaign_uid}/tiles/{tile_id}_residual.laz`` (if
    ``include_residual`` is ``True``)

    The function preserves all point attributes present in the input
    files.  No renaming of ExtraBytes dimensions is performed; the
    caller is responsible for recording the mapping of dimension names
    (via the ``dims_json`` in the ``campaigns`` table).

    :param campaign_uid: Unique identifier for the campaign.
    :param input_paths: Iterable of input LAS/LAZ file paths.
    :param instance_dim: Name of the instance segmentation dimension in
        the input point clouds.
    :param semantic_dim: Name of the semantic segmentation dimension in
        the input point clouds.
    :param score_dim: Name of the confidence score dimension (optional).
    :param ground_classes: Iterable of integer semantic codes
        representing ground or non‑tree points.
    :param tree_classes: Iterable of integer semantic codes
        representing tree points (wood and leaf classes).
    :param include_residual: Whether to produce a residual file
        containing points that have a tree semantic class but no valid
        instance ID (instance ID <= 0).
    :param output_root: Root directory under which to write output
        files.  Campaign output will be placed in
        ``{output_root}/{campaign_uid}/tiles``.
    :param chunk_size: Number of points to process per chunk.  Larger
        values reduce overhead but increase memory usage.
    :returns: A list of dictionaries describing the generated assets.
    Each dictionary contains keys suitable for insertion into the
    ``assets`` table (e.g. ``asset_uid``, ``campaign_uid``, ``uri``,
    ``pc_role``, ``asset_type``, ``format``, ``crs_epsg``, ``point_count``,
    ``bytes``).
    """

    if laspy is None or np is None:
        raise ImportError(
            "laspy and numpy must be installed to use import_campaign_tree_packs"
        )

    ground_codes = np.array(list(ground_classes), dtype=int)
    tree_codes = np.array(list(tree_classes), dtype=int)

    campaign_dir = os.path.join(output_root, campaign_uid, "tiles")
    os.makedirs(campaign_dir, exist_ok=True)

    asset_records: List[Dict[str, object]] = []
    for index, input_path in enumerate(input_paths):
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        tile_id = _derive_tile_id(input_path, index)

        # Prepare output file paths
        tree_pack_path = os.path.join(campaign_dir, f"{tile_id}_tree_pack.laz")
        ground_only_path = os.path.join(campaign_dir, f"{tile_id}_ground_only.laz")
        residual_path = os.path.join(campaign_dir, f"{tile_id}_residual.laz")

        # Open reader and prepare writers
        with laspy.open(input_path) as reader:
            header = reader.header

            # Copy header for each writer so point format and VLRs are preserved
            tree_header = header.copy()
            ground_header = header.copy()
            residual_header = header.copy()

            # Write outputs with the same point format and header
            with laspy.open(tree_pack_path, mode="w", header=tree_header) as tree_writer, \
                 laspy.open(ground_only_path, mode="w", header=ground_header) as ground_writer, \
                 (laspy.open(residual_path, mode="w", header=residual_header) if include_residual else _NullWriter()) as residual_writer:

                # Track counts and bounding boxes
                counts = {"tree": 0, "ground": 0, "residual": 0}
                bboxes = {
                    "tree": None,
                    "ground": None,
                    "residual": None,
                }

                for points in reader.chunk_iterator(chunk_size):
                    # `points` is a LasData containing arrays for each dimension
                    sem = points[semantic_dim]
                    inst = points[instance_dim] if instance_dim in points.point_format.extra_dimension_names else None

                    # Identify tree points
                    mask_tree = np.isin(sem, tree_codes)
                    # Identify ground points
                    mask_ground = np.isin(sem, ground_codes)
                    # Identify residual points (tree semantic but no valid instance)
                    if include_residual:
                        if inst is None:
                            mask_residual = mask_tree.copy()
                        else:
                            # Consider instance <= 0 or NaN as invalid
                            mask_residual = mask_tree & ((inst <= 0) | np.isnan(inst))
                        mask_tree = mask_tree & ~mask_residual  # remove residual from tree mask
                    else:
                        mask_residual = None

                    # Write tree points
                    if mask_tree.any():
                        tree_writer.write_points(points[mask_tree])
                        counts["tree"] += int(mask_tree.sum())
                        bboxes["tree"] = _update_bbox(bboxes["tree"], points[mask_tree])

                    # Write ground points
                    if mask_ground.any():
                        ground_writer.write_points(points[mask_ground])
                        counts["ground"] += int(mask_ground.sum())
                        bboxes["ground"] = _update_bbox(bboxes["ground"], points[mask_ground])

                    # Write residual points if enabled
                    if include_residual and mask_residual is not None and mask_residual.any():
                        residual_writer.write_points(points[mask_residual])
                        counts["residual"] += int(mask_residual.sum())
                        bboxes["residual"] = _update_bbox(bboxes["residual"], points[mask_residual])

        # Determine EPSG code from header
        crs_epsg = getattr(header, "epsg_code", None)

        # Populate asset records
        # Tree pack asset
        asset_records.append({
            "asset_uid": f"pc_{campaign_uid}_{tile_id}_tree_pack",
            "campaign_uid": campaign_uid,
            "tree_uid": None,
            "scope": "tile",
            "pc_role": "tree_pack",
            "asset_type": "pointcloud",
            "format": "LAZ",
            "uri": os.path.relpath(tree_pack_path, output_root),
            "crs_epsg": crs_epsg,
            "point_count": counts["tree"],
            "bytes": _file_size(tree_pack_path),
            "hash": None,  # hash can be computed externally
            "created_at": None,
            "notes": None,
        })
        asset_records.append({
            "asset_uid": f"pc_{campaign_uid}_{tile_id}_ground_only",
            "campaign_uid": campaign_uid,
            "tree_uid": None,
            "scope": "tile",
            "pc_role": "ground_only",
            "asset_type": "pointcloud",
            "format": "LAZ",
            "uri": os.path.relpath(ground_only_path, output_root),
            "crs_epsg": crs_epsg,
            "point_count": counts["ground"],
            "bytes": _file_size(ground_only_path),
            "hash": None,
            "created_at": None,
            "notes": None,
        })
        if include_residual:
            asset_records.append({
                "asset_uid": f"pc_{campaign_uid}_{tile_id}_residual",
                "campaign_uid": campaign_uid,
                "tree_uid": None,
                "scope": "tile",
                "pc_role": "background_residual",
                "asset_type": "pointcloud",
                "format": "LAZ",
                "uri": os.path.relpath(residual_path, output_root),
                "crs_epsg": crs_epsg,
                "point_count": counts["residual"],
                "bytes": _file_size(residual_path),
                "hash": None,
                "created_at": None,
                "notes": None,
            })

    return asset_records


class _NullWriter:
    """Context manager that acts like a laspy writer but does nothing.

    This is used when ``include_residual`` is False.  It implements
    ``write_points`` and the context manager protocol so that code
    does not need to branch on the existence of the residual writer.
    """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False  # propagate exceptions

    def write_points(self, points):  # type: ignore[no-self-use]
        return None


def _update_bbox(current_bbox, points: laspy.LasData):
    """Update a bounding box with the points from a chunk.

    :param current_bbox: A tuple ``((min_x, min_y, min_z), (max_x, max_y, max_z))``
        or ``None`` if no bbox exists yet.
    :param points: A ``LasData`` object containing point arrays.
    :returns: Updated bounding box.
    """
    # Extract coordinates
    xs = points.x
    ys = points.y
    zs = points.z
    # Compute min and max for this chunk
    chunk_min = (float(xs.min()), float(ys.min()), float(zs.min()))
    chunk_max = (float(xs.max()), float(ys.max()), float(zs.max()))
    if current_bbox is None:
        return (chunk_min, chunk_max)
    else:
        (min_x, min_y, min_z), (max_x, max_y, max_z) = current_bbox
        min_x = min(min_x, chunk_min[0])
        min_y = min(min_y, chunk_min[1])
        min_z = min(min_z, chunk_min[2])
        max_x = max(max_x, chunk_max[0])
        max_y = max(max_y, chunk_max[1])
        max_z = max(max_z, chunk_max[2])
        return ((min_x, min_y, min_z), (max_x, max_y, max_z))


def _file_size(path: str) -> Optional[int]:
    """Return the file size in bytes, or ``None`` if the file does not exist."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


__all__ = [
    "import_campaign_tree_packs",
]