"""
Utilitaires partages entre les fichiers de tests des controles de projection.
"""

import json
from typing import Any


def construire_feature(
    identifiant: str,
    type_geom: str,
    coordonnees: Any,
) -> dict[str, Any]:
    """Construit une feature GeoJSON minimale pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant},
        "geometry": {"type": type_geom, "coordinates": coordonnees},
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
    code = epsg[5:]  # Retire le prefixe "EPSG:"
    crs = {
        "type": "name",
        "properties": {"name": f"urn:ogc:def:crs:EPSG::{code}"},
    }
    collection = {"type": "FeatureCollection", "crs": crs, "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


def ecrire_metadata(chemin: str, srs: str) -> None:
    """Ecrit un fichier _metadata.json minimal avec le SRS specifie."""
    metadonnees = {"Metadata": {"SRS": srs}}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(metadonnees, fichier, ensure_ascii=False)
