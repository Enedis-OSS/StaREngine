"""
Controle de la coherence entre les elements de terre.

Verifie que chaque cable terre possede une relation valide avec un noeud terre
via le champ noeudreseau_href, et que chaque cable terre possede un identifiant.

Ce controle est bloquant : aucun export ne doit etre possible si une anomalie
est detectee.

Usage CLI : python controle_coherence_terre.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_coherence_terre.json + ecarts_coherence_terre.geojson
"""

import argparse
import json
import os
import sys
from typing import Any

# Fichiers GeoJSON concernes
FICHIER_CABLES_TERRE: str = "RPD_CableTerre_Reco.geojson"
FICHIER_NOEUDS_TERRE: str = "RPD_Terre_Reco.geojson"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_coherence_terre.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_coherence_terre.geojson"


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne son contenu. Retourne None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def extraire_ids_noeuds_terre(features_noeuds: list[dict[str, Any]]) -> frozenset[str]:
    """Extrait l'ensemble des identifiants des noeuds terre."""
    ids: set[str] = set()
    for noeud in features_noeuds:
        id_val = noeud.get("properties", {}).get("id")
        if id_val is not None:
            ids.add(str(id_val))
    return frozenset(ids)


def controler_coherence_terre(
    features_cables: list[dict[str, Any]],
    ids_noeuds: frozenset[str],
) -> list[dict[str, Any]]:
    """Verifie que chaque cable terre est lie a un noeud terre existant.

    Regles :
    - Chaque cable terre doit posseder un identifiant (champ id).
    - Chaque cable terre doit avoir un noeudreseau_href referencant
      un identifiant present dans les noeuds terre.

    Retourne la liste des anomalies (vide si conforme).
    """
    anomalies: list[dict[str, Any]] = []

    for cable in features_cables:
        props = cable.get("properties", {})
        id_cable = props.get("id")

        # Cable sans identifiant
        if id_cable is None:
            anomalies.append(
                {
                    "id_cable": None,
                    "type": "cable_terre_sans_identifiant",
                    "message": "Cable terre sans identifiant",
                }
            )
            continue

        id_cable_str = str(id_cable)
        noeud_href = props.get("noeudreseau_href")

        # Cable sans reference vers un noeud terre
        if noeud_href is None or str(noeud_href) not in ids_noeuds:
            anomalies.append(
                {
                    "id_cable": id_cable_str,
                    "type": "cable_terre_sans_noeud_terre",
                    "message": (
                        f"Le cable terre {id_cable_str} n'est lie "
                        "a aucun noeud terre"
                    ),
                    "noeudreseau_href": noeud_href,
                }
            )

    return anomalies


def construire_rapport_json(
    anomalies: list[dict[str, Any]],
    nombre_cables: int,
    nombre_noeuds: int,
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle de coherence terre."""
    return {
        "controle": "coherence_terre",
        "bloquant": len(anomalies) > 0,
        "nombre_cables_terre": nombre_cables,
        "nombre_noeuds_terre": nombre_noeuds,
        "nombre_anomalies": len(anomalies),
        "anomalies": anomalies,
    }


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des anomalies detectees.

    Chaque anomalie est representee par une feature sans geometrie.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = []

    for anomalie in anomalies:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id_cable": anomalie.get("id_cable"),
                    "type_anomalie": anomalie.get("type", ""),
                    "message": anomalie.get("message", ""),
                    "priorite": "bloquant",
                },
                "geometry": None,
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
    """Execute le controle de coherence terre en mode CLI.

    Charge les GeoJSON depuis le repertoire, execute le controle,
    et ecrit les fichiers de sortie (rapport JSON + GeoJSON des ecarts).
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    # Chargement des cables terre
    chemin_cables = os.path.join(repertoire, FICHIER_CABLES_TERRE)
    collection_cables = lire_geojson(chemin_cables)
    features_cables: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    if collection_cables is not None:
        features_cables = collection_cables.get("features", [])
        crs = collection_cables.get("crs")

    # Chargement des noeuds terre
    chemin_noeuds = os.path.join(repertoire, FICHIER_NOEUDS_TERRE)
    collection_noeuds = lire_geojson(chemin_noeuds)
    features_noeuds: list[dict[str, Any]] = []
    if collection_noeuds is not None:
        features_noeuds = collection_noeuds.get("features", [])
        if crs is None:
            crs = collection_noeuds.get("crs")

    # Extraction des identifiants des noeuds terre
    ids_noeuds = extraire_ids_noeuds_terre(features_noeuds)

    # Controle de coherence
    anomalies = controler_coherence_terre(features_cables, ids_noeuds)

    # Generation du rapport JSON
    rapport = construire_rapport_json(
        anomalies, len(features_cables), len(features_noeuds)
    )
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    # Generation du GeoJSON des ecarts
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)
    chemin_ecarts = os.path.join(dossier_sortie, FICHIER_ECARTS_GEOJSON)
    _ecrire_json(geojson_ecarts, chemin_ecarts)

    return {"succes": True, "rapport": chemin_rapport, "ecarts": chemin_ecarts}


def main() -> None:
    """Point d'entree CLI du controle de coherence terre."""
    parseur = argparse.ArgumentParser(
        description="Controle de coherence entre noeuds terre et cables terre"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant "
        + FICHIER_CABLES_TERRE
        + " et "
        + FICHIER_NOEUDS_TERRE,
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
