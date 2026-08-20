"""
Utilitaires partages entre les fichiers de tests du controle E400.
"""

import json
from typing import Any


def construire_feature_linestring(
    identifiant: str,
    coordonnees: list[list[float]],
) -> dict[str, Any]:
    """Construit une feature GeoJSON LineString minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def construire_feature_multilinestring(
    identifiant: str,
    coordonnees: list[list[list[float]]],
) -> dict[str, Any]:
    """Construit une feature GeoJSON MultiLineString minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": "MultiLineString", "coordinates": coordonnees},
    }


def ecrire_collection(chemin: str, features: list[dict[str, Any]]) -> None:
    """Ecrit un FeatureCollection GeoJSON sans CRS sur disque pour les tests."""
    collection = {"type": "FeatureCollection", "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


def ecrire_collection_avec_crs(
    chemin: str,
    features: list[dict[str, Any]],
    epsg: str,
) -> None:
    """Ecrit un FeatureCollection GeoJSON avec CRS sur disque pour les tests.

    epsg doit etre au format 'EPSG:NNNN'.
    """
    code = epsg[5:]
    crs = {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{code}"},
    }
    collection = {"type": "FeatureCollection", "crs": crs, "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)
