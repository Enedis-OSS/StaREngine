"""
Controle E504 : densite de sommets des cables electriques.

Verifie que chaque cable electrique en cours de mise en service possede une
densite de sommets suffisante : aucun segment entre deux sommets consecutifs ne
doit depasser 15 metres (il existe donc au moins un sommet tous les 15 metres).

Perimetre :
  - Entites RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Les cables references par un cheminement aerien (RPD_Aerien_Reco.cables_href)
    sont exclus, conformement au comportement des controles E202 / E208.
  - Compatible RecoStaR V1.0 et V1.1 (geometries et mecanisme aerien identiques).

Regle : pour chaque cable controle, on parcourt les sommets dans l'ordre et on
calcule la distance 3D (convention du calcul de longueur du projet) entre sommets
consecutifs. Si un segment est strictement superieur a 15 metres, le cable est
non conforme et genere une anomalie E504.

Usage CLI :
    python controle_e504.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_densite_sommets_cable.geojson
"""

import argparse
import json
import math
import os
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

from utils_cable import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature
from utils_geometrie import extraire_parties_lineaires

# Fichier source des cables electriques
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Fichier des cheminements aeriens (source des cables exclus)
FICHIER_AERIEN: str = "RPD_Aerien_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_densite_sommets_cable.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "densite_sommets_insuffisante"

# Statut des cables a controler
CHAMP_STATUT: str = "Statut"
STATUT_CONTROLE: str = "UnderCommissionning"

# Champ de reference des cables dans les cheminements aeriens
CHAMP_CABLES_HREF: str = "cables_href"

# Distance maximale autorisee entre deux sommets consecutifs (metres)
SEUIL_DISTANCE: float = 15.0


# ---------------------------------------------------------------------------
# Exclusion des cables aeriens (mecanisme aligne sur E202 / E208)
# ---------------------------------------------------------------------------


def charger_ids_cables_aeriens(repertoire: str) -> set[str]:
    """Charge l'ensemble des identifiants de cables references par l'aerien.

    L'absence du fichier aerien n'est pas bloquante : aucune exclusion n'est
    appliquee dans ce cas. Le set garantit un test d'appartenance en O(1).
    """
    collection = lire_geojson(os.path.join(repertoire, FICHIER_AERIEN))
    features = collection.get("features", []) if collection else []
    ids_cables: set[str] = set()
    for feature in features:
        props = feature.get("properties") or {}
        ids_cables.update(_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)))
    return ids_cables


# ---------------------------------------------------------------------------
# Analyse de la densite de sommets
# ---------------------------------------------------------------------------


def _analyser_partie(sommets: list[list[float]], seuil: float) -> tuple[float, int]:
    """Analyse une polyligne : retourne (distance_max, nb_segments_trop_longs).

    La distance est calculee en 3D (dx, dy, dz) selon la convention du calcul de
    longueur du projet ; si un sommet n'a pas de Z, la composante dz vaut 0.
    """
    distance_max = 0.0
    nb_depassements = 0
    hypot = math.hypot  # alias local (boucle critique)
    for precedent, courant in pairwise(sommets):
        dz = courant[2] - precedent[2] if len(courant) > 2 and len(precedent) > 2 else 0.0
        distance = hypot(courant[0] - precedent[0], courant[1] - precedent[1], dz)
        if distance > distance_max:
            distance_max = distance
        if distance > seuil:
            nb_depassements += 1
    return distance_max, nb_depassements


def analyser_geometrie(
    geometrie: dict[str, Any] | None,
    seuil: float = SEUIL_DISTANCE,
) -> tuple[float, int]:
    """Analyse toute la geometrie d'un cable (toutes parties confondues).

    Retourne (distance_max, nb_segments_trop_longs). Les segments sont evalues
    a l'interieur de chaque partie (aucun segment fictif entre parties disjointes).
    """
    distance_max = 0.0
    nb_depassements = 0
    for sommets in extraire_parties_lineaires(geometrie):
        distance_partie, nb_partie = _analyser_partie(sommets, seuil)
        if distance_partie > distance_max:
            distance_max = distance_partie
        nb_depassements += nb_partie
    return distance_max, nb_depassements


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _est_a_controler(props: dict[str, Any], id_cable: str | None, ids_aeriens: set[str]) -> bool:
    """Indique si un cable doit etre controle (statut, non aerien)."""
    if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
        return False
    return id_cable not in ids_aeriens


def detecter_anomalies(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str],
    seuil: float = SEUIL_DISTANCE,
) -> list[dict[str, Any]]:
    """Detecte les cables dont la densite de sommets est insuffisante.

    Seuls les cables au statut UnderCommissionning et non aeriens sont analyses.
    Une anomalie est generee par cable presentant au moins un segment trop long.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        id_cable = obtenir_id_feature(feature)
        if not _est_a_controler(props, id_cable, ids_cables_aeriens):
            continue
        geometrie = feature.get("geometry")
        distance_max, nb_depassements = analyser_geometrie(geometrie, seuil)
        if nb_depassements == 0:
            continue
        anomalies.append(
            {
                "id_cable": id_cable,
                "distance_max": round(distance_max, 2),
                "nombre_segments_trop_longs": nb_depassements,
                "geometrie": geometrie,
            }
        )
    return anomalies


def compter_cables_controles(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str],
) -> int:
    """Compte les cables effectivement controles (UnderCommissionning, non aeriens)."""
    return sum(
        1
        for feature in features
        if _est_a_controler(feature.get("properties") or {}, obtenir_id_feature(feature), ids_cables_aeriens)
    )


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des cables de densite insuffisante.

    La geometrie de chaque feature est celle du cable concerne (localisation
    QGIS). Le crs est propage depuis le fichier source des cables.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "fichier_source": FICHIER_CABLE_ELECTRIQUE,
                "id_cable": a["id_cable"],
                "distance_max_m": a["distance_max"],
                "seuil_m": SEUIL_DISTANCE,
                "nombre_segments_trop_longs": a["nombre_segments_trop_longs"],
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


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de densite de sommets des cables en mode CLI.

    Charge les cables aeriens a exclure, controle chaque cable electrique au
    statut UnderCommissionning non aerien et ecrit le fichier d'ecarts GeoJSON.
    L'absence du fichier cable est signalee sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    ids_cables_aeriens = charger_ids_cables_aeriens(repertoire_resolu)

    chemin_cable = os.path.join(repertoire_resolu, FICHIER_CABLE_ELECTRIQUE)
    collection = lire_geojson(chemin_cable) if os.path.isfile(chemin_cable) else None
    fichier_cable_absent = collection is None
    features = collection.get("features", []) if collection is not None else []
    crs = collection.get("crs") if collection is not None else None

    anomalies = detecter_anomalies(features, ids_cables_aeriens)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_controles": compter_cables_controles(features, ids_cables_aeriens),
        "nombre_cables_aeriens_exclus": len(ids_cables_aeriens),
        "seuil_m": SEUIL_DISTANCE,
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de densite de sommets des cables."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E504 : densite de sommets des cables electriques "
            "(RPD_CableElectrique_Reco au statut UnderCommissionning, hors cables "
            "aeriens) — au moins un sommet tous les 15 metres."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
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
