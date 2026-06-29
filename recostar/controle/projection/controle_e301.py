"""
Controle de coherence spatiale des entites GeoJSON.

Identifie les entites dont la position est anormalement eloignee du reste
des donnees de l'ensemble du jeu de donnees Recostar. Chaque entite est
representee par son centroide (moyenne de ses coordonnees). La detection
repose sur la methode de Tukey : les entites dont la distance au point
median spatial depasse Q3 + 1,5 × IQR sont signalee en anomalie.

Le point de reference est le median spatial (mediane independante de X et Y),
insensible aux valeurs aberrantes, contrairement a la moyenne arithmetique.

Prerequis : les coordonnees doivent etre dans une projection en metres.
Ce point est verifie via pyproj lorsque le champ crs est present.

Usage CLI :
    python controle_e301.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_coherence_spatiale.geojson
"""

import argparse
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any

from pyproj import CRS
from utils_geojson import (
    ecrire_geojson,
    lire_geojson,
    lister_fichiers_geojson,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_coherence_spatiale.geojson"

# Niveau de priorite affecte aux entites aberrantes
PRIORITE_ANOMALIE: str = "bloquant"

# Nombre minimal d'entites pour une detection statistique significative
NB_ENTITES_MIN: int = 4


# Correspondance type de geometrie -> extracteur de paires (x, y)
_EXTRACTEURS_XY: dict[str, Any] = {
    "Point": lambda c: [(c[0], c[1])],
    "LineString": lambda c: [(pt[0], pt[1]) for pt in c],
    "MultiPoint": lambda c: [(pt[0], pt[1]) for pt in c],
    "Polygon": lambda c: [(pt[0], pt[1]) for pt in c[0]],
    "MultiLineString": lambda c: [(pt[0], pt[1]) for ligne in c for pt in ligne],
    "MultiPolygon": lambda c: [(pt[0], pt[1]) for poly in c for pt in poly[0]],
}


def _extraire_coordonnees_xy(
    geometrie: dict[str, Any],
) -> list[tuple[float, float]]:
    """Extrait toutes les paires (x, y) d'une geometrie GeoJSON."""
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []
    extracteur = _EXTRACTEURS_XY.get(geometrie.get("type", ""))
    if extracteur is None:
        return []
    return extracteur(coordonnees)


def _calculer_centroide(
    points: list[tuple[float, float]],
) -> tuple[float, float]:
    """Calcule le centroide (moyenne) d'une liste de points (x, y) non vide."""
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _extraire_point_representatif(
    geometrie: dict[str, Any],
) -> tuple[float, float] | None:
    """Retourne le centroide d'une geometrie comme point representatif.

    Retourne None si la geometrie est vide ou de type inconnu.
    """
    points = _extraire_coordonnees_xy(geometrie)
    if not points:
        return None
    return _calculer_centroide(points)


def extraire_points_representatifs(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Extrait les centroides de toutes les entites d'une collection GeoJSON.

    Les entites sans geometrie ou de type inconnu sont ignorees.
    Retourne une liste de dictionnaires portant les metadonnees de chaque entite.
    """
    donnees: list[dict[str, Any]] = []
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        point = _extraire_point_representatif(geometrie)
        if point is None:
            continue
        donnees.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": obtenir_id_feature(feature),
                "type_geometrie": geometrie.get("type", "inconnu"),
                "geometrie": geometrie,
                "x_rep": point[0],
                "y_rep": point[1],
            }
        )
    return donnees


def _calculer_seuil_iqr(distances: list[float]) -> float:
    """Calcule le seuil de Tukey (Q3 + 1,5 × IQR) sur une liste de distances."""
    quartiles = statistics.quantiles(distances, n=4)
    q1, q3 = quartiles[0], quartiles[2]
    return q3 + 1.5 * (q3 - q1)


def _valider_crs_projete(nom_crs: str) -> bool:
    """Verifie que le CRS est projete (coordonnees en metres) via pyproj.

    Un CRS projete garantit que les distances euclidiennes sont exprimees en metres.
    Retourne False si le CRS est geographique (en degres) ou non reconnu par pyproj.
    """
    try:
        return CRS(nom_crs).is_projected
    except Exception:
        return False


def detecter_anomalies_spatiales(
    donnees: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float]:
    """Detecte les entites spatialement aberrantes par la methode IQR de Tukey.

    Le point de reference est le median spatial (mediane independante de X et Y).
    Les entites dont la distance au median depasse le seuil IQR sont signalee.
    Retourne (anomalies, seuil_applique).
    """
    x_med = statistics.median(d["x_rep"] for d in donnees)
    y_med = statistics.median(d["y_rep"] for d in donnees)

    distances = [math.hypot(d["x_rep"] - x_med, d["y_rep"] - y_med) for d in donnees]
    seuil = _calculer_seuil_iqr(distances)

    anomalies: list[dict[str, Any]] = [
        {**d, "distance_m": round(distances[i], 2), "seuil_m": round(seuil, 2)}
        for i, d in enumerate(donnees)
        if distances[i] > seuil
    ]
    return anomalies, seuil


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des entites en ecart de coherence spatiale.

    La geometrie originale est conservee pour la localisation dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "fichier_source": a["fichier_source"],
                "id_entite": a["id_entite"],
                "type_geometrie": a["type_geometrie"],
                "distance_au_median_m": a["distance_m"],
                "seuil_m": a["seuil_m"],
                "type_anomalie": "position_aberrante",
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


def _collecter_donnees_spatiales(
    repertoire: str,
    fichiers: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Charge tous les GeoJSON eligibles et extrait les donnees spatiales.

    Retourne (donnees, crs_premier_fichier).
    """
    donnees: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        donnees.extend(extraire_points_representatifs(collection.get("features", []), nom_fichier))

    return donnees, crs


def _extraire_nom_crs(crs: dict[str, Any] | None) -> str | None:
    """Extrait le nom textuel du CRS depuis un objet crs GeoJSON."""
    if crs is None:
        return None
    return (crs.get("properties") or {}).get("name") or None


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de coherence spatiale en mode CLI.

    Charge les GeoJSON du repertoire, detecte les entites dont la position
    est aberrante par rapport au reste du jeu de donnees et ecrit le fichier
    de sortie.
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

    donnees, crs = _collecter_donnees_spatiales(repertoire_resolu, fichiers)

    # Verification que le CRS est projete (prerequis pour les distances euclidiennes)
    nom_crs = _extraire_nom_crs(crs)
    if nom_crs is not None and not _valider_crs_projete(nom_crs):
        return {
            "succes": False,
            "erreur": (f"CRS non projete ({nom_crs}) : les distances euclidiennes ne sont pas applicables en degres"),
        }

    if len(donnees) < NB_ENTITES_MIN:
        return {
            "succes": False,
            "erreur": (
                f"Nombre d'entites insuffisant ({len(donnees)} < {NB_ENTITES_MIN})"
                " pour une detection statistique fiable"
            ),
        }

    anomalies, seuil = detecter_anomalies_spatiales(donnees)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "entites_analysees": len(donnees),
        "fichiers_analyses": len(fichiers),
        "seuil_m": round(seuil, 2),
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence spatiale."""
    parseur = argparse.ArgumentParser(description="Controle de coherence spatiale des entites GeoJSON")
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
