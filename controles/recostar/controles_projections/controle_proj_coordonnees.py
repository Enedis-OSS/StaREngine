"""
Controle de coherence des coordonnees avec la projection declaree.

Verifie que les coordonnees de chaque entite GeoJSON sont coherentes avec
le systeme de reference de coordonnees (CRS) declare. Detecte les anomalies
suivantes :
- coordonnees hors de l'emprise valide du CRS
- valeurs non finies (NaN, infini) ou non numeriques
- CRS absent ou non interpretable empechant la verification

Utilise pyproj pour determiner l'emprise projetee de chaque CRS a partir
de sa zone d'utilisation geographique officielle.

Usage CLI :
    python controle_proj_coordonnees.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_proj_coordonnees.geojson
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from functools import lru_cache
from typing import Any, Sequence

from pyproj import CRS, Transformer

from controle_proj import (
    _obtenir_id_feature,
    extraire_code_epsg,
    lire_geojson,
    lister_fichiers_geojson,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_proj_coordonnees.geojson"

# Niveau de priorite affecte aux anomalies detectees
PRIORITE_ANOMALIE: str = "bloquant"

# Nombre de points echantillonnes par bord pour le calcul d'emprise
_NB_ECHANTILLONS_BORD: int = 8

# CRS geographique de reference pour les transformations
_CODE_WGS84: int = 4326

# Types d'anomalies detectees
TYPE_HORS_EMPRISE: str = "hors_emprise"
TYPE_COORDONNEE_INVALIDE: str = "coordonnee_invalide"
TYPE_CRS_INDETERMINE: str = "crs_indetermine"


# --------------------------------------------------------------------------- #
# Calcul de l'emprise projetee d'un CRS via pyproj
# --------------------------------------------------------------------------- #


def _transformer_et_collecter(
    transformeur: Transformer,
    lon: float,
    lat: float,
    coords_x: list[float],
    coords_y: list[float],
) -> None:
    """Transforme un point geographique et ajoute le resultat si fini."""
    try:
        px, py = transformeur.transform(lon, lat)
    except Exception:
        return
    if math.isfinite(px) and math.isfinite(py):
        coords_x.append(px)
        coords_y.append(py)


def _echantillonner_emprise(
    transformeur: Transformer,
    ouest: float,
    sud: float,
    est: float,
    nord: float,
) -> tuple[float, float, float, float] | None:
    """Echantillonne les bords geographiques et calcule l'emprise projetee.

    Transforme des points regulierement espaces le long des quatre bords
    de la zone d'utilisation geographique, puis determine l'enveloppe
    projetee.
    """
    coords_x: list[float] = []
    coords_y: list[float] = []
    nb = _NB_ECHANTILLONS_BORD
    collecteur = _transformer_et_collecter

    for i in range(nb + 1):
        t = i / nb
        lon_h = ouest + t * (est - ouest)
        lat_v = sud + t * (nord - sud)
        collecteur(transformeur, lon_h, sud, coords_x, coords_y)
        collecteur(transformeur, lon_h, nord, coords_x, coords_y)
        collecteur(transformeur, ouest, lat_v, coords_x, coords_y)
        collecteur(transformeur, est, lat_v, coords_x, coords_y)

    if len(coords_x) < 4:
        return None

    x_min, x_max = min(coords_x), max(coords_x)
    y_min, y_max = min(coords_y), max(coords_y)

    return (x_min, y_min, x_max, y_max)


@lru_cache(maxsize=32)
def obtenir_emprise_projetee(
    code_epsg: int,
) -> tuple[float, float, float, float] | None:
    """Calcule l'emprise projetee pour un code EPSG via pyproj.

    Utilise la zone d'utilisation officielle du CRS, la transforme en
    coordonnees projetees.

    Retourne (x_min, y_min, x_max, y_max) ou None si indeterminable.
    Le resultat est mis en cache pour eviter les recalculs.
    """
    try:
        crs_proj = CRS.from_epsg(code_epsg)
    except Exception:
        return None

    zone = crs_proj.area_of_use
    if zone is None:
        return None

    ouest, sud, est, nord = zone.bounds

    try:
        transformeur = Transformer.from_crs(
            CRS.from_epsg(_CODE_WGS84), crs_proj, always_xy=True
        )
    except Exception:
        return None

    return _echantillonner_emprise(transformeur, ouest, sud, est, nord)


# --------------------------------------------------------------------------- #
# Extraction indexee des sommets d'une geometrie GeoJSON
# --------------------------------------------------------------------------- #


def _indexer_anneaux(
    anneaux: list[list[Sequence[float]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste d'anneaux ou de lignes."""
    resultat: list[tuple[int, Sequence[float]]] = []
    indice = 0
    for anneau in anneaux:
        for point in anneau:
            resultat.append((indice, point))
            indice += 1
    return resultat


