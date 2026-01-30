"""SingleTree package

This package provides the core classes and functions for working with the
SingleTree data model.  It includes modules for loading and saving
datasets, importing various data types (LiDAR, harvester logs, field
inventories), handling point cloud operations and interacting with the
underlying GeoPackage database.

At this stage the package skeleton is under active development.  See
`singletree/ingest/lidar.py` for the Mode A2 tree pack importer.
"""

# Export subpackages and modules for external use.
__all__ = [
    "ingest",
    "pointcloud",
    "matching",
    "query",
]