"""
Controle des coordonnees Z nulles dans les entites GeoJSON.

Detecte les sommets dont l'altitude est exactement egale a 0.0 dans l'ensemble
des fichiers GeoJSON d'un repertoire. Chaque sommet concerne est exporte sous
forme de point dans un fichier GeoJSON d'ecarts, accompagne de ses metadonnees
de localisation (fichier source, identifiant, indice du sommet).

Les entites sans geometrie ou en 2D (sans composante Z) sont ignorees :
seuls les sommets 3D portant une valeur Z = 0.0 sont signales.

Usage CLI :
    python controle_z_null.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_z_null.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_z_null.geojson"

# Niveau de priorite affecte aux sommets signales
PRIORITE_ANOMALIE: str = "information"

# Extension des fichiers analyses
EXTENSION_GEOJSON: str = ".geojson"

# Prefixe des fichiers d'ecarts (exclus de l'analyse)
PREFIXE_ECARTS: str = "ecarts_"

# Valeur Z consideree comme nulle
Z_NULL: float = 0.0


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


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


def _extraire_points_indexes(
    geometrie: dict[str, Any],
) -> list[tuple[int, Sequence[float]]]:
    """Extrait les points d'une geometrie avec leur indice sequentiel.

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


def detecter_z_null_feature(
    feature: dict[str, Any],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Detecte les sommets a Z nul dans une feature GeoJSON.

    Seuls les sommets 3D (possedant une composante Z) sont inspectes.
    Un sommet 2D est ignore (relevant du controle 3D, pas de ce controle).
    """
    geometrie = feature.get("geometry")
    if geometrie is None:
        return []

    identifiant = _obtenir_id_feature(feature)
    type_geom = geometrie.get("type", "inconnu")
    points = _extraire_points_indexes(geometrie)

    anomalies: list[dict[str, Any]] = []
    for indice, point in points:
        # Ignorer les sommets 2D (pas de composante Z a verifier)
        if len(point) < 3:
            continue
        if point[2] != Z_NULL:
            continue
        anomalies.append(
            {
                "fichier_source": nom_fichier,
                "id_entite": identifiant,
                "type_geometrie": type_geom,
                "indice_sommet": indice,
                "coordonnees": list(point),
            }
        )

    return anomalies


def detecter_z_null_collection(
    features: list[dict[str, Any]],
    nom_fichier: str,
) -> list[dict[str, Any]]:
    """Analyse une collection de features et retourne toutes les anomalies Z nul."""
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        anomalies.extend(detecter_z_null_feature(feature, nom_fichier))
    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets a Z nul.

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
                "indice_sommet": anomalie["indice_sommet"],
                "z_detecte": Z_NULL,
                "type_anomalie": "z_null",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": {
                "type": "Point",
                "coordinates": anomalie["coordonnees"],
            },
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
    """Execute le controle des Z nuls en mode CLI.

    Parcourt tous les GeoJSON du repertoire, detecte les sommets a Z nul
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

        anomalies = detecter_z_null_collection(features, nom_fichier)
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
    """Point d'entree CLI du controle des coordonnees Z nulles."""
    parseur = argparse.ArgumentParser(
        description="Controle des coordonnees Z nulles dans les entites GeoJSON"
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