def _indexer_polygones(
    polygones: list[list[list[Sequence[float]]]],
) -> list[tuple[int, Sequence[float]]]:
    """Indexe sequentiellement les points d'une liste de polygones."""
    anneaux_aplatis: list[list[Sequence[float]]] = []
    for polygone in polygones:
        anneaux_aplatis.extend(polygone)
    return _indexer_anneaux(anneaux_aplatis)


# Correspondance type de geometrie -> fonction d'extraction indexee
_EXTRACTEURS: dict[str, Any] = {
    "Point": lambda coords: [(0, coords)],
    "LineString": lambda coords: list(enumerate(coords)),
    "MultiPoint": lambda coords: list(enumerate(coords)),
    "Polygon": _indexer_anneaux,
    "MultiLineString": _indexer_anneaux,
    "MultiPolygon": _indexer_polygones,
}


def extraire_points_indexes(
    geometrie: dict[str, Any],
) -> list[tuple[int, Sequence[float]]]:
    """Extrait les sommets d'une geometrie avec leur indice sequentiel.

    Retourne une liste de tuples (indice, coordonnees) couvrant tous les
    sommets de la geometrie, quel que soit son type. L'indice est continu
    et demarre a 0 pour chaque geometrie.
    """
    coordonnees = geometrie.get("coordinates")
    if coordonnees is None:
        return []

    extracteur = _EXTRACTEURS.get(geometrie.get("type", ""))
    if extracteur is None:
        return []
    return extracteur(coordonnees)


# --------------------------------------------------------------------------- #
# Validation des coordonnees par rapport a l'emprise
# --------------------------------------------------------------------------- #


def est_valeur_finie(valeur: object) -> bool:
    """Verifie qu'une valeur est un nombre fini (int ou float, ni NaN ni inf)."""
    if not isinstance(valeur, (int, float)):
        return False
    return math.isfinite(valeur)


def verifier_point(
    coordonnees: Sequence[float],
    emprise: tuple[float, float, float, float],
) -> str | None:
    """Verifie la coherence d'un point avec l'emprise du CRS.

    Retourne le type d'anomalie detectee ou None si le point est conforme.
    Seules les composantes X et Y sont verifiees (Z est libre).
    """
    if len(coordonnees) < 2:
        return TYPE_COORDONNEE_INVALIDE

    x, y = coordonnees[0], coordonnees[1]

    if not est_valeur_finie(x) or not est_valeur_finie(y):
        return TYPE_COORDONNEE_INVALIDE

    x_min, y_min, x_max, y_max = emprise
    if x < x_min or x > x_max or y < y_min or y > y_max:
        return TYPE_HORS_EMPRISE

    return None


# --------------------------------------------------------------------------- #
# Detection des anomalies par feature et par collection
# --------------------------------------------------------------------------- #


def detecter_anomalies_feature(
    feature: dict[str, Any],
    emprise: tuple[float, float, float, float],
    nom_fichier: str,
) -> tuple[list[dict[str, Any]], int]:
    """Detecte les anomalies de coordonnees dans une feature GeoJSON.

    Retourne un tuple (anomalies, nombre_sommets_verifies).
    """
    geometrie = feature.get("geometry")
    if geometrie is None:
        return [], 0

    identifiant = _obtenir_id_feature(feature)
    type_geom = geometrie.get("type", "inconnu")
    points = extraire_points_indexes(geometrie)

    anomalies: list[dict[str, Any]] = []
    verificateur = verifier_point
    for indice, point in points:
        type_anomalie = verificateur(point, emprise)
        if type_anomalie is None:
            continue
        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": identifiant,
                "type_geometrie": type_geom,
                "indice_sommet": indice,
                "coordonnees": list(point),
                "type_anomalie": type_anomalie,
            }
        )

    return anomalies, len(points)


def detecter_anomalies_collection(
    features: list[dict[str, Any]],
    emprise: tuple[float, float, float, float],
    nom_fichier: str,
) -> tuple[list[dict[str, Any]], int]:
    """Analyse une collection de features et retourne les anomalies.

    Retourne un tuple (anomalies, nombre_sommets_verifies).
    """
    anomalies: list[dict[str, Any]] = []
    nombre_sommets = 0
    for feature in features:
        anomalies_feature, nb = detecter_anomalies_feature(
            feature, emprise, nom_fichier
        )
        anomalies.extend(anomalies_feature)
        nombre_sommets += nb
    return anomalies, nombre_sommets


