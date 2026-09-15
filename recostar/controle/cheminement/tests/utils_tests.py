"""
Utilitaires partages entre les fichiers de tests du controle E-5108.
"""

import json
from typing import Any


def construire_feature_linestring(
    identifiant: str,
    coordonnees: list[list[float]],
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON LineString minimale pour les tests.

    `proprietes_extra` complete les proprietes de l'entite : il sert aux
    controles qui lisent un attribut metier sur le cheminement, `cables_href`
    au premier chef.
    """
    proprietes: dict[str, Any] = {"id": identifiant}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "LineString", "coordinates": coordonnees},
    }


def construire_feature_multilinestring(
    identifiant: str,
    coordonnees: list[list[list[float]]],
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON MultiLineString minimale pour les tests."""
    proprietes: dict[str, Any] = {"id": identifiant}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
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
