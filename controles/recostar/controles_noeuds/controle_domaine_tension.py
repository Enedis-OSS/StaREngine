"""
Controle de la coherence du domaine de tension entre cables et jonctions.
Verifie que le DomaineTension de chaque cable correspond a celui des jonctions
auxquelles il est connecte via cables_href.

Usage CLI : python controle_domaine_tension.py --repertoire <chemin> [--sortie <chemin>]
Sorties : rapport_controle_domaine_tension.json + ecarts_domaine_tension.geojson
"""

import argparse
import json
import math
import os
import sys
from typing import Any

SEUIL_DISTANCE: float = 0.5

FICHIERS_NOEUDS_AVEC_CABLES_HREF: list[str] = [
    "RPD_Jonction_Reco.geojson",
    "RPD_Support_Reco.geojson",
]


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


def cable_est_lie_dans_href(feature: dict[str, Any], id_cable: str | int) -> bool:
    """Verifie si un cable est reference dans le cables_href d'une feature."""
    ids = extraire_ids_cables_href(feature)
    return str(id_cable) in ids


# Fichiers GeoJSON concernes
FICHIER_CABLES: str = "RPD_CableElectrique_Reco.geojson"
FICHIER_JONCTIONS: str = FICHIERS_NOEUDS_AVEC_CABLES_HREF[0]

# Noms des fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_domaine_tension.json"
FICHIER_ECARTS_GEOJSON: str = "ecarts_domaine_tension.geojson"


def _jonction_est_proche(
    jonction: dict[str, Any],
    id_cable: str | int,
    coords_extremite: list[float],
) -> bool:
    """Verifie si une jonction est liee et proche d'une extremite de cable."""
    if not cable_est_lie_dans_href(jonction, id_cable):
        return False

    coords_jonction = extraire_coordonnees(jonction)
    if coords_jonction is None:
        return False

    return calculer_distance_2d(coords_extremite, coords_jonction) <= SEUIL_DISTANCE


def _extraire_info_tension(jonction: dict[str, Any]) -> dict[str, Any] | None:
    """Extrait l'identifiant et le domaine de tension d'une jonction.

    Retourne None si l'identifiant est absent ou la tension non renseignee.
    """
    id_jonction = obtenir_id_feature(jonction)
    if id_jonction is None:
        return None

    tension = jonction.get("properties", {}).get("DomaineTension")
    if not isinstance(tension, str):
        return None

    return {"id_jonction": id_jonction, "domaine_tension": tension}


