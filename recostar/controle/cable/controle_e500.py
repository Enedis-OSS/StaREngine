"""
Controle E500 : coherence du DomaineTension entre jonctions et cables electriques.

Verifie que chaque entite RPD_Jonction_Reco reference par son champ cables_href
un ou plusieurs cables portant exactement la meme valeur de DomaineTension que
la jonction elle-meme.

Regle de gestion :
  - Parcourir les entites RPD_Jonction_Reco.
  - Pour chaque reference presente dans cables_href, recuperer le cable associe.
  - Comparer le DomaineTension de la jonction a celui du cable.
  - Les deux valeurs doivent etre strictement identiques ; sinon anomalie E500.

Perimetre des cables :
  Seul RPD_CableElectrique_Reco porte l'attribut DomaineTension dans le modele
  RecoStaR (cf. XSD : CableTerre et CableTelecommunication n'ont pas de domaine
  de tension). Les references cables_href pointant vers un cable non electrique
  (terre / telecommunication) ou vers un identifiant inexistant sont donc hors
  perimetre de ce controle (l'integrite referentielle releve du controle E401).

Versions :
  RPD_Jonction_Reco et RPD_CableElectrique_Reco (attribut DomaineTension inclus)
  ont une structure identique en RecoStaR V1.0 et V1.1. Le controle est donc
  agnostique de version et s'applique tel quel aux deux jeux de donnees, sans
  detection de version ni dependance a RPD_PointLeveOuvrageReseau_Reco.

Usage CLI :
    python controle_e500.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_coherence_domaine_tension.geojson
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_cable import extraire_ids_cables_href as _extraire_ids_cables_href
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Fichier source des jonctions
FICHIER_JONCTION: str = "RPD_Jonction_Reco.geojson"

# Seul fichier cable portant l'attribut DomaineTension (cf. XSD)
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_coherence_domaine_tension.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "domaine_tension_incoherent"

# Noms des champs dans les proprietes des features
CHAMP_CABLES_HREF: str = "cables_href"
CHAMP_DOMAINE_TENSION: str = "DomaineTension"


@dataclass(slots=True)
class EntiteJonction:
    """Entite jonction avec son domaine de tension et ses references cables."""

    id_entite: str | None
    domaine_tension: Any
    ids_cables: list[str]  # identifiants extraits du champ cables_href
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_domaines_tension_cables(
    repertoire: str,
) -> tuple[dict[str, Any], bool]:
    """Charge l'index {id_cable_electrique: DomaineTension}.

    Retourne (index, fichier_absent). Le dictionnaire permet un test
    d'appartenance et une lecture du domaine de tension en O(1) lors de la
    comparaison. Les entites sans identifiant sont ignorees silencieusement.
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE)
    if not os.path.isfile(chemin):
        return {}, True
    collection = lire_geojson(chemin)
    if collection is None:
        return {}, True

    index: dict[str, Any] = {}
    for feature in collection.get("features", []):
        id_entite = obtenir_id_feature(feature)
        if id_entite is None:
            continue
        props = feature.get("properties") or {}
        index[id_entite] = props.get(CHAMP_DOMAINE_TENSION)

    return index, False


def _creer_entite_jonction(feature: dict[str, Any]) -> EntiteJonction:
    """Cree une EntiteJonction depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteJonction(
        id_entite=obtenir_id_feature(feature),
        domaine_tension=props.get(CHAMP_DOMAINE_TENSION),
        ids_cables=_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)),
        geometrie=feature.get("geometry"),
    )


def charger_jonctions(
    repertoire: str,
) -> tuple[list[EntiteJonction], bool, dict[str, Any] | None]:
    """Charge toutes les entites jonction depuis RPD_Jonction_Reco.

    Retourne (jonctions, fichier_absent, crs).
    """
    chemin = os.path.join(repertoire, FICHIER_JONCTION)
    if not os.path.isfile(chemin):
        return [], True, None
    collection = lire_geojson(chemin)
    if collection is None:
        return [], True, None

    crs = collection.get("crs")
    jonctions = [_creer_entite_jonction(f) for f in collection.get("features", [])]
    return jonctions, False, crs


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _anomalie_incoherence(
    jonction: EntiteJonction,
    id_cable: str,
    domaine_tension_cable: Any,
) -> dict[str, Any]:
    """Construit l'anomalie pour un lien jonction/cable de tensions differentes."""
    return {
        "id_jonction": jonction.id_entite,
        "id_cable": id_cable,
        "domaine_tension_jonction": jonction.domaine_tension,
        "domaine_tension_cable": domaine_tension_cable,
        "geometrie": jonction.geometrie,
    }


def _analyser_jonction(
    jonction: EntiteJonction,
    index_cables: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detecte les incoherences de DomaineTension d'une jonction.

    Seules les references correspondant a un cable electrique (present dans
    index_cables) sont comparees ; les autres references (cables terre /
    telecommunication ou orphelines) sont hors perimetre et ignorees.
    """
    anomalies: list[dict[str, Any]] = []
    domaine_jonction = jonction.domaine_tension
    for id_cable in jonction.ids_cables:
        if id_cable not in index_cables:
            continue
        domaine_cable = index_cables[id_cable]
        # Comparaison stricte : toute difference (valeur ou absence) est signalee
        if domaine_cable != domaine_jonction:
            anomalies.append(_anomalie_incoherence(jonction, id_cable, domaine_cable))
    return anomalies


def detecter_anomalies(
    jonctions: list[EntiteJonction],
    index_cables: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detecte toutes les incoherences de DomaineTension jonction/cable.

    Produit une anomalie par lien (jonction, cable electrique) dont les
    domaines de tension different.
    """
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_jonction  # alias local
    for jonction in jonctions:
        anomalies.extend(analyser(jonction, index_cables))
    return anomalies


def compter_liens_controles(
    jonctions: list[EntiteJonction],
    index_cables: dict[str, Any],
) -> int:
    """Compte les liens jonction/cable electrique effectivement compares."""
    return sum(1 for jonction in jonctions for id_cable in jonction.ids_cables if id_cable in index_cables)


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des incoherences detectees.

    La geometrie de chaque feature est celle de la jonction concernee (Point),
    ce qui permet la localisation dans QGIS. Le crs est propage depuis le
    fichier source des jonctions.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "id_jonction": a["id_jonction"],
                "id_cable": a["id_cable"],
                "domaine_tension_jonction": a["domaine_tension_jonction"],
                "domaine_tension_cable": a["domaine_tension_cable"],
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
    """Execute le controle de coherence du DomaineTension en mode CLI.

    Charge les cables electriques et les jonctions, detecte les incoherences
    de DomaineTension et ecrit le fichier d'ecarts GeoJSON. Les fichiers absents
    sont signales dans le rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    index_cables, fichier_cable_absent = charger_domaines_tension_cables(repertoire_resolu)
    jonctions, fichier_jonction_absent, crs = charger_jonctions(repertoire_resolu)

    anomalies = detecter_anomalies(jonctions, index_cables)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_jonctions_analysees": len(jonctions),
        "nombre_cables_electriques": len(index_cables),
        "nombre_liens_controles": compter_liens_controles(jonctions, index_cables),
        "fichier_jonction_absent": fichier_jonction_absent,
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence du DomaineTension."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E500 : coherence du DomaineTension entre les jonctions "
            "(RPD_Jonction_Reco) et les cables electriques (RPD_CableElectrique_Reco) "
            "qu'elles referencent via le champ cables_href."
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
