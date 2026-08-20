"""
Controle E503 : precision XY/Z des cheminements associes a un cable electrique.

Verifie que tous les cheminements qui referencent un cable electrique en cours
de mise en service possedent PrecisionXY == "A" et PrecisionZ == "A".

Perimetre :
  - Cables controles : RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Cheminements analyses (porteurs du champ cables_href) :
      RPD_Fourreau_Reco, RPD_PleineTerre_Reco, RPD_ProtectionMecanique_Reco.
  - Compatible RecoStaR V1.0 et V1.1 (memes champs, cables_href litteral).

Regle : pour chaque cable electrique controle, tout cheminement le referençant
dont PrecisionXY ou PrecisionZ differe de "A" genere une anomalie E503.

Sens de la relation : c'est le cheminement qui porte cables_href pointant vers
le cable (comme dans le controle d'integrite E401).

Usage CLI :
    python controle_e503.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e503_precision_cheminement_cable.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_cable import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source des cables electriques
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Fichiers cheminement porteurs du champ cables_href a analyser
FICHIERS_CHEMINEMENT: tuple[str, ...] = (
    "RPD_Fourreau_Reco.geojson",
    "RPD_PleineTerre_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e503_precision_cheminement_cable.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E503"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "precision_cheminement_non_conforme": ("La précision du cheminement associé au câble n'est pas conforme."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cheminement", "id_cable"),
)


# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "precision_cheminement_non_conforme"

# Statut des cables a controler
CHAMP_STATUT: str = "Statut"
STATUT_CONTROLE: str = "UnderCommissionning"

# Noms des champs analyses
CHAMP_CABLES_HREF: str = "cables_href"
CHAMP_PRECISION_XY: str = "PrecisionXY"
CHAMP_PRECISION_Z: str = "PrecisionZ"

# Valeur attendue pour les deux champs de precision
VALEUR_PRECISION_ATTENDUE: str = "A"


@dataclass(slots=True)
class EntiteCheminement:
    """Cheminement referençant un cable, avec ses precisions et sa geometrie."""

    id_entite: str | None
    fichier: str
    precision_xy: Any
    precision_z: Any
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_ids_cables_a_controler(repertoire: str) -> tuple[set[str], bool]:
    """Charge les identifiants des cables electriques a controler.

    Retourne (ids, fichier_absent). Ne conserve que les cables au statut
    UnderCommissionning, dans un set pour un test d'appartenance en O(1).
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE)
    if not os.path.isfile(chemin):
        return set(), True
    collection = lire_geojson(chemin)
    if collection is None:
        return set(), True

    ids: set[str] = set()
    for feature in collection.get("features", []):
        props = feature.get("properties") or {}
        if props.get(CHAMP_STATUT) != STATUT_CONTROLE:
            continue
        id_entite = obtenir_id_feature(feature)
        if id_entite is not None:
            ids.add(id_entite)
    return ids, False


def _creer_cheminement(feature: dict[str, Any], nom_fichier: str) -> EntiteCheminement:
    """Cree une EntiteCheminement depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteCheminement(
        id_entite=obtenir_id_feature(feature),
        fichier=nom_fichier,
        precision_xy=props.get(CHAMP_PRECISION_XY),
        precision_z=props.get(CHAMP_PRECISION_Z),
        geometrie=feature.get("geometry"),
    )


def _indexer_feature(
    feature: dict[str, Any],
    nom_fichier: str,
    ids_cables_controles: set[str],
    index: dict[str, list[EntiteCheminement]],
) -> None:
    """Indexe une feature cheminement sous chaque cable controle qu'elle reference.

    L'EntiteCheminement n'est construite qu'une fois, a la premiere reference
    pertinente, puis partagee entre les cables lies (pas de copie inutile).
    """
    props = feature.get("properties") or {}
    cheminement: EntiteCheminement | None = None
    for id_cable in _extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)):
        if id_cable not in ids_cables_controles:
            continue
        if cheminement is None:
            cheminement = _creer_cheminement(feature, nom_fichier)
        index[id_cable].append(cheminement)


def _indexer_fichier(
    chemin: str,
    nom_fichier: str,
    ids_cables_controles: set[str],
    index: dict[str, list[EntiteCheminement]],
) -> dict[str, Any] | None:
    """Indexe les cheminements d'un fichier. Retourne son crs (ou None)."""
    collection = lire_geojson(chemin)
    if collection is None:
        return None
    for feature in collection.get("features", []):
        _indexer_feature(feature, nom_fichier, ids_cables_controles, index)
    return collection.get("crs")


