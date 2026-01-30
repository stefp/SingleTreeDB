"""Measurement-to-tree matching utilities for SingleTree.

This module implements helper functions to determine how incoming
measurement records should be associated with existing trees in the
database.  Because spatial positions are not always reliable (field
measurements may be inaccurate or missing), the matching logic relies
on a combination of attributes such as diameter at breast height
(``dbh_cm``), total height (``height_m``) and species code.  When
multiple trees satisfy the matching criteria or no tree fits the
measurement within the configured tolerances, the measurement is
flagged as **unmatched** and a new temporary tree record can be
created to hold the data until a human reviewer resolves the
ambiguity.

The key function is :func:`match_measurement_to_tree`, which accepts
a single measurement record, a list of tree records and a matching
configuration.  It returns a tuple containing the resolved tree
identifier (or ``None``), a ``match_status`` string and a
``candidate_tree_uid`` when the match is ambiguous.  See the
SingleTree SPEC for more details on these fields.

These utilities operate purely on Python data structures.  They do
not perform any database operations; callers are responsible for
inserting or updating records in the underlying GeoPackage.  When a
measurement cannot be matched with certainty, a temporary tree record
should be created with ``is_temporary=1`` and the measurement’s
``tree_uid`` should point to this new tree.  A suggested candidate
tree (the best match among ambiguous candidates) is provided to
assist manual review.
"""

from __future__ import annotations

import uuid
from typing import Dict, Iterable, Optional, Tuple, List


class MatchConfig:
    """Configuration for measurement-to-tree matching.

    :param dbh_tolerance: Maximum allowed absolute difference in DBH
        (centimetres) for a tree to be considered a match.
    :param height_tolerance: Maximum allowed absolute difference in
        total height (metres) for a tree to be considered a match.
    :param species_must_match: If True, candidate trees must have the
        same species code as the measurement.  If False, species is
        ignored when searching for matches.
    """

    def __init__(
        self,
        dbh_tolerance: float = 5.0,
        height_tolerance: float = 1.0,
        species_must_match: bool = True,
    ) -> None:
        self.dbh_tolerance = dbh_tolerance
        self.height_tolerance = height_tolerance
        self.species_must_match = species_must_match


def generate_temporary_tree_uid() -> str:
    """Generate a unique identifier for a temporary tree.

    Temporary tree identifiers are prefixed with ``temp_`` to
    distinguish them from permanent tree_uids, which typically
    incorporate stand and tree numbering.  The UUID ensures global
    uniqueness.

    :returns: A string such as ``temp_d3b07384-d9a6-44b3-a5d3-...``.
    """
    return f"temp_{uuid.uuid4()}"