def creer_anomalie_crs_indetermine(
    nom_fichier: str,
) -> dict[str, Any]:
    """Cree une anomalie pour un fichier dont le CRS ne permet pas la verification."""
    return {
        "fichier_source": nom_fichier,
        "id_entite": None,
        "type_geometrie": None,
        "indice_sommet": None,
        "coordonnees": None,
        "type_anomalie": TYPE_CRS_INDETERMINE,
    }


# --------------------------------------------------------------------------- #
# Construction du GeoJSON de sortie
# --------------------------------------------------------------------------- #


def _construire_geometrie_anomalie(
    coordonnees: list[float] | None,
) -> dict[str, Any] | None:
    """Construit la geometrie Point pour une anomalie, ou None si indisponible."""
    if coordonnees is None:
        return None
    return {"type": "Point", "coordinates": coordonnees}


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des anomalies de coordonnees detectees.

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
                "indice_sommet": a["indice_sommet"],
                "type_anomalie": a["type_anomalie"],
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": _construire_geometrie_anomalie(a["coordonnees"]),
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def _ecrire_geojson(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un FeatureCollection GeoJSON sur disque."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Controle d'un fichier individuel
# --------------------------------------------------------------------------- #


def controler_fichier(
    collection: dict[str, Any],
    nom_fichier: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Controle la coherence des coordonnees d'un fichier GeoJSON.

    Retourne un tuple (anomalies, detail) ou detail contient les
    statistiques du controle pour ce fichier.
    """
    code_epsg = extraire_code_epsg(collection)
    features = collection.get("features", [])

    if code_epsg is None:
        anomalie = creer_anomalie_crs_indetermine(nom_fichier)
        detail = _construire_detail(nom_fichier, None, 0, 1, "crs_indetermine")
        return [anomalie], detail

    emprise = obtenir_emprise_projetee(code_epsg)
    if emprise is None:
        anomalie = creer_anomalie_crs_indetermine(nom_fichier)
        detail = _construire_detail(
            nom_fichier, code_epsg, 0, 1, "emprise_indeterminee"
        )
        return [anomalie], detail

    anomalies, nb_sommets = detecter_anomalies_collection(
        features, emprise, nom_fichier
    )
    statut = "conforme" if not anomalies else "anomalies_detectees"
    detail = _construire_detail(
        nom_fichier, code_epsg, nb_sommets, len(anomalies), statut
    )
    return anomalies, detail


def _construire_detail(
    nom_fichier: str,
    code_epsg: int | None,
    nb_sommets: int,
    nb_anomalies: int,
    statut: str,
) -> dict[str, Any]:
    """Construit le dictionnaire de detail pour un fichier analyse."""
    return {
        "fichier": nom_fichier,
        "code_epsg": code_epsg,
        "nb_sommets": nb_sommets,
        "nb_anomalies": nb_anomalies,
        "statut": statut,
    }


# --------------------------------------------------------------------------- #
# Orchestration CLI
# --------------------------------------------------------------------------- #


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de coherence des coordonnees en mode CLI.

    Parcourt tous les GeoJSON du repertoire, verifie la coherence
    des coordonnees avec le CRS declare et ecrit le fichier d'ecarts.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    fichiers = lister_fichiers_geojson(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier GeoJSON dans le repertoire"}

    toutes_anomalies: list[dict[str, Any]] = []
    detail_fichiers: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        if crs is None:
            crs = collection.get("crs")

        anomalies, detail = controler_fichier(collection, nom_fichier)
        toutes_anomalies.extend(anomalies)
        detail_fichiers.append(detail)

    geojson_ecarts = construire_geojson_ecarts(toutes_anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    fichiers_conformes = sum(1 for d in detail_fichiers if d["statut"] == "conforme")
    return {
        "succes": True,
        "fichiers_analyses": len(detail_fichiers),
        "fichiers_conformes": fichiers_conformes,
        "fichiers_non_conformes": len(detail_fichiers) - fichiers_conformes,
        "nombre_anomalies": len(toutes_anomalies),
        "sortie": chemin_sortie,
        "detail": detail_fichiers,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence des coordonnees."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle de coherence des coordonnees "
            "avec la projection declaree dans les fichiers GeoJSON"
        )
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
