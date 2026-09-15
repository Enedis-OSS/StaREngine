"""
Controle de conformite 3D des entites GeoJSON.

Verifie que toutes les entites geometriques d'un ensemble de fichiers GeoJSON
possedent des coordonnees 3D (X, Y, Z). Les entites ne possedant pas de
composante Z sont signalees et exportees dans un fichier GeoJSON d'ecarts.

"""

from collections.abc import Sequence
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    obtenir_id_feature,
)


def _aplatir_anneaux(coordonnees: list[Any]) -> list[Sequence[float]]:
    """Aplatit une liste d'anneaux ou de lignes en liste de points."""
    points: list[Sequence[float]] = []
    for anneau in coordonnees:
        points.extend(anneau)
    return points


def _aplatir_polygones(coordonnees: list[Any]) -> list[Sequence[float]]:
    """Aplatit une liste de polygones en liste de points (deux niveaux)."""
    points: list[Sequence[float]] = []
    for polygone in coordonnees:
        for anneau in polygone:
            points.extend(anneau)
    return points


# Correspondance type de geometrie -> extracteur de points (sans indice)
_EXTRACTEURS: dict[str, Any] = {
    "Point": lambda c: [c],
    "LineString": lambda c: list(c),
    "MultiPoint": lambda c: list(c),
    "Polygon": _aplatir_anneaux,
    "MultiLineString": _aplatir_anneaux,
    "MultiPolygon": _aplatir_polygones,
}


def _extraire_points_geometrie(geometrie: dict[str, Any]) -> list[Sequence[float]]:
    """Extrait la liste plate de tous les points d'une geometrie GeoJSON.

    Retourne une liste vide si la geometrie est absente ou de type inconnu.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []
    extracteur = _EXTRACTEURS.get(geometrie.get("type", ""))
    if extracteur is None:
        return []
    return extracteur(coordonnees)


def _entite_est_2d(geometrie: dict[str, Any]) -> bool:
    """Determine si une geometrie contient au moins un point sans composante Z.

    Retourne False si la geometrie est vide ou absente (rien a signaler).
    """
    points = _extraire_points_geometrie(geometrie)
    if not points:
        return False
    return any(len(point) < 3 for point in points)


def detecter_entites_2d(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Analyse les features et retourne les anomalies 2D detectees.

    Chaque anomalie contient le fichier source, l'identifiant de l'entite,
    le type de geometrie et la geometrie originale pour localisation.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        if not _entite_est_2d(geometrie):
            continue
        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": obtenir_id_feature(feature),
                "type_geometrie": geometrie.get("type", "inconnu"),
                "geometrie": geometrie,
            }
        )
    return anomalies
