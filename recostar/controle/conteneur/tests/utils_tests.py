"""Utilitaires partages entre les fichiers de tests des controles de conteneur."""

import json
from typing import Any


def construire_feature_jonction(
    identifiant: str,
    statut: str = "UnderCommissionning",
    type_jonction: str = "Jonction",
    domaine_tension: Any = "HTA",
    materiel_href: Any = None,
    coordonnees: list[float] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON Point representant une jonction.

    proprietes_extra permet de simuler les champs additionnels d'une version
    donnee (ex. Commentaire en V1.1) sans modifier le comportement du controle.
    """
    proprietes: dict[str, Any] = {
        "id": identifiant,
        "Statut": statut,
        "TypeJonction": type_jonction,
        "DomaineTension": domaine_tension,
        "materiel_href": materiel_href,
    }
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": {"type": "Point", "coordinates": coordonnees or [0.0, 0.0, 0.0]},
    }


def construire_feature_materiel(
    identifiant: str,
    fabricant: Any = None,
    modele: Any = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit une feature GeoJSON representant un materiel.

    RPD_Materiel_Reco n'a pas de geometrie propre : le champ `geometry` est nul,
    conformement a l'export RecoStaR.
    """
    proprietes: dict[str, Any] = {
        "id": identifiant,
        "Fabricant": fabricant,
        "Modele": modele,
    }
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {"type": "Feature", "properties": proprietes, "geometry": None}


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
