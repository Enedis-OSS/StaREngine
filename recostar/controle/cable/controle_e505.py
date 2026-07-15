"""
Controle E505 : coherence longueur / DomaineTension des cables electriques.

Verifie que la longueur d'un cable electrique en cours de mise en service reste
compatible avec son domaine de tension :
  - DomaineTension = BT  : longueur <= 250 metres ;
  - DomaineTension = HTA : longueur <= 500 metres ;
  - autres domaines (HTB, ...) : aucune verification.

Perimetre :
  - Entites RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Les cables references par un cheminement aerien (RPD_Aerien_Reco.cables_href)
    sont exclus, via le meme mecanisme que les controles E202 / E208 / E504.
  - Compatible RecoStaR V1.0 et V1.1.

La longueur est calculee en 3D (convention du calcul de longueur du projet), en
reutilisant la decomposition geometrique du controle E504.

Priorite : information (non bloquante).

Usage CLI :
    python controle_e505.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_longueur_domaine_tension.geojson
"""

import argparse
import json
import math
import os
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

# Mecanisme d'exclusion aerienne et decomposition geometrique reutilises d'E504
from controle_e504 import (
    CHAMP_STATUT,
    FICHIER_CABLE_ELECTRIQUE,
    STATUT_CONTROLE,
    charger_ids_cables_aeriens,
)
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature
from utils_geometrie import extraire_parties_lineaires

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_longueur_domaine_tension.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "information"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "longueur_excessive"

# Champ du domaine de tension
CHAMP_DOMAINE: str = "DomaineTension"

# Seuils de longueur (metres) par domaine de tension ; absence de cle = pas de controle
SEUILS_LONGUEUR: dict[str, float] = {
    "BT": 250.0,
    "HTA": 500.0,
}


# ---------------------------------------------------------------------------
# Calcul de longueur 3D
# ---------------------------------------------------------------------------


def _longueur_partie(sommets: list[list[float]]) -> float:
    """Somme des distances 3D entre sommets consecutifs d'une polyligne.

    Un sommet sans composante Z est traite en 2D (dz = 0), comme dans E504.
    """
    total = 0.0
    hypot = math.hypot  # alias local (boucle critique)
    for precedent, courant in pairwise(sommets):
        dz = courant[2] - precedent[2] if len(courant) > 2 and len(precedent) > 2 else 0.0
        total += hypot(courant[0] - precedent[0], courant[1] - precedent[1], dz)
    return total


def calculer_longueur(geometrie: dict[str, Any] | None) -> float:
    """Calcule la longueur 3D totale d'une geometrie lineaire (toutes parties)."""
    return sum(_longueur_partie(sommets) for sommets in extraire_parties_lineaires(geometrie))


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _seuil_applicable(
    props: dict[str, Any],
    id_cable: str | None,
    ids_cables_aeriens: set[str],
) -> float | None:
    """Retourne le seuil de longueur applicable au cable, ou None si non controle.

    Un cable n'est controle que s'il est UnderCommissionning, non aerien et d'un
    domaine de tension dote d'un seuil (BT ou HTA).
    """
    if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
        return None
    if id_cable in ids_cables_aeriens:
        return None
    domaine = props.get(CHAMP_DOMAINE)
    if not isinstance(domaine, str):
        return None
    return SEUILS_LONGUEUR.get(domaine)


def detecter_anomalies(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str],
) -> list[dict[str, Any]]:
    """Detecte les cables dont la longueur depasse le seuil de leur domaine.

    Une anomalie est generee par cable dont la longueur 3D est strictement
    superieure au seuil associe a son DomaineTension.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        id_cable = obtenir_id_feature(feature)
        seuil = _seuil_applicable(props, id_cable, ids_cables_aeriens)
        if seuil is None:
            continue
        geometrie = feature.get("geometry")
        longueur = calculer_longueur(geometrie)
        if longueur <= seuil:
            continue
        anomalies.append(
            {
                "id_cable": id_cable,
                "domaine_tension": props.get(CHAMP_DOMAINE),
                "longueur": round(longueur, 2),
                "seuil": seuil,
                "geometrie": geometrie,
            }
        )
    return anomalies


def compter_cables_controles(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str],
) -> int:
    """Compte les cables effectivement controles (statut, non aerien, BT ou HTA)."""
    return sum(
        1
        for feature in features
        if _seuil_applicable(feature.get("properties") or {}, obtenir_id_feature(feature), ids_cables_aeriens)
        is not None
    )


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des cables de longueur excessive.

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
                "domaine_tension": a["domaine_tension"],
                "longueur_m": a["longueur"],
                "seuil_m": a["seuil"],
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
    """Execute le controle de coherence longueur / DomaineTension en mode CLI.

    Charge les cables aeriens a exclure, controle chaque cable electrique au
    statut UnderCommissionning non aerien (BT ou HTA) et ecrit le fichier
    d'ecarts GeoJSON. L'absence du fichier cable est signalee sans bloquer.
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
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence longueur / DomaineTension."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E505 : coherence longueur / DomaineTension des cables "
            "electriques (RPD_CableElectrique_Reco au statut UnderCommissionning, "
            "hors cables aeriens) — BT <= 250 m, HTA <= 500 m."
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