def indexer_cheminements_par_cable(
    repertoire: str,
    ids_cables_controles: set[str],
) -> tuple[dict[str, list[EntiteCheminement]], list[str], dict[str, Any] | None]:
    """Indexe les cheminements par identifiant de cable controle.

    Parcourt les trois couches de cheminement en une seule passe et n'indexe
    que les cheminements referençant un cable a controler (filtrage par set).
    Retourne (index, fichiers_absents, crs).
    """
    index: dict[str, list[EntiteCheminement]] = defaultdict(list)
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        crs_fichier = _indexer_fichier(chemin, nom_fichier, ids_cables_controles, index)
        if crs is None:
            crs = crs_fichier

    return index, fichiers_absents, crs


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _est_conforme(cheminement: EntiteCheminement) -> bool:
    """Indique si un cheminement respecte PrecisionXY == PrecisionZ == 'A'."""
    return (
        cheminement.precision_xy == VALEUR_PRECISION_ATTENDUE and cheminement.precision_z == VALEUR_PRECISION_ATTENDUE
    )


def detecter_anomalies(
    index: dict[str, list[EntiteCheminement]],
) -> list[dict[str, Any]]:
    """Detecte les cheminements non conformes lies a un cable controle.

    Produit une anomalie par lien (cable, cheminement) dont la precision XY ou Z
    differe de la valeur attendue.
    """
    anomalies: list[dict[str, Any]] = []
    conforme = _est_conforme  # alias local
    for id_cable, cheminements in index.items():
        for cheminement in cheminements:
            if conforme(cheminement):
                continue
            anomalies.append(
                {
                    "id_cable": id_cable,
                    "fichier_cheminement": cheminement.fichier,
                    "id_cheminement": cheminement.id_entite,
                    "precision_xy": cheminement.precision_xy,
                    "precision_z": cheminement.precision_z,
                    "geometrie": cheminement.geometrie,
                }
            )
    return anomalies


def compter_liens(index: dict[str, list[EntiteCheminement]]) -> int:
    """Compte les liens (cable controle, cheminement) analyses."""
    return sum(len(cheminements) for cheminements in index.values())


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des cheminements de precision non conforme.

    La geometrie de chaque feature est celle du cheminement fautif (localisation
    QGIS de la valeur de precision incorrecte). Le crs est propage depuis les
    fichiers cheminement.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "id_cable": a["id_cable"],
                "fichier_cheminement": a["fichier_cheminement"],
                "id_cheminement": a["id_cheminement"],
                "precision_xy": a["precision_xy"],
                "precision_z": a["precision_z"],
                "priorite": PRIORITE_ANOMALIE,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de precision des cheminements en mode CLI.

    Charge les identifiants des cables electriques controles, indexe les
    cheminements qui les referencent et signale ceux dont la precision XY ou Z
    n'est pas conforme. Les fichiers absents sont signales sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    ids_cables, fichier_cable_absent = charger_ids_cables_a_controler(repertoire_resolu)
    index, fichiers_cheminement_absents, crs = indexer_cheminements_par_cable(repertoire_resolu, ids_cables)

    anomalies = detecter_anomalies(index)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_controles": len(ids_cables),
        "nombre_liens_controles": compter_liens(index),
        "fichier_cable_absent": fichier_cable_absent,
        "fichiers_cheminement_absents": fichiers_cheminement_absents,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de precision des cheminements."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E503 : precision XY/Z des cheminements (Fourreau, PleineTerre, "
            "ProtectionMecanique) associes a un cable electrique au statut "
            "UnderCommissionning."
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
