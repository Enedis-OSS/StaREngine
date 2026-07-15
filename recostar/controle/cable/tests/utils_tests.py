"""Utilitaires partages entre les fichiers de tests des controles de cable."""

import json
from typing import Any


def construire_feature_jonction(
    identifiant: str,
    domaine_tension: Any,
    cables_href: Any = None,
    coordonnees: list[float] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON Point representant une jonction.

    proprietes_extra permet de simuler les champs additionnels d'une version
    donnee (ex. Commentaire en V1.1) sans modifier le comportement du controle.
    """
    proprietes: dict[str, Any] = {
        "id": identifiant,
        "DomaineTension": domaine_tension,
        "cables_href": cables_href,
    }
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees or [0.0, 0.0]},
    }


def construire_feature_cable_electrique(
    identifiant: str,
    domaine_tension: Any,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON LineString representant un cable electrique."""
    proprietes: dict[str, Any] = {"id": identifiant, "DomaineTension": domaine_tension}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


def construire_feature_noeud(
    identifiant: str,
    cables_href: Any = None,
    coordonnees: list[float] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON Point representant un noeud du reseau.

    Utilisable pour n'importe quel type de noeud (jonction, support, terre...) :
    seuls cables_href et la geometrie interviennent dans le controle E506.
    """
    proprietes: dict[str, Any] = {"id": identifiant, "cables_href": cables_href}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees or [0.0, 0.0]},
    }


def construire_feature_cable_lineaire(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON LineString de geometrie libre.

    Complete construire_feature_cable_electrique lorsque le test porte sur la
    geometrie du cable (extremites) plutot que sur ses attributs metier.
    """
    proprietes: dict[str, Any] = {"id": identifiant}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {
            "type": "LineString",
            "coordinates": coordonnees or [[0.0, 0.0], [100.0, 0.0]],
        },
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