def _trouver_jonctions_liees(
    cable: dict[str, Any],
    features_jonctions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Trouve toutes les jonctions liees a un cable via cables_href et proximite."""
    id_cable = obtenir_id_feature(cable)
    if id_cable is None:
        return []

    extremites = extraire_extremites_cable(cable)
    if extremites is None:
        return []

    jonctions_liees: list[dict[str, Any]] = []
    ids_vues: set[str] = set()

    for coords_extremite in extremites:
        for jonction in features_jonctions:
            if not _jonction_est_proche(jonction, id_cable, coords_extremite):
                continue

            info = _extraire_info_tension(jonction)
            if info is None:
                continue

            cle = str(info["id_jonction"])
            if cle in ids_vues:
                continue
            ids_vues.add(cle)

            jonctions_liees.append(info)

    return jonctions_liees


def _verifier_coherence_cable(
    cable: dict[str, Any],
    features_jonctions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Verifie la coherence du domaine de tension pour un cable.

    Retourne None si le cable n'a pas de domaine de tension ou aucun probleme.
    """
    id_cable = obtenir_id_feature(cable)
    if id_cable is None:
        return None

    tension_cable = cable.get("properties", {}).get("DomaineTension")
    if not isinstance(tension_cable, str):
        return None

    jonctions_liees = _trouver_jonctions_liees(cable, features_jonctions)

    problemes: list[dict[str, Any]] = []
    for jonction in jonctions_liees:
        if jonction["domaine_tension"] != tension_cable:
            problemes.append(
                {
                    "id_jonction": jonction["id_jonction"],
                    "tension_cable": tension_cable,
                    "tension_jonction": jonction["domaine_tension"],
                }
            )

    if len(problemes) == 0:
        return None

    return {"id_cable": id_cable, "problemes": problemes}


def controler_domaine_tension(
    cables: list[dict[str, Any]],
    features_jonctions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute le controle de coherence du domaine de tension.

    Retourne la liste des cables en incoherence.
    """
    resultats: list[dict[str, Any]] = []
    for cable in cables:
        resultat = _verifier_coherence_cable(cable, features_jonctions)
        if resultat is not None:
            resultats.append(resultat)
    return resultats


def construire_rapport_json(
    resultats: list[dict[str, Any]],
    nombre_cables: int,
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique du controle de domaine de tension."""
    nombre_incoherences = len(resultats)

    return {
        "controle": "domaine_tension",
        "nombre_cables": nombre_cables,
        "nombre_incoherences": nombre_incoherences,
        "resultats": resultats,
    }


def construire_geojson_ecarts(
    resultats: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un GeoJSON FeatureCollection des incoherences de tension.

    Chaque cable en incoherence est represente avec ses problemes en proprietes.
    Le champ crs est propage depuis le fichier source pour assurer
    l'affichage correct dans QGIS.
    """
    features: list[dict[str, Any]] = []

    for resultat in resultats:
        id_cable = resultat.get("id_cable", "")
        for probleme in resultat.get("problemes", []):
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id_cable": id_cable,
                        "id_jonction": probleme.get("id_jonction", ""),
                        "tension_cable": probleme.get("tension_cable", ""),
                        "tension_jonction": probleme.get("tension_jonction", ""),
                        "type_anomalie": "incoherence_domaine_tension",
                        "priorite": "bloquant",
                    },
                    "geometry": None,
                }
            )

    resultat_geojson: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
    }
    if crs is not None:
        resultat_geojson["crs"] = crs
    return resultat_geojson


def _ecrire_json(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un dictionnaire au format JSON dans un fichier."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de domaine de tension en mode CLI.

    Charge les GeoJSON depuis le repertoire, execute le controle,
    et ecrit les fichiers de sortie (rapport JSON + GeoJSON des ecarts).
    """
    dossier_sortie = sortie if sortie is not None else repertoire

    # Chargement des cables
    chemin_cables = os.path.join(repertoire, FICHIER_CABLES)
    collection_cables = lire_geojson(chemin_cables)
    if collection_cables is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_CABLES} introuvable dans {repertoire}",
        }

    cables = collection_cables.get("features", [])
    crs = collection_cables.get("crs")

    # Chargement des jonctions
    chemin_jonctions = os.path.join(repertoire, FICHIER_JONCTIONS)
    collection_jonctions = lire_geojson(chemin_jonctions)
    features_jonctions: list[dict[str, Any]] = []
    if collection_jonctions is not None:
        features_jonctions = collection_jonctions.get("features", [])

    # Controle de coherence du domaine de tension
    resultats = controler_domaine_tension(cables, features_jonctions)

    # Generation du rapport JSON
    rapport = construire_rapport_json(resultats, len(cables))
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    # Generation du GeoJSON des ecarts
    geojson_ecarts = construire_geojson_ecarts(resultats, crs)
    chemin_ecarts = os.path.join(dossier_sortie, FICHIER_ECARTS_GEOJSON)
    _ecrire_json(geojson_ecarts, chemin_ecarts)

    return {"succes": True, "rapport": chemin_rapport, "ecarts": chemin_ecarts}


def main() -> None:
    """Point d'entree CLI du controle de domaine de tension."""
    parseur = argparse.ArgumentParser(
        description="Controle de coherence du domaine de tension"
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant " + FICHIER_CABLES + " et " + FICHIER_JONCTIONS,
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
