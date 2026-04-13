"""
Controle de conformite 3D des entites GeoJSON.

Verifie que toutes les entites geometriques d'un ensemble de fichiers GeoJSON
possedent des coordonnees 3D (X, Y, Z). Les entites ne possedant pas de
composante Z sont signalees et exportees dans un fichier GeoJSON d'ecarts.

Usage CLI :
    python controle_3d.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_3d.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_3d.geojson"

# Niveau de priorite affecte aux entites non conformes
PRIORITE_ANOMALIE: str = "information"

# Extension des fichiers analyses
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"

# Types de geometries supportes et leur chemin d'acces aux coordonnees brutes
_TYPES_SIMPLES: frozenset[str] = frozenset({"Point", "LineString", "Polygon"})
_TYPES_MULTI: frozenset[str] = frozenset(
    {"MultiPoint", "MultiLineString", "MultiPolygon"}
)


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def _extraire_points_geometrie(geometrie: dict[str, Any]) -> list[Sequence[float]]:
    """Extrait la liste plate de tous les points d'une geometrie GeoJSON.

    Retourne une liste vide si la geometrie est absente ou de type inconnu.
    """
    type_geom = geometrie.get("type", "")
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []

    if type_geom == "Point":
        return [coordonnees]

    if type_geom == "LineString" or type_geom == "MultiPoint":
        # Liste de points
        return coordonnees

    if type_geom == "Polygon" or type_geom == "MultiLineString":
        # Liste d'anneaux ou de lignes -> aplatir un niveau
        points: list[Sequence[float]] = []
        for anneau in coordonnees:
            points.extend(anneau)
        return points

    if type_geom == "MultiPolygon":
        # Liste de polygones -> aplatir deux niveaux
        points_mp: list[Sequence[float]] = []
        for polygone in coordonnees:
            for anneau in polygone:
                points_mp.extend(anneau)
        return points_mp

    return []


def _entite_est_2d(geometrie: dict[str, Any]) -> bool:
    """Determine si une geometrie contient au moins un point sans composante Z.

    Retourne False si la geometrie est vide ou absente (rien a signaler).
    """
    points = _extraire_points_geometrie(geometrie)
    if not points:
        return False

    for point in points:
        if len(point) < 3:
            return True
    return False


def lister_fichiers_geojson(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON eligibles dans le repertoire.

    Exclut les fichiers d'ecarts (prefixe 'ecarts_') pour eviter
    l'analyse des sorties de controles precedents.
    """
    fichiers: list[str] = []
    for nom in sorted(os.listdir(repertoire)):
        if not nom.lower().endswith(EXTENSION_GEOJSON):
            continue
        if nom.lower().startswith(PREFIXE_ECARTS):
            continue
        fichiers.append(nom)
    return fichiers


def _obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


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

        identifiant = _obtenir_id_feature(feature)
        type_geom = geometrie.get("type", "inconnu")

        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": identifiant,
                "type_geometrie": type_geom,
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
                "fichier_source": anomalie["fichier_source"],
                "id_entite": anomalie["id_entite"],
                "type_geometrie": anomalie["type_geometrie"],
                "type_anomalie": "absence_coordonnee_z",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": anomalie["geometrie"],
        }
        for anomalie in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def _ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle 3D en mode CLI.

    Parcourt tous les GeoJSON du repertoire, detecte les entites 2D
    et ecrit le fichier d'ecarts.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    fichiers = lister_fichiers_geojson(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    fichiers_analyses = 0
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        if crs is None:
            crs = collection.get("crs")

        features = collection.get("features", [])
        if not features:
            fichiers_analyses += 1
            continue

        anomalies = detecter_entites_2d(features, nom_fichier)
        toutes_anomalies.extend(anomalies)
        fichiers_analyses += 1

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(toutes_anomalies),
        "fichiers_analyses": fichiers_analyses,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de conformite 3D."""
    parseur = argparse.ArgumentParser(
        description="Controle de conformite 3D des entites GeoJSON"
    )
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
