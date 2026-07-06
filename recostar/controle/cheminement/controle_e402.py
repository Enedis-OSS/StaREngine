"""
Controle E402 : coherence metier des relations cables de terre / cheminements.

Verifie qu'aucune entite de RPD_CableTerre_Reco n'est associee a un cheminement
de type aerien ou de protection mecanique. Un cable de terre est physiquement
pose dans le sol (fourreau ou pleine terre) et ne peut pas etre achemine en
aerien ou sous protection mecanique.

Regle metier :
    Toute valeur du champ cables_href presente dans :
      - RPD_Aerien_Reco.geojson
      - RPD_ProtectionMecanique_Reco.geojson
    qui correspond a l'identifiant d'une entite de RPD_CableTerre_Reco.geojson
    est signalee comme anomalie.

Usage CLI :
    python controle_e402.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_cable_terre_cheminement_incompatible.geojson
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_cheminement import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Fichier source des cables de terre
FICHIER_CABLE_TERRE: str = "RPD_CableTerre_Reco.geojson"

# Fichiers de cheminement incompatibles avec les cables de terre
FICHIERS_CHEMINEMENT_INCOMPATIBLES: tuple[str, ...] = (
    "RPD_Aerien_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_cable_terre_cheminement_incompatible.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Nom du champ de relation dans les proprietes des cheminements
CHAMP_CABLES_HREF: str = "cables_href"

# Identifiant du type d'anomalie produit par ce controle
TYPE_ANOMALIE: str = "cable_terre_cheminement_incompatible"


@dataclass(slots=True)
class EntiteCheminement:
    """Entite de cheminement avec ses references cables et sa geometrie."""

    id_entite: str | None
    fichier: str
    ids_cables: list[str]  # identifiants extraits du champ cables_href
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_ids_cables_terre(
    repertoire: str,
) -> tuple[set[str], bool]:
    """Charge les identifiants des cables de terre depuis le fichier source.

    Retourne (ids_cables_terre, fichier_absent). Seul le champ 'id' de chaque
    feature est extrait ; la geometrie n'est pas necessaire pour ce controle.
    Les entites sans identifiant sont ignorees silencieusement.
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_TERRE)
    if not os.path.isfile(chemin):
        return set(), True
    collection = lire_geojson(chemin)
    if collection is None:
        return set(), False
    ids: set[str] = set()
    for feature in collection.get("features", []):
        id_entite = obtenir_id_feature(feature)
        if id_entite is not None:
            ids.add(id_entite)
    return ids, False


def _creer_entite_cheminement(
    feature: dict[str, Any],
    nom_fichier: str,
) -> EntiteCheminement:
    """Cree une EntiteCheminement depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteCheminement(
        id_entite=obtenir_id_feature(feature),
        fichier=nom_fichier,
        ids_cables=_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)),
        geometrie=feature.get("geometry"),
    )


def charger_cheminements_incompatibles(
    repertoire: str,
) -> tuple[list[EntiteCheminement], list[str], dict[str, Any] | None]:
    """Charge les cheminements aeriens et de protection mecanique.

    Retourne (cheminements, fichiers_absents, crs). Ces deux types de
    cheminements sont les seuls incompatibles avec les cables de terre.
    """
    cheminements: list[EntiteCheminement] = []
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT_INCOMPATIBLES:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            cheminements.append(_creer_entite_cheminement(feature, nom_fichier))

    return cheminements, fichiers_absents, crs


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    ids_cables_terre: set[str],
    cheminements: list[EntiteCheminement],
) -> list[dict[str, Any]]:
    """Detecte les cheminements incompatibles referençant un cable de terre.

    Pour chaque cheminement aerien ou de protection mecanique, chaque valeur
    de cables_href est testee en O(1) contre l'ensemble des identifiants de
    cables de terre. Une anomalie est produite par couple (cheminement, cable
    terre) invalide.
    """
    anomalies: list[dict[str, Any]] = []

    for cheminement in cheminements:
        for id_cable in cheminement.ids_cables:
            if id_cable in ids_cables_terre:
                anomalies.append(
                    {
                        "type_anomalie": TYPE_ANOMALIE,
                        "fichier_cheminement": cheminement.fichier,
                        "id_cheminement": cheminement.id_entite,
                        "id_cable_terre": id_cable,
                        "geometrie": cheminement.geometrie,
                    }
                )

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des anomalies de coherence detectees.

    La geometrie de chaque feature est celle du cheminement incompatible,
    ce qui permet la localisation precise dans QGIS. Le crs est propage
    depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "priorite": PRIORITE_ANOMALIE,
                "fichier_cheminement": a["fichier_cheminement"],
                "id_cheminement": (str(a["id_cheminement"]) if a["id_cheminement"] is not None else None),
                "id_cable_terre": a["id_cable_terre"],
            },
            "geometry": a.get("geometrie"),
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
    """Execute le controle de coherence cables de terre / cheminements.

    Charge les identifiants de cables de terre et les entites des fichiers
    de cheminement incompatibles, detecte les relations invalides et ecrit
    le fichier d'ecarts GeoJSON. Les fichiers absents sont listes dans le
    rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    ids_cables_terre, cable_terre_absent = charger_ids_cables_terre(repertoire_resolu)
    cheminements, fichiers_cheminement_absents, crs = charger_cheminements_incompatibles(repertoire_resolu)

    anomalies = detecter_anomalies(ids_cables_terre, cheminements)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_terre_analyses": len(ids_cables_terre),
        "nombre_cheminements_analyses": len(cheminements),
        "cable_terre_absent": cable_terre_absent,
        "fichiers_cheminement_absents": fichiers_cheminement_absents,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence cables de terre / cheminements."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E402 : verifie qu'aucun cable de terre "
            "(RPD_CableTerre_Reco) n'est associe a un cheminement aerien "
            "(RPD_Aerien_Reco) ou de protection mecanique "
            "(RPD_ProtectionMecanique_Reco) via le champ cables_href."
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
