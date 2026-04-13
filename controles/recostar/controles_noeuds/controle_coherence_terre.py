"""
Controle de la coherence entre les elements de terre.
Verifie que chaque noeud terre est lie a au moins un cable terre,
et que chaque cable terre est lie a au moins un noeud terre.

Ce controle est bloquant : aucun export ne doit etre possible si une anomalie
est detectee.

Usage CLI : python controle_coherence_terre.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_coherence_terre.json + ecarts_coherence_terre.geojson
"""

import argparse
import json
import math
import os
import sys
from typing import Any

SEUIL_DISTANCE: float = 0.5


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne son contenu. Retourne None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def obtenir_id_feature(feature: dict[str, Any]) -> str | int | None:
    """Retourne l'identifiant d'une feature GeoJSON."""
    props = feature.get("properties", {})
    id_val = props.get("id")
    if id_val is not None:
        return id_val
    return feature.get("id")


def extraire_coordonnees(feature: dict[str, Any]) -> list[float] | None:
    """Extrait les coordonnees d'une feature ponctuelle."""
    geometrie = feature.get("geometry")
    if geometrie is None:
        return None
    coords = geometrie.get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return None
    return coords


def calculer_distance_2d(coords1: list[float], coords2: list[float]) -> float:
    """Calcule la distance euclidienne 2D entre deux points."""
    dx = coords1[0] - coords2[0]
    dy = coords1[1] - coords2[1]
    return math.sqrt(dx * dx + dy * dy)


def extraire_extremites_cable(cable: dict[str, Any]) -> list[list[float]] | None:
    """Extrait les extremites (premier et dernier point) d'un cable LineString."""
    geometrie = cable.get("geometry", {})
    if geometrie.get("type") != "LineString":
        return None
    coords = geometrie.get("coordinates", [])
    if len(coords) < 2:
        return None
    return [coords[0], coords[-1]]


def extraire_ids_cables_href(feature: dict[str, Any]) -> set[str]:
    """Extrait les identifiants des cables references dans cables_href."""
    props = feature.get("properties", {})
    cables_href = props.get("cables_href")
    if cables_href is None:
        return set()
    if isinstance(cables_href, str):
        return {x.strip() for x in cables_href.split(",") if x.strip()}
    if not isinstance(cables_href, list):
        return set()
    ids: set[str] = set()
    for ref in cables_href:
        if isinstance(ref, str):
            ids.add(ref)
        elif isinstance(ref, (int, float)):
            ids.add(str(ref))
        elif isinstance(ref, dict):
            val = ref.get("id") or ref.get("href", "")
            if val:
                ids.add(str(val))
    return ids


