"""
Moteur de detection : coherence metier FonctionCable_href / DomaineTension / HierarchieBT.

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

Le champ FonctionCable_href contient directement la valeur metier (et non un
identifiant a resoudre) dans les donnees Recostar serialisees en GeoJSON.

Pourquoi le cable de telecommunication est hors perimetre
---------------------------------------------------------
Il l'etait a tort : la couche etait controlee comme si elle portait un
FonctionCable valant « Communication ». Elle n'en porte aucun. Au XSD,
FonctionCable n'existe que sur RPD_CableElectrique_Reco et RPD_CableTerre_Reco
(cf. sequences du type, et regle C_FONCTION_CABLE de regles_valeurs, PDF
§10.1.6) ; « Communication » est une valeur de **leur** CodeList, non celle du
cable de telecommunication. Ce dernier porte un champ distinct, `Fonction`,
d'une CodeList distincte — RRTT ou TLC (regle C_FONCTION_TELECOM, PDF §10.1.7).
Le controle lisait donc un champ absent et le comparait a un domaine etranger :
tout cable de telecommunication ressortait en anomalie.

La couche est retiree plutot que corrigee, car il n'y reste rien a verifier ici :
elle n'a ni DomaineTension ni HierarchieBT — les deux coherences qui font l'objet
de ce moteur — et son unique attribut contraint, `Fonction`, est **optionnel** au
XSD. Sa valeur releve du controle des valeurs, E0114 / E0014, qui la verifie deja
sous le code E-2100. La reprendre ici ferait sortir un meme defaut sous deux
codes, contre la regle du projet : un defaut, un code.

Versions : les trois fichiers cable ont une structure identique en RecoStaR
V1.0 et V1.1 ; le controle est agnostique de version.

"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_DOMAINE_TENSION,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TERRE,
)

# Noms des champs dans les proprietes des features
CHAMP_FONCTION: str = "FonctionCable_href"
CHAMP_HIERARCHIE: str = "HierarchieBT"

# Valeurs de reference (frozenset -> appartenance en O(1)). Les deux seules
# couches portant un FonctionCable : le cable de telecommunication n'en a pas.
FONCTIONS_ELECTRIQUE: frozenset[str] = frozenset({"DistributionEnergie", "TransportEnergie"})
FONCTIONS_TERRE: frozenset[str] = frozenset({"ProtectionCathodique", "MaltEquipot", "Equipotentialite", "MiseTerre"})

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


# Signature commune des validateurs : (fonction, domaine, hierarchie) -> codes
Validateur = Callable[[Any, Any, Any], list[str]]

# Association fichier source -> validateur, dans l'ordre d'analyse. Le cable de
# telecommunication n'y figure pas : il ne porte aucun des trois champs de ce
# moteur (cf. en-tete du module).
VALIDATEURS: tuple[tuple[str, Validateur], ...] = (
    (FICHIER_CABLE_ELECTRIQUE, valider_cable_electrique),
    (FICHIER_CABLE_TERRE, valider_cable_terre),
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
        domaine = props.get(CHAMP_DOMAINE_TENSION)
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
    profil: ProfilEcarts,
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
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
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

    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_cables_analyses": nb_cables_analyses,
        "fichiers_absents": fichiers_absents,
        "sortie": chemin_ecrit,
    }
