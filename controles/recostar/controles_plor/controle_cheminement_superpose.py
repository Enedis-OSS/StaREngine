"""
Controle des superpositions de cheminements.

Detecte les superpositions totales ou partielles entre les entites
lineaires des fichiers de cheminement :
- RPD_Fourreau_Reco.geojson
- RPD_PleineTerre_Reco.geojson
- RPD_ProtectionMecanique_Reco.geojson

Deux entites sont considerees comme superposees si elles partagent au
moins un segment geometrique commun (deux sommets consecutifs identiques
en X, Y, Z).

Usage CLI :
    python controle_cheminement_superpose.py --repertoire <chemin> [--sortie <chemin>]

Sortie : cheminement_superpose.geojson
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Fichiers de cheminement a analyser
FICHIERS_CHEMINEMENTS: tuple[str, ...] = (
    "RPD_Fourreau_Reco.geojson",
    "RPD_PleineTerre_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "cheminement_superpose.geojson"

# Niveau de priorite affecte aux superpositions detectees
PRIORITE_ANOMALIE: str = "bloquant"

# Alias de type pour un segment normalise
Segment = tuple[tuple[float, ...], tuple[float, ...]]


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Charge un fichier GeoJSON et retourne son contenu ou None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def _obtenir_id_feature(feature: dict[str, Any]) -> str | None:
    """Retourne l'identifiant metier d'une feature GeoJSON."""
    proprietes = feature.get("properties") or {}
    valeur = proprietes.get("id")
    if isinstance(valeur, (str, int)):
        return str(valeur)
    return None


def _normaliser_segment(
    point_a: tuple[float, ...],
    point_b: tuple[float, ...],
) -> Segment:
    """Normalise un segment pour que (A, B) et (B, A) soient identiques."""
    if point_a <= point_b:
        return (point_a, point_b)
    return (point_b, point_a)


def extraire_segments_ligne(
    coordonnees: list[list[float]],
) -> set[Segment]:
    """Extrait les segments normalises d'une sequence de coordonnees.

    Les segments degeneres (meme point de depart et d'arrivee) sont ignores.
    """
    segments: set[Segment] = set()
    for i in range(len(coordonnees) - 1):
        point_a = tuple(coordonnees[i])
        point_b = tuple(coordonnees[i + 1])
        if point_a == point_b:
            continue
        segments.add(_normaliser_segment(point_a, point_b))
    return segments


def _extraire_segments_multiligne(
    coordonnees: list[list[list[float]]],
) -> set[Segment]:
    """Extrait les segments normalises d'une MultiLineString."""
    segments: set[Segment] = set()
    for ligne in coordonnees:
        segments.update(extraire_segments_ligne(ligne))
    return segments


_EXTRACTEURS_SEGMENTS: dict[str, Any] = {
    "LineString": extraire_segments_ligne,
    "MultiLineString": _extraire_segments_multiligne,
}


def extraire_segments_feature(feature: dict[str, Any]) -> set[Segment]:
    """Extrait tous les segments normalises d'une feature GeoJSON.

    Supporte les geometries LineString et MultiLineString.
    Les autres types sont ignores (ensemble vide retourne).
    """
    geometrie = feature.get("geometry") or {}
    type_geo = geometrie.get("type")
    coordonnees = geometrie.get("coordinates")
    if type_geo is None or coordonnees is None:
        return set()
    extracteur = _EXTRACTEURS_SEGMENTS.get(type_geo)
    if extracteur is None:
        return set()
    return extracteur(coordonnees)


def indexer_segments(
    entrees: list[tuple[dict[str, Any], str]],
) -> dict[Segment, list[int]]:
    """Construit un index segment vers indices des entrees qui le contiennent."""
    index: dict[Segment, list[int]] = {}
    for idx, (feature, _) in enumerate(entrees):
        for segment in extraire_segments_feature(feature):
            references = index.get(segment)
            if references is None:
                references = []
                index[segment] = references
            references.append(idx)
    return index


def construire_carte_superpositions(
    index_segments: dict[Segment, list[int]],
) -> dict[int, set[int]]:
    """Associe chaque indice d'entree aux indices des entrees superposees."""
    carte: dict[int, set[int]] = {}
    for indices in index_segments.values():
        if len(indices) < 2:
            continue
        ensemble = set(indices)
        for idx in indices:
            existant = carte.get(idx)
            if existant is None:
                existant = set()
                carte[idx] = existant
            existant.update(ensemble)
            existant.discard(idx)
    return carte


def construire_anomalies(
    carte: dict[int, set[int]],
    entrees: list[tuple[dict[str, Any], str]],
) -> list[dict[str, Any]]:
    """Construit la liste des anomalies a partir de la carte de superpositions."""
    anomalies: list[dict[str, Any]] = []
    for idx in sorted(carte):
        feature, nom_fichier = entrees[idx]
        ids_superposes = [
            _obtenir_id_feature(entrees[i][0]) for i in sorted(carte[idx])
        ]
        anomalies.append(
            {
                "id_entite": _obtenir_id_feature(feature),
                "fichier_source": nom_fichier,
                "ids_superposes": ids_superposes,
                "feature": feature,
            }
        )
    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des cheminements superposes.

    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": anomalie["id_entite"],
                "fichier_source": anomalie["fichier_source"],
                "ids_superposes": ", ".join(
                    str(i) for i in anomalie["ids_superposes"] if i is not None
                ),
                "nb_superpositions": len(anomalie["ids_superposes"]),
                "type_anomalie": "superposition_cheminement",
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": anomalie["feature"].get("geometry"),
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


def charger_cheminements(
    repertoire: str,
) -> tuple[list[tuple[dict[str, Any], str]], dict[str, Any] | None, int]:
    """Charge les features de tous les fichiers de cheminement disponibles.

    Retourne le triplet (entrees, crs, nombre_fichiers_trouves).
    Les fichiers absents sont simplement ignores.
    """
    entrees: list[tuple[dict[str, Any], str]] = []
    crs: dict[str, Any] | None = None
    nb_fichiers = 0
    for nom_fichier in FICHIERS_CHEMINEMENTS:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        nb_fichiers += 1
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            entrees.append((feature, nom_fichier))
    return entrees, crs, nb_fichiers


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des superpositions de cheminements en mode CLI.

    Charge les fichiers de cheminement, indexe les segments, detecte les
    superpositions et ecrit le fichier de sortie.
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    dossier_sortie = sortie if sortie is not None else repertoire

    entrees, crs, nb_fichiers = charger_cheminements(repertoire)
    if nb_fichiers == 0:
        return {
            "succes": False,
            "erreur": f"Aucun fichier de cheminement trouve dans {repertoire}",
        }

    index = indexer_segments(entrees)
    carte = construire_carte_superpositions(index)
    anomalies = construire_anomalies(carte, entrees)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    _ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_entites": len(entrees),
        "nombre_fichiers": nb_fichiers,
        "nombre_anomalies": len(anomalies),
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle des superpositions de cheminements."""
    parseur = argparse.ArgumentParser(
        description="Controle des superpositions de cheminements"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON de cheminement",
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
