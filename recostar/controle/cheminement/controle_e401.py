"""
Controle E401 : integrite des relations entre cables et cheminements.

Verifie la coherence bidirectionnelle entre les entites cable et les entites
cheminement via le champ cables_href. Quatre regles sont appliquees :

  Regle 1 / Regle 3 — Cable non reference :
      Toute entite cable absente de tout cables_href est signalee.

  Regle 2 — Reference orpheline :
      Toute valeur de cables_href ne correspondant pas a l'identifiant
      d'une entite cable existante est signalee.

  Regle 4 — Cardinalite :
      Un cheminement doit etre associe a exactement un cable.
      Un cheminement sans cables_href (null ou absent) et un cheminement
      referençant plusieurs cables sont tous deux signales.

Fichiers cables analyses :
  RPD_CableElectrique_Reco.geojson
  RPD_CableTerre_Reco.geojson
  RPD_CableTelecommunication_Reco.geojson

Fichiers cheminement analyses :
  RPD_Fourreau_Reco.geojson
  RPD_PleineTerre_Reco.geojson
  RPD_Aerien_Reco.geojson
  RPD_ProtectionMecanique_Reco.geojson

Usage CLI :
    python controle_e401.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_integrite_cables_cheminements.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_cheminement import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Fichiers cable dont les entites doivent etre referenceees par les cheminements
FICHIERS_CABLES: tuple[str, ...] = (
    "RPD_CableElectrique_Reco.geojson",
    "RPD_CableTerre_Reco.geojson",
    "RPD_CableTelecommunication_Reco.geojson",
)

# Fichiers cheminement porteurs du champ cables_href
FICHIERS_CHEMINEMENT: tuple[str, ...] = (
    "RPD_Fourreau_Reco.geojson",
    "RPD_PleineTerre_Reco.geojson",
    "RPD_Aerien_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_integrite_cables_cheminements.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Nom du champ de relation dans les proprietes des cheminements
CHAMP_CABLES_HREF: str = "cables_href"


@dataclass(slots=True)
class EntiteCable:
    """Entite cable avec son identifiant, son fichier source et sa geometrie."""

    id_entite: str
    fichier: str
    geometrie: dict[str, Any] | None


@dataclass(slots=True)
class EntiteCheminement:
    """Entite cheminement avec ses references cables et sa geometrie."""

    id_entite: str | None
    fichier: str
    ids_cables: list[str]  # identifiants extraits du champ cables_href
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_cables(
    repertoire: str,
) -> tuple[dict[str, EntiteCable], list[str]]:
    """Charge toutes les entites cable depuis les fichiers concernes.

    Retourne ({id_cable: EntiteCable}, fichiers_absents).
    Les entites sans identifiant sont ignorees silencieusement.
    """
    cables: dict[str, EntiteCable] = {}
    fichiers_absents: list[str] = []

    for nom_fichier in FICHIERS_CABLES:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        for feature in collection.get("features", []):
            id_entite = obtenir_id_feature(feature)
            if id_entite is None:
                continue
            cables[id_entite] = EntiteCable(
                id_entite=id_entite,
                fichier=nom_fichier,
                geometrie=feature.get("geometry"),
            )

    return cables, fichiers_absents


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


def charger_cheminements(
    repertoire: str,
) -> tuple[list[EntiteCheminement], list[str], dict[str, Any] | None]:
    """Charge toutes les entites cheminement depuis les fichiers concernes.

    Retourne (cheminements, fichiers_absents, crs).
    """
    cheminements: list[EntiteCheminement] = []
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT:
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
# Construction des anomalies unitaires
# ---------------------------------------------------------------------------


def _anomalie_cable_non_reference(cable: EntiteCable) -> dict[str, Any]:
    """Construit l'anomalie pour un cable sans reference cheminement (regles 1 et 3)."""
    return {
        "type_anomalie": "cable_non_reference",
        "fichier_cable": cable.fichier,
        "id_cable": cable.id_entite,
        "geometrie": cable.geometrie,
    }


def _anomalie_sans_cable(cheminement: EntiteCheminement) -> dict[str, Any]:
    """Construit l'anomalie pour un cheminement sans cables_href (regle 4)."""
    return {
        "type_anomalie": "cheminement_sans_cable",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "geometrie": cheminement.geometrie,
    }


def _anomalie_multi_cables(cheminement: EntiteCheminement) -> dict[str, Any]:
    """Construit l'anomalie pour un cheminement referençant plusieurs cables (regle 4)."""
    return {
        "type_anomalie": "cheminement_multi_cables",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "nb_cables": len(cheminement.ids_cables),
        "cables_href": ",".join(cheminement.ids_cables),
        "geometrie": cheminement.geometrie,
    }