def match_measurement_to_tree(
    measurement: Dict[str, object],
    trees: Iterable[Dict[str, object]],
    config: MatchConfig,
) -> Tuple[Optional[str], str, Optional[str]]:
    """Determine how a measurement should be linked to a tree.

    This function examines the provided list of existing tree
    records and returns a tuple with three elements:

    1. ``tree_uid``: The identifier of the tree to which the
       measurement should be attached.  If the measurement could
       not be matched with certainty, this will be ``None``.
    2. ``match_status``: One of ``'auto'``, ``'unmatched'`` or
       ``'manual'``.  In this implementation, only ``'auto'`` and
       ``'unmatched'`` are returned.  ``'auto'`` indicates that a
       single tree matched within the configured tolerances.  ``'unmatched'``
       means either no tree matched or multiple trees matched and the
       association is ambiguous.
    3. ``candidate_tree_uid``: When ``match_status`` is
       ``'unmatched'`` and multiple candidate trees were found, this
       field contains the tree_uid of the best candidate (the one
       with the smallest differences).  It can be used to guide
       manual resolution.  Otherwise it is ``None``.

    :param measurement: A measurement record with keys ``dbh_cm``,
        ``height_m`` and ``species_code``.  Values may be ``None``.
    :param trees: An iterable of tree records with the same keys.
    :param config: Matching configuration specifying tolerances and
        species matching behaviour.
    :returns: Tuple ``(tree_uid, match_status, candidate_tree_uid)``.
    """

    # Extract measurement attributes, defaulting to None
    m_dbh = measurement.get("dbh_cm")
    m_height = measurement.get("height_m")
    m_species = measurement.get("species_code")

    candidates: List[Tuple[str, float, float]] = []  # (tree_uid, dbh_diff, height_diff)

    for tree in trees:
        # Skip temporary trees when matching; they represent unresolved records
        if tree.get("is_temporary"):
            continue
        t_uid = tree["tree_uid"]
        t_dbh = tree.get("dbh_cm")
        t_height = tree.get("height_m")
        t_species = tree.get("species_code")

        # Species check
        if config.species_must_match and m_species and t_species and m_species != t_species:
            continue

        # Compute differences; if either value is missing, use a large difference
        if m_dbh is not None and t_dbh is not None:
            dbh_diff = abs(float(m_dbh) - float(t_dbh))
        else:
            dbh_diff = float("inf")

        if m_height is not None and t_height is not None:
            height_diff = abs(float(m_height) - float(t_height))
        else:
            height_diff = float("inf")

        # Candidate qualifies if differences are within tolerances
        if dbh_diff <= config.dbh_tolerance and height_diff <= config.height_tolerance:
            candidates.append((t_uid, dbh_diff, height_diff))

    if len(candidates) == 1:
        # Exactly one match: auto assign
        return candidates[0][0], "auto", None
    elif len(candidates) == 0:
        # No suitable tree found
        return None, "unmatched", None
    else:
        # Multiple candidates: ambiguous
        # Sort by DBH then height difference to find the best candidate
        candidates.sort(key=lambda x: (x[1], x[2]))
        best_candidate = candidates[0][0]
        return None, "unmatched", best_candidate


def assign_measurement(
    measurement: Dict[str, object],
    trees: Iterable[Dict[str, object]],
    config: Optional[MatchConfig] = None,
) -> Tuple[Dict[str, object], Optional[Dict[str, object]]]:
    """Assign a measurement to a tree, creating a temporary tree if needed.

    This helper wraps :func:`match_measurement_to_tree` and produces an
    updated measurement record with ``tree_uid``, ``match_status``
    and ``candidate_tree_uid`` fields populated.  If the match is
    ambiguous or no match is found, a new temporary tree record is
    created (and returned) with ``is_temporary=1``.  The caller can
    insert both the updated measurement and the temporary tree into
    the database.

    :param measurement: The measurement record to assign.  It must
        have a unique ``measurement_uid`` and at minimum ``dbh_cm``
        and ``height_m`` fields for matching.  Any existing
        ``tree_uid``, ``match_status`` or ``candidate_tree_uid``
        values will be overwritten.
    :param trees: Iterable of existing tree records.
    :param config: Optional matching configuration.  Defaults to
        :class:`MatchConfig()`.
    :returns: Tuple ``(updated_measurement, temporary_tree)``.  The
        ``temporary_tree`` will be ``None`` if the measurement could
        be assigned automatically.  Otherwise it contains a new tree
        record with ``is_temporary=1`` and ``tree_uid`` set to a
        generated identifier.
    """
    if config is None:
        config = MatchConfig()

    tree_uid, status, candidate_uid = match_measurement_to_tree(measurement, trees, config)

    temp_tree: Optional[Dict[str, object]] = None

    if status == "auto" and tree_uid is not None:
        measurement["tree_uid"] = tree_uid
        measurement["match_status"] = "auto"
        measurement["candidate_tree_uid"] = None
    else:
        # Generate a temporary tree UID and record
        tmp_uid = generate_temporary_tree_uid()
        temp_tree = {
            "tree_uid": tmp_uid,
            "treeID": None,
            "source": None,
            "species_code": measurement.get("species_code"),
            "status": None,
            "height_m": measurement.get("height_m"),
            "dbh_cm": measurement.get("dbh_cm"),
            "crown_base_height_m": measurement.get("crown_base_height_m"),
            "last_measurement_date": measurement.get("measurement_date"),
            "crs_epsg": None,
            "geom": None,
            "is_temporary": 1,
        }
        measurement["tree_uid"] = tmp_uid
        measurement["match_status"] = "unmatched"
        measurement["candidate_tree_uid"] = candidate_uid

    return measurement, temp_tree