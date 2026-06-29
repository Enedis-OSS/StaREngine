"""
Utilitaires partagés entre les fichiers de tests des controles altimetriques.
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
    """Ecrit un FeatureCollection GeoJSON sur disque pour les tests."""
    collection = {"type": "FeatureCollection", "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


def ecrire_collection_avec_crs(
    chemin: str,
    features: list[dict[str, Any]],
    crs: dict[str, Any],
) -> None:
    """Ecrit un FeatureCollection GeoJSON avec CRS sur disque pour les tests."""
    collection = {"type": "FeatureCollection", "crs": crs, "features": features}
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(collection, fichier, ensure_ascii=False)


def reponse_api_mock(altitudes: list[float]) -> list[dict[str, Any]]:
    """Construit une reponse API IGN simulee."""
    return [{"z": z, "lon": 0.0, "lat": 0.0, "acc": 1.0} for z in altitudes]


def construire_feature_avec_proprietes(
    identifiant: str,
    type_geom: str,
    coordonnees: Any,
    proprietes: dict[str, Any],
) -> dict[str, Any]:
    """Construit une feature GeoJSON avec des proprietes personnalisees pour les tests."""
    return {
        "type": "Feature",
        "properties": {"id": identifiant, **proprietes},
        "geometry": {"type": type_geom, "coordinates": coordonnees},
    }


def lire_geojson_depuis(chemin: str) -> dict[str, Any]:
    """Lit et retourne le contenu d'un fichier GeoJSON de test."""
    with open(chemin, encoding="utf-8") as fichier:
        return json.load(fichier)