def _anomalie_reference_orpheline(
    cheminement: EntiteCheminement,
    id_cable_invalide: str,
) -> dict[str, Any]:
    """Construit l'anomalie pour une reference cables_href sans cable correspondant (regle 2)."""
    return {
        "type_anomalie": "reference_orpheline",
        "fichier_cheminement": cheminement.fichier,
        "id_cheminement": cheminement.id_entite,
        "cables_href_invalide": id_cable_invalide,
        "geometrie": cheminement.geometrie,
    }


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _analyser_cheminement(
    cheminement: EntiteCheminement,
    ids_cables_valides: set[str],
) -> list[dict[str, Any]]:
    """Detecte les anomalies d'un cheminement (regles 2 et 4).

    Les regles de cardinalite (0 ou >1 cable) et de validite des references
    sont appliquees independamment : un cheminement peut cumuler plusieurs
    types d'anomalies.
    """
    anomalies: list[dict[str, Any]] = []
    ids = cheminement.ids_cables

    if not ids:
        anomalies.append(_anomalie_sans_cable(cheminement))
    elif len(ids) > 1:
        anomalies.append(_anomalie_multi_cables(cheminement))

    for id_cable in ids:
        if id_cable not in ids_cables_valides:
            anomalies.append(_anomalie_reference_orpheline(cheminement, id_cable))

    return anomalies


def detecter_anomalies(
    cables: dict[str, EntiteCable],
    cheminements: list[EntiteCheminement],
) -> list[dict[str, Any]]:
    """Detecte toutes les anomalies d'integrite cables/cheminements.

    Applique les quatre regles :
    - Regle 4 : cheminement sans cable ou avec plusieurs cables.
    - Regle 2 : reference cables_href sans cable correspondant.
    - Regles 1 et 3 : cable non reference par aucun cheminement.

    L'ensemble ids_references est construit en une seule passe sur les
    cheminements pour identifier les cables non references en O(n).
    """
    ids_valides = set(cables.keys())  # set pour appartenance en O(1)
    ids_references: set[str] = set()
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_cheminement  # alias local

    for cheminement in cheminements:
        anomalies.extend(analyser(cheminement, ids_valides))
        for id_cable in cheminement.ids_cables:
            if id_cable in ids_valides:
                ids_references.add(id_cable)

    for id_cable, cable in cables.items():
        if id_cable not in ids_references:
            anomalies.append(_anomalie_cable_non_reference(cable))

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _construire_proprietes(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Construit le dictionnaire de proprietes GeoJSON d'une anomalie.

    Les proprietes communes (type_anomalie, priorite) sont toujours presentes.
    Les proprietes specifiques dependent du type d'anomalie.
    """
    type_anomalie = anomalie["type_anomalie"]
    id_chemin = anomalie.get("id_cheminement")

    props: dict[str, Any] = {
        "type_anomalie": type_anomalie,
        "priorite": PRIORITE_ANOMALIE,
    }

    if type_anomalie == "cable_non_reference":
        props["fichier_cable"] = anomalie["fichier_cable"]
        props["id_cable"] = anomalie["id_cable"]
    elif type_anomalie == "reference_orpheline":
        props["fichier_cheminement"] = anomalie["fichier_cheminement"]
        props["id_cheminement"] = str(id_chemin) if id_chemin is not None else None
        props["cables_href_invalide"] = anomalie["cables_href_invalide"]
    elif type_anomalie == "cheminement_sans_cable":
        props["fichier_cheminement"] = anomalie["fichier_cheminement"]
        props["id_cheminement"] = str(id_chemin) if id_chemin is not None else None
    elif type_anomalie == "cheminement_multi_cables":
        props["fichier_cheminement"] = anomalie["fichier_cheminement"]
        props["id_cheminement"] = str(id_chemin) if id_chemin is not None else None
        props["nb_cables"] = anomalie["nb_cables"]
        props["cables_href"] = anomalie["cables_href"]

    return props


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des anomalies d'integrite detectees.

    La geometrie de chaque feature est celle de l'entite concernee (cable
    ou cheminement selon le type d'anomalie), ce qui permet la localisation
    dans QGIS. Le crs est propage depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": _construire_proprietes(a),
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


def _compter_par_type(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Compte les anomalies par type pour le rapport JSON."""
    comptes: defaultdict[str, int] = defaultdict(int)
    for anomalie in anomalies:
        comptes[anomalie["type_anomalie"]] += 1
    return dict(comptes)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle d'integrite cables/cheminements en mode CLI.

    Charge les entites cables et cheminements, detecte les quatre types
    d'anomalies et ecrit le fichier d'ecarts GeoJSON. Les fichiers absents
    sont listes dans le rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    cables, fichiers_cables_absents = charger_cables(repertoire_resolu)
    cheminements, fichiers_cheminement_absents, crs = charger_cheminements(repertoire_resolu)

    anomalies = detecter_anomalies(cables, cheminements)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": _compter_par_type(anomalies),
        "nombre_cables_analyses": len(cables),
        "nombre_cheminements_analyses": len(cheminements),
        "fichiers_cables_absents": fichiers_cables_absents,
        "fichiers_cheminement_absents": fichiers_cheminement_absents,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle d'integrite cables/cheminements."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E401 : integrite des relations entre cables "
            "(CableElectrique, CableTerre, CableTelecommunication) "
            "et cheminements (Fourreau, PleineTerre, Aerien, "
            "ProtectionMecanique) via le champ cables_href."
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
