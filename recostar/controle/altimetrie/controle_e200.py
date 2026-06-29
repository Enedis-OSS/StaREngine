"""
Controle de conformite 3D des entites GeoJSON.

Verifie que toutes les entites geometriques d'un ensemble de fichiers GeoJSON
possedent des coordonnees 3D (X, Y, Z). Les entites ne possedant pas de
composante Z sont signalees et exportees dans un fichier GeoJSON d'ecarts.

Usage CLI :
    python controle_e200.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_3d.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from utils_geojson import (
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_3d.geojson"

# Niveau de priorite affecte aux entites non conformes
PRIORITE_ANOMALIE: str = "bloquant"


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


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites non conformes en 3D.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "type_anomalie": "absence_coordonnee_z",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle 3D en mode CLI.

    Parcourt tous les GeoJSON du repertoire, detecte les entites 2D
    et ecrit le fichier d'ecarts.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    fichiers = lister_fichiers_geojson(repertoire_resolu)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_analyses = 0
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        features = collection.get("features", [])
        anomalies = detecter_entites_2d(features, nom_fichier)
        toutes_anomalies.extend(anomalies)
        fichiers_analyses += 1

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(toutes_anomalies),
        "fichiers_analyses": fichiers_analyses,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de conformite 3D."""
    parseur = argparse.ArgumentParser(description="Controle de conformite 3D des entites GeoJSON")
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON a analyser",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
