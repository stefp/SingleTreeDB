"""Merge point clouds for SingleTree campaigns.

This module provides utilities to combine multiple tree pack and
background point clouds (ground and residual) belonging to the same
campaign into a single LAZ file.  The merged cloud maintains all
point attributes, including instance IDs, semantic classes and
optional confidence scores.  Merging is performed via streaming
append using `laspy` to avoid loading entire clouds into memory.

Usage example::

    from singletree.pointcloud.merge import merge_campaign_tree_packs
    assets = merge_campaign_tree_packs(
        campaign_uid="MLS_2025-06-01_STAND123",
        input_root="pointclouds/campaigns",
        include_ground=True,
        include_residual=False
    )
    for asset in assets:
        print(asset)

The function returns asset metadata for the merged files.  It does
not update the database; callers must insert the returned records
into the ``assets`` table.
"""

from __future__ import annotations

import os
from typing import List, Dict, Optional

try:
    import numpy as np
    import laspy
except ImportError:
    np = None  # type: ignore
    laspy = None  # type: ignore


def merge_campaign_tree_packs(
    campaign_uid: str,
    *,
    input_root: str = "pointclouds/campaigns",
    include_ground: bool = False,
    include_residual: bool = False,
    output_root: str = "pointclouds/campaigns",
    out_filename: Optional[str] = None,
    chunk_size: int = 1_000_000,
) -> List[Dict[str, object]]:
    """Merge all tree pack tiles for a campaign into a single point cloud.

    This function scans the tiles directory for the specified campaign,
    identifies all tree pack files (ending with ``_tree_pack.laz``), and
    appends their points into a single merged LAZ file.  If
    ``include_ground`` is ``True``, all corresponding ground clouds
    (ending with ``_ground_only.laz``) are appended after the tree
    points.  Similarly, if ``include_residual`` is ``True``, all
    residual clouds (ending with ``_residual.laz``) are appended.

    Merging is done in a streaming manner using `laspy` so that very
    large campaigns can be handled without exhausting memory.  The
    merged point cloud inherits the point format, VLRs and coordinate
    system from the first tree pack file encountered.  All additional
    files are assumed to have identical point formats and CRS.

    The merged file is stored under::

        {output_root}/{campaign_uid}/merged/{campaign_uid}_trees.laz

    If ``include_ground`` or ``include_residual`` are enabled, the
    suffix will be ``_trees_ground`` or ``_trees_ground_residual``
    respectively.

    :param campaign_uid: The campaign identifier.
    :param input_root: Root directory containing campaign data
        (default ``pointclouds/campaigns``).  The function will
        search in ``{input_root}/{campaign_uid}/tiles``.
    :param include_ground: Whether to include ground-only clouds in
        the merged output.
    :param include_residual: Whether to include residual clouds in
        the merged output.
    :param output_root: Root directory under which to place the
        merged output.  Defaults to the same as ``input_root``.
    :param out_filename: Optional custom filename for the merged
        output (without directory).  If ``None``, the filename is
        derived from ``campaign_uid`` and the options.
    :param chunk_size: Number of points to read/write per chunk.
    :returns: A list containing a single asset record for the merged
        file.  Asset fields include ``asset_uid``, ``campaign_uid``,
        ``uri``, ``pc_role``, ``asset_type``, ``format``, ``crs_epsg``,
        ``point_count`` and ``bytes``.
    """

    if laspy is None or np is None:
        raise ImportError(
            "laspy and numpy must be installed to use merge_campaign_tree_packs"
        )

    # Locate the tiles directory for this campaign
    tiles_dir = os.path.join(input_root, campaign_uid, "tiles")
    if not os.path.isdir(tiles_dir):
        raise FileNotFoundError(f"Tiles directory does not exist: {tiles_dir}")

    # Collect input files by role
    tree_files: List[str] = []
    ground_files: List[str] = []
    residual_files: List[str] = []
    for fname in sorted(os.listdir(tiles_dir)):
        if fname.endswith("_tree_pack.laz"):
            tree_files.append(os.path.join(tiles_dir, fname))
        elif include_ground and fname.endswith("_ground_only.laz"):
            ground_files.append(os.path.join(tiles_dir, fname))
        elif include_residual and fname.endswith("_residual.laz"):
            residual_files.append(os.path.join(tiles_dir, fname))

    if not tree_files:
        raise ValueError(f"No tree pack files found in {tiles_dir}")

    # Determine output directory and filename
    merged_dir = os.path.join(output_root, campaign_uid, "merged")
    os.makedirs(merged_dir, exist_ok=True)
    if out_filename is None:
        suffix = "trees"
        if include_ground:
            suffix += "_ground"
        if include_residual:
            suffix += "_residual"
        out_filename = f"{campaign_uid}_{suffix}.laz"
    merged_path = os.path.join(merged_dir, out_filename)

    # Prepare the writer using the header from the first tree file
    first_file = tree_files[0]
    with laspy.open(first_file) as infile:
        header = infile.header
        crs_epsg = getattr(header, "epsg_code", None)
        with laspy.open(merged_path, mode="w", header=header.copy()) as writer:
            point_count = 0
            bboxes = None

            # Helper to append all points from a list of files
            def append_files(files: List[str]) -> None:
                nonlocal point_count, bboxes
                for fpath in files:
                    with laspy.open(fpath) as src:
                        for points in src.chunk_iterator(chunk_size):
                            writer.write_points(points)
                            point_count += len(points)
                            bboxes = _update_bbox(bboxes, points)

            # Append tree points
            append_files(tree_files)
            # Append ground points if requested
            if include_ground:
                append_files(ground_files)
            # Append residual points if requested
            if include_residual:
                append_files(residual_files)

    # Prepare asset metadata
    asset_uid = f"pc_{campaign_uid}_merged"
    if include_ground:
        asset_uid += "_ground"
    if include_residual:
        asset_uid += "_residual"

    asset_record = {
        "asset_uid": asset_uid,
        "campaign_uid": campaign_uid,
        "tree_uid": None,
        "scope": "campaign",
        "pc_role": "merged",
        "asset_type": "pointcloud",
        "format": "LAZ",
        "uri": os.path.relpath(merged_path, output_root),
        "crs_epsg": crs_epsg,
        "point_count": point_count,
        "bytes": _file_size(merged_path),
        "hash": None,
        "created_at": None,
        "notes": None,
    }

    return [asset_record]


def _update_bbox(current_bbox, points: laspy.LasData):
    """Update a bounding box with points from a chunk.

    If ``current_bbox`` is ``None``, returns a new bbox.  Otherwise
    returns the expanded bbox covering both the existing bbox and the
    new points.
    """
    xs = points.x
    ys = points.y
    zs = points.z
    chunk_min = (float(xs.min()), float(ys.min()), float(zs.min()))
    chunk_max = (float(xs.max()), float(ys.max()), float(zs.max()))
    if current_bbox is None:
        return (chunk_min, chunk_max)
    (min_x, min_y, min_z), (max_x, max_y, max_z) = current_bbox
    min_x = min(min_x, chunk_min[0])
    min_y = min(min_y, chunk_min[1])
    min_z = min(min_z, chunk_min[2])
    max_x = max(max_x, chunk_max[0])
    max_y = max(max_y, chunk_max[1])
    max_z = max(max_z, chunk_max[2])
    return ((min_x, min_y, min_z), (max_x, max_y, max_z))


def _file_size(path: str) -> Optional[int]:
    """Return size of a file in bytes or ``None`` if it does not exist."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


__all__ = [
    "merge_campaign_tree_packs",
]