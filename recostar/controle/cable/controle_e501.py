"""
Controle E501 : coherence metier FonctionCable_href / DomaineTension / HierarchieBT.

Verifie, pour chaque type de cable, la coherence entre la fonction du cable,
son domaine de tension et sa hierarchie BT. Les regles different selon le type.

Regles de gestion :

  RPD_CableElectrique_Reco :
    - FonctionCable_href doit valoir DistributionEnergie ou TransportEnergie.
    - Coherence fonction / domaine :
        * TransportEnergie   -> DomaineTension doit etre strictement HTB.
        * DistributionEnergie -> DomaineTension doit etre BT ou HTA.
    - Coherence domaine / hierarchie :
        * DomaineTension == BT   -> HierarchieBT peut etre renseigne (autorise).
        * DomaineTension != BT   -> HierarchieBT ne doit contenir aucune valeur.

  RPD_CableTerre_Reco :
    - FonctionCable_href doit valoir ProtectionCathodique, MaltEquipot,
      Equipotentialite ou MiseTerre ; toute autre valeur est une anomalie.

  RPD_CableTelecommunication_Reco :
    - FonctionCable_href doit valoir Communication ; toute autre valeur est
      une anomalie.

Le champ FonctionCable_href contient directement la valeur metier (et non un
identifiant a resoudre) dans les donnees Recostar serialisees en GeoJSON.

Versions : les trois fichiers cable ont une structure identique en RecoStaR
V1.0 et V1.1 ; le controle est agnostique de version.

Usage CLI :
    python controle_e501.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e501_coherence_fonction_cable.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichiers cable analyses
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"
FICHIER_CABLE_TERRE: str = "RPD_CableTerre_Reco.geojson"
FICHIER_CABLE_TELECOM: str = "RPD_CableTelecommunication_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e501_coherence_fonction_cable.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E501"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "fonction_cable_invalide": ("La FonctionCable du câble n'est pas une valeur autorisée."),
    "domaine_tension_fonction_incoherent": ("Le DomaineTension du câble est incohérent avec sa FonctionCable."),
    "hierarchie_bt_interdite": ("La HierarchieBT est renseignée alors qu'elle est interdite pour ce câble."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


# Niveau de priorite affecte a toutes les anomalies. Mineur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "mineur"

# Noms des champs dans les proprietes des features
CHAMP_FONCTION: str = "FonctionCable_href"
CHAMP_DOMAINE: str = "DomaineTension"
CHAMP_HIERARCHIE: str = "HierarchieBT"

# Valeurs de reference (frozenset -> appartenance en O(1))
FONCTIONS_ELECTRIQUE: frozenset[str] = frozenset({"DistributionEnergie", "TransportEnergie"})
FONCTIONS_TERRE: frozenset[str] = frozenset({"ProtectionCathodique", "MaltEquipot", "Equipotentialite", "MiseTerre"})
FONCTIONS_TELECOM: frozenset[str] = frozenset({"Communication"})

# Domaines de tension de reference
DOMAINE_TRANSPORT: str = "HTB"
DOMAINE_BT: str = "BT"
DOMAINES_DISTRIBUTION: frozenset[str] = frozenset({"BT", "HTA"})

# Fonctions specifiques declenchant une regle de coherence de domaine
FONCTION_TRANSPORT: str = "TransportEnergie"
FONCTION_DISTRIBUTION: str = "DistributionEnergie"

# Types d'anomalie produits par ce controle
TYPE_FONCTION_INVALIDE: str = "fonction_cable_invalide"
TYPE_DOMAINE_INCOHERENT: str = "domaine_tension_fonction_incoherent"
TYPE_HIERARCHIE_INTERDITE: str = "hierarchie_bt_interdite"


# ---------------------------------------------------------------------------
# Validateurs metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def _est_renseigne(valeur: Any) -> bool:
    """Indique si un champ porte une valeur exploitable (non nulle, non vide)."""
    if valeur is None:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return True


def valider_cable_electrique(
    fonction: Any,
    domaine: Any,
    hierarchie: Any,
) -> list[str]:
    """Valide un cable electrique et retourne la liste des codes d'anomalie.

    Applique les trois regles : fonction autorisee, coherence fonction/domaine
    et coherence domaine/hierarchie. La regle sur HierarchieBT est independante
    de la validite de la fonction (elle ne depend que du DomaineTension).
    """
    codes: list[str] = []

    if fonction not in FONCTIONS_ELECTRIQUE:
        codes.append(TYPE_FONCTION_INVALIDE)
    elif (fonction == FONCTION_TRANSPORT and domaine != DOMAINE_TRANSPORT) or (
        fonction == FONCTION_DISTRIBUTION and domaine not in DOMAINES_DISTRIBUTION
    ):
        codes.append(TYPE_DOMAINE_INCOHERENT)

    # Hors BT, la hierarchie BT ne doit porter aucune valeur.
    if domaine != DOMAINE_BT and _est_renseigne(hierarchie):
        codes.append(TYPE_HIERARCHIE_INTERDITE)

    return codes


def valider_cable_terre(fonction: Any, _domaine: Any, _hierarchie: Any) -> list[str]:
    """Valide un cable de terre : seule la fonction est contrainte."""
    if fonction not in FONCTIONS_TERRE:
        return [TYPE_FONCTION_INVALIDE]
    return []


def valider_cable_telecom(fonction: Any, _domaine: Any, _hierarchie: Any) -> list[str]:
    """Valide un cable de telecommunication : seule la fonction est contrainte."""
    if fonction not in FONCTIONS_TELECOM:
        return [TYPE_FONCTION_INVALIDE]
    return []


# Signature commune des validateurs : (fonction, domaine, hierarchie) -> codes
Validateur = Callable[[Any, Any, Any], list[str]]

# Association fichier source -> validateur, dans l'ordre d'analyse
VALIDATEURS: tuple[tuple[str, Validateur], ...] = (
    (FICHIER_CABLE_ELECTRIQUE, valider_cable_electrique),
    (FICHIER_CABLE_TERRE, valider_cable_terre),
    (FICHIER_CABLE_TELECOM, valider_cable_telecom),
)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_fichier(
    features: list[dict[str, Any]],
    nom_fichier: str,
    validateur: Validateur,
) -> list[dict[str, Any]]:
    """Detecte les anomalies d'un fichier cable via son validateur.

    Une entite peut produire plusieurs anomalies (une par regle violee).
    Les valeurs des trois champs sont conservees pour le diagnostic.
    """
    anomalies: list[dict[str, Any]] = []
    valider = validateur  # alias local
    for feature in features:
        props = feature.get("properties") or {}
        fonction = props.get(CHAMP_FONCTION)
        domaine = props.get(CHAMP_DOMAINE)
        hierarchie = props.get(CHAMP_HIERARCHIE)
        codes = valider(fonction, domaine, hierarchie)
        if not codes:
            continue
        id_cable = obtenir_id_feature(feature)
        geometrie = feature.get("geometry")
        for code in codes:
            anomalies.append(
                {
                    "type_anomalie": code,
                    "fichier_source": nom_fichier,
                    "id_cable": id_cable,
                    "fonction_cable": fonction,
                    "domaine_tension": domaine,
                    "hierarchie_bt": hierarchie,
                    "geometrie": geometrie,
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
    """Construit un FeatureCollection des incoherences metier detectees.

    La geometrie de chaque feature est celle du cable concerne, ce qui permet
    la localisation dans QGIS. Le crs est propage depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": a["fichier_source"],
                "id_cable": a["id_cable"],
                "fonction_cable": a["fonction_cable"],
                "domaine_tension": a["domaine_tension"],
                "hierarchie_bt": a["hierarchie_bt"],
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
    """Execute le controle de coherence metier des cables en mode CLI.

    Parcourt les trois fichiers cable, applique le validateur propre a chaque
    type et ecrit le fichier d'ecarts GeoJSON. Les fichiers absents sont
    listes dans le rapport sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    anomalies: list[dict[str, Any]] = []
    fichiers_absents: list[str] = []
    nb_cables_analyses = 0
    crs: dict[str, Any] | None = None

    for nom_fichier, validateur in VALIDATEURS:
        chemin = os.path.join(repertoire_resolu, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        features = collection.get("features", [])
        nb_cables_analyses += len(features)
        anomalies.extend(detecter_anomalies_fichier(features, nom_fichier, validateur))

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_cables_analyses": nb_cables_analyses,
        "fichiers_absents": fichiers_absents,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence metier des cables."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E501 : coherence metier entre FonctionCable_href, "
            "DomaineTension et HierarchieBT selon le type de cable "
            "(electrique, terre, telecommunication)."
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