def indexer_features_par_id(
    features: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Indexe une liste de features par leur identifiant (converti en chaine)."""
    index: dict[str, dict[str, Any]] = {}
    for feature in features:
        id_val = obtenir_id_feature(feature)
        if id_val is not None:
            index[str(id_val)] = feature
    return index


# Fichiers GeoJSON concernes
FICHIER_CABLES_TERRE: str = "RPD_CableTerre_Reco.geojson"
FICHIER_NOEUDS_TERRE: str = "RPD_Terre_Reco.geojson"

# Valeur de NatureTerre_href excluant un noeud du controle
NATURE_TERRE_EXCLUE: str = "TerreMasses"

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_coherence_terre.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_coherence_terre.geojson"


def _est_terre_masses(feature: dict[str, Any]) -> bool:
    """Verifie si un noeud terre est de nature TerreMasses (exclu du controle)."""
    nature = feature.get("properties", {}).get("NatureTerre_href")
    return nature == NATURE_TERRE_EXCLUE


def _filtrer_noeuds_terre_masses(
    features_noeuds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separe les noeuds terre en deux listes : a controler et exclus (TerreMasses).

    Retourne (noeuds_a_controler, noeuds_exclus).
    """
    noeuds_a_controler: list[dict[str, Any]] = []
    noeuds_exclus: list[dict[str, Any]] = []
    for noeud in features_noeuds:
        if _est_terre_masses(noeud):
            noeuds_exclus.append(noeud)
        else:
            noeuds_a_controler.append(noeud)
    return noeuds_a_controler, noeuds_exclus


def _noeud_est_proche_cable(
    coords_noeud: list[float],
    extremites_cable: list[list[float]],
) -> bool:
    """Verifie si un noeud est proche d'au moins une extremite d'un cable."""
    distance_2d = calculer_distance_2d
    seuil = SEUIL_DISTANCE
    for extremite in extremites_cable:
        if distance_2d(coords_noeud, extremite) <= seuil:
            return True
    return False


def _noeud_a_cable_terre_valide(
    coords_noeud: list[float],
    ids_cables_ref: set[str],
    cables_par_id: dict[str, dict[str, Any]],
) -> bool:
    """Verifie si un noeud terre est lie a au moins un cable terre valide."""
    for id_cable_ref in ids_cables_ref:
        cable = cables_par_id.get(id_cable_ref)
        if cable is None:
            continue

        extremites = extraire_extremites_cable(cable)
        if extremites is None:
            continue

        if _noeud_est_proche_cable(coords_noeud, extremites):
            return True
    return False


def _verifier_noeuds_terre_sans_cable(
    features_noeuds: list[dict[str, Any]],
    features_cables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verifie que chaque noeud terre est lie a au moins un cable terre.

    Un noeud est considere lie si :
    - Son cables_href reference un cable terre existant, ET
    - Ce cable possede une extremite a proximite du noeud
    """
    cables_par_id = indexer_features_par_id(features_cables)
    anomalies: list[dict[str, Any]] = []

    for noeud in features_noeuds:
        id_noeud = obtenir_id_feature(noeud)
        if id_noeud is None:
            continue

        coords_noeud = extraire_coordonnees(noeud)
        if coords_noeud is None:
            continue

        ids_cables_ref = extraire_ids_cables_href(noeud)

        if not _noeud_a_cable_terre_valide(coords_noeud, ids_cables_ref, cables_par_id):
            anomalies.append(
                {
                    "id_noeud": id_noeud,
                    "type": "noeud_terre_sans_cable_terre",
                    "message": f"Le noeud terre {id_noeud} n'est lie a aucun cable terre",
                    "coordonnees": coords_noeud,
                    "cables_href": list(ids_cables_ref),
                }
            )

    return anomalies


def _cable_a_noeud_terre_valide(
    id_cable_str: str,
    extremites: list[list[float]],
    noeuds_avec_coords: list[tuple[dict[str, Any], list[float], set[str]]],
) -> bool:
    """Verifie si un cable terre est reference par au moins un noeud terre proche."""
    for _noeud, coords_noeud, ids_cables_ref in noeuds_avec_coords:
        if id_cable_str not in ids_cables_ref:
            continue
        if _noeud_est_proche_cable(coords_noeud, extremites):
            return True
    return False


def _preparer_noeuds_avec_coords(
    features_noeuds: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[float], set[str]]]:
    """Prepare la liste des noeuds avec leurs coordonnees et cables references."""
    noeuds_avec_coords: list[tuple[dict[str, Any], list[float], set[str]]] = []
    for noeud in features_noeuds:
        coords = extraire_coordonnees(noeud)
        if coords is None:
            continue
        ids_cables = extraire_ids_cables_href(noeud)
        noeuds_avec_coords.append((noeud, coords, ids_cables))
    return noeuds_avec_coords


def _verifier_cables_terre_sans_noeud(
    features_cables: list[dict[str, Any]],
    features_noeuds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verifie que chaque cable terre est lie a au moins un noeud terre.

    Un cable est considere lie si un noeud terre :
    - Reference ce cable dans son cables_href, ET
    - Possede une position a proximite d'une extremite du cable
    """
    noeuds_avec_coords = _preparer_noeuds_avec_coords(features_noeuds)
    anomalies: list[dict[str, Any]] = []

    for cable in features_cables:
        id_cable = obtenir_id_feature(cable)
        if id_cable is None:
            continue

        extremites = extraire_extremites_cable(cable)
        if extremites is None:
            continue

        id_cable_str = str(id_cable)

        if not _cable_a_noeud_terre_valide(
            id_cable_str, extremites, noeuds_avec_coords
        ):
            anomalies.append(
                {
                    "id_cable": id_cable,
                    "type": "cable_terre_sans_noeud_terre",
                    "message": f"Le cable terre {id_cable} n'est lie a aucun noeud terre",
                    "extremites": extremites,
                }
            )

    return anomalies


def controler_coherence_terre(
    features_cables: list[dict[str, Any]],
    features_noeuds: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Execute le controle de coherence terre sur les features fournies.

    Les noeuds de nature TerreMasses sont exclus du controle de presence
    d'un cable terre, mais restent pris en compte cote cable (un cable
    lie a un noeud TerreMasses est considere valide).

    Retourne (anomalies, nombre_noeuds_exclus).
    """
    noeuds_a_controler, noeuds_exclus = _filtrer_noeuds_terre_masses(features_noeuds)
    nombre_exclus = len(noeuds_exclus)

    if len(features_cables) == 0 and len(noeuds_a_controler) == 0:
        return [], nombre_exclus

    anomalies: list[dict[str, Any]] = []

    if len(noeuds_a_controler) > 0:
        anomalies.extend(
            _verifier_noeuds_terre_sans_cable(noeuds_a_controler, features_cables)
        )

    if len(features_cables) > 0:
        # Tous les noeuds (y compris TerreMasses) restent valides cote cable
        anomalies.extend(
            _verifier_cables_terre_sans_noeud(features_cables, features_noeuds)
        )

    return anomalies, nombre_exclus


def construire_rapport_json(
    anomalies: list[dict[str, Any]],
    nombre_cables: int,
    nombre_noeuds: int,
    nombre_noeuds_exclus: int = 0,
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle de coherence terre."""
    bloquant = len(anomalies) > 0

    return {
        "controle": "coherence_terre",
        "bloquant": bloquant,
        "nombre_cables_terre": nombre_cables,
        "nombre_noeuds_terre": nombre_noeuds,
        "nombre_noeuds_exclus_terre_masses": nombre_noeuds_exclus,
        "nombre_anomalies": len(anomalies),
        "anomalies": anomalies,
    }


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des entites en anomalie.

    Les noeuds sont representes par des Points, les cables par leurs extremites.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = []

    for anomalie in anomalies:
        type_anomalie = anomalie.get("type", "")

        if type_anomalie == "noeud_terre_sans_cable_terre":
            coordonnees = anomalie.get("coordonnees", [0.0, 0.0, 0.0])
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id_noeud": anomalie.get("id_noeud", ""),
                        "type_anomalie": type_anomalie,
                        "message": anomalie.get("message", ""),
                        "priorite": "bloquant",
                    },
                    "geometry": {"type": "Point", "coordinates": coordonnees},
                }
            )

        elif type_anomalie == "cable_terre_sans_noeud_terre":
            extremites = anomalie.get("extremites", [])
            for extremite in extremites:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "id_cable": anomalie.get("id_cable", ""),
                            "type_anomalie": type_anomalie,
                            "message": anomalie.get("message", ""),
                            "priorite": "bloquant",
                        },
                        "geometry": {"type": "Point", "coordinates": extremite},
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

    # Controle de coherence
    anomalies, nombre_exclus = controler_coherence_terre(
        features_cables, features_noeuds
    )

    # Generation du rapport JSON
    rapport = construire_rapport_json(
        anomalies, len(features_cables), len(features_noeuds), nombre_exclus
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
