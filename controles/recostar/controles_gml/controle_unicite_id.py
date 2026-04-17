"""
Controle de l'unicite des identifiants dans les fichiers GeoJSON.

Verifie que tous les objets presents dans les fichiers GeoJSON prefixes
par RPD_ possedent un identifiant unique. Les doublons sont signales
comme anomalies bloquantes.

Ce controle est bloquant : aucun export ne doit etre possible si un
doublon d'identifiant est detecte.

Usage CLI : python controle_unicite_id.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_unicite_id.json + ecarts_unicite_id.geojson
"""

import argparse
import json
import os
import sys
from typing import Any

# Prefixe des fichiers GeoJSON a controler
PREFIXE_FICHIER: str = "RPD_"
SUFFIXE_FICHIER: str = ".geojson"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_unicite_id.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_unicite_id.geojson"


def lister_fichiers_rpd(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON prefixes par RPD_ dans le repertoire.

    Retourne les noms de fichiers tries par ordre alphabetique.
    """
    if not os.path.isdir(repertoire):
        return []
    return sorted(
        nom
        for nom in os.listdir(repertoire)
        if nom.startswith(PREFIXE_FICHIER) and nom.endswith(SUFFIXE_FICHIER)
    )


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne son contenu. Retourne None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def collecter_ids_et_doublons(
    repertoire: str,
    fichiers: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], int, dict[str, Any] | None]:
    """Parcourt les fichiers et collecte les occurrences de chaque identifiant.

    Retourne :
    - un dictionnaire id -> liste de (nom_fichier, feature) pour les ids dupliques
    - le nombre total de features analysees
    - le CRS du premier fichier charge (pour propagation dans le GeoJSON de sortie)
    """
    # Premiere passe : collecter toutes les occurrences de chaque id
    occurrences: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    total_features = 0
    crs: dict[str, Any] | None = None

    for nom_fichier in fichiers:
        chemin = os.path.join(repertoire, nom_fichier)
        collection = lire_geojson(chemin)
        if collection is None:
            continue

        if crs is None:
            crs = collection.get("crs")

        features = collection.get("features", [])
        total_features += len(features)

        for feature in features:
            id_val = feature.get("properties", {}).get("id")
            if id_val is None:
                continue

            id_str = str(id_val)
            occurrences.setdefault(id_str, []).append((nom_fichier, feature))

    # Seconde passe : ne conserver que les ids avec plus d'une occurrence
    doublons: dict[str, list[dict[str, Any]]] = {}
    for id_str, liste_occurrences in occurrences.items():
        if len(liste_occurrences) > 1:
            doublons[id_str] = [
                {"nom_fichier": nom, "feature": feat} for nom, feat in liste_occurrences
            ]

    return doublons, total_features, crs


def construire_anomalies(
    doublons: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Construit la liste des anomalies a partir des doublons detectes.

    Chaque anomalie correspond a un identifiant duplique et regroupe
    toutes les occurrences (fichier source et geometrie).
    """
    anomalies: list[dict[str, Any]] = []

    for id_str, occurrences in doublons.items():
        fichiers_sources = [occ["nom_fichier"] for occ in occurrences]
        anomalies.append(
            {
                "id_duplique": id_str,
                "type": "id_duplique",
                "nombre_occurrences": len(occurrences),
                "fichiers": fichiers_sources,
                "message": (
                    f"L'identifiant {id_str} est present "
                    f"{len(occurrences)} fois dans : "
                    + ", ".join(sorted(set(fichiers_sources)))
                ),
                "occurrences": occurrences,
            }
        )

    return anomalies


def construire_rapport_json(
    anomalies: list[dict[str, Any]],
    nombre_fichiers: int,
    nombre_features: int,
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle d'unicite."""
    nombre_doublons = sum(a["nombre_occurrences"] for a in anomalies)
    return {
        "controle": "unicite_id",
        "bloquant": len(anomalies) > 0,
        "nombre_fichiers_analyses": nombre_fichiers,
        "nombre_features_total": nombre_features,
        "nombre_ids_dupliques": len(anomalies),
        "nombre_occurrences_doublons": nombre_doublons,
        "nombre_anomalies": len(anomalies),
        "anomalies": [
            {
                "id_duplique": a["id_duplique"],
                "nombre_occurrences": a["nombre_occurrences"],
                "fichiers": a["fichiers"],
                "message": a["message"],
            }
            for a in anomalies
        ],
    }


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des entites avec ID duplique.

    Chaque occurrence d'un doublon est representee comme une feature
    individuelle, conservant sa geometrie d'origine.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = []

    for anomalie in anomalies:
        id_duplique = anomalie["id_duplique"]
        message = anomalie["message"]

        for occurrence in anomalie["occurrences"]:
            feature_source = occurrence["feature"]
            geometrie = feature_source.get("geometry")

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id_duplique": id_duplique,
                        "fichier_source": occurrence["nom_fichier"],
                        "type_anomalie": "id_duplique",
                        "message": message,
                        "priorite": "bloquant",
                    },
                    "geometry": geometrie,
                }
            )

    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def _ecrire_json(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un dictionnaire au format JSON dans un fichier."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle d'unicite des identifiants en mode CLI.

    Parcourt tous les fichiers RPD_*.geojson du repertoire, detecte les
    doublons d'identifiants, et ecrit les fichiers de sortie.
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    # Lister les fichiers a analyser
    fichiers = lister_fichiers_rpd(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier RPD_*.geojson trouve"}

    # Collecter les doublons
    doublons, total_features, crs = collecter_ids_et_doublons(repertoire, fichiers)

    # Construire les anomalies
    anomalies = construire_anomalies(doublons)

    # Generation du rapport JSON
    rapport = construire_rapport_json(anomalies, len(fichiers), total_features)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    # Generation du GeoJSON des ecarts
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)
    chemin_ecarts = os.path.join(dossier_sortie, FICHIER_ECARTS_GEOJSON)
    _ecrire_json(geojson_ecarts, chemin_ecarts)

    return {"succes": True, "rapport": chemin_rapport, "ecarts": chemin_ecarts}


def main() -> None:
    """Point d'entree CLI du controle d'unicite des identifiants."""
    parseur = argparse.ArgumentParser(
        description="Controle de l'unicite des identifiants dans les GeoJSON RPD_"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers RPD_*.geojson",
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
