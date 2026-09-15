"""
Moteur de detection des longueurs de cable excessives.

La longueur admise depend du domaine de tension, et le verificateur reserve un
code a chacun :

    DomaineTension = BT   longueur <= 250 m    -> E-4200
    DomaineTension = HTA  longueur <= 500 m    -> E-4201
    autres domaines (HTB, ...)                 aucune verification

C'est tout l'objet de ce moteur : le seuil et le code d'erreur sont deux faces
de la meme regle metier, portees ensemble par `REGLES_PAR_DOMAINE`. Un domaine
absent de la table n'est pas controle.

Le domaine de tension est le discriminant : il est deja lu pour resoudre le
seuil, et c'est lui qui designe le code sous lequel l'anomalie est rendue.

Perimetre :
  - Entites RPD_CableElectrique_Reco au Statut UnderCommissionning.
  - Les cables references par un cheminement aerien (RPD_Aerien_Reco.cables_href)
    sont exclus, via le meme mecanisme que les controles E-5201 / E-5102 / E-5100.
  - Compatible RecoStaR V1.0 et V1.1.

La longueur est calculee en 3D (convention du calcul de longueur du projet), en
reutilisant la decomposition geometrique d'E-5100.
"""

import math
import os
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.geometrie import corriger_z_nuls, extraire_parties_lineaires

# Mecanisme d'exclusion aerienne et decomposition geometrique, communs avec E-5100
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_DOMAINE_TENSION,
    CHAMP_STATUT,
    FICHIER_CABLE_ELECTRIQUE,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.references_cables import (
    charger_ids_cables_aeriens,
)

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "longueur_excessive"

# Champ du domaine de tension

# Types d'anomalie produits par le moteur, un par code du verificateur.
TYPE_LONGUEUR_BT: str = "longueur_bt_excessive"
TYPE_LONGUEUR_HTA: str = "longueur_hta_excessive"


@dataclass(frozen=True, slots=True)
class RegleLongueur:
    """Longueur maximale d'un domaine de tension, et le code qui la sanctionne.

    Les deux vont ensemble : le verificateur ne nomme pas « longueur
    excessive », il nomme « longueur BT superieure a 250 m » et « longueur HTA
    superieure a 500 m ». Le domaine est donc le discriminant du code autant que
    du seuil, et les separer inviterait a les faire diverger.
    """

    seuil: float
    type_anomalie: str


# Regles par domaine de tension ; absence de cle = domaine non controle.
REGLES_PAR_DOMAINE: dict[str, RegleLongueur] = {
    "BT": RegleLongueur(250.0, TYPE_LONGUEUR_BT),
    "HTA": RegleLongueur(500.0, TYPE_LONGUEUR_HTA),
}


# ---------------------------------------------------------------------------
# Calcul de longueur 3D
# ---------------------------------------------------------------------------


def _longueur_partie(sommets: list[list[float]]) -> float:
    """Somme des distances 3D entre sommets consecutifs d'une polyligne.

    Les altitudes nulles sont corrigees comme dans E-5100 et dans le calcul des
    longueurs de cables : un Z a 0.0 signale une altitude absente, non une
    altitude nulle. Sans cette correction, un cable de quelques metres se voit
    attribuer la longueur de l'altitude du terrain et depasse tout seuil.
    """
    total = 0.0
    z_corrige = corriger_z_nuls(sommets)
    hypot = math.hypot  # alias local (boucle critique)
    for indice, (precedent, courant) in enumerate(pairwise(sommets), start=1):
        dz = z_corrige[indice] - z_corrige[indice - 1]
        total += hypot(courant[0] - precedent[0], courant[1] - precedent[1], dz)
    return total


def calculer_longueur(geometrie: dict[str, Any] | None) -> float:
    """Calcule la longueur 3D totale d'une geometrie lineaire (toutes parties)."""
    return sum(_longueur_partie(sommets) for sommets in extraire_parties_lineaires(geometrie))


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def regle_applicable(
    props: dict[str, Any],
    id_cable: str | None,
    ids_cables_aeriens: set[str],
) -> RegleLongueur | None:
    """Retourne la regle applicable au cable, ou None s'il n'est pas controle.

    Filtre et regle en une seule resolution : un cable n'est controle que s'il
    est UnderCommissionning, non aerien et d'un domaine de tension dote d'une
    regle (BT ou HTA). La regle porte le seuil **et** le type d'anomalie, donc le
    code d'erreur.
    """
    if props.get(CHAMP_STATUT) != STATUT_MISE_EN_SERVICE:
        return None
    if id_cable in ids_cables_aeriens:
        return None
    domaine = props.get(CHAMP_DOMAINE_TENSION)
    if not isinstance(domaine, str):
        return None
    return REGLES_PAR_DOMAINE.get(domaine)


def detecter_anomalies(
    features: list[dict[str, Any]],
    ids_cables_aeriens: set[str],
) -> list[dict[str, Any]]:
    """Detecte les cables dont la longueur depasse le seuil de leur domaine.

    Une anomalie par cable dont la longueur 3D est strictement superieure au
    seuil de son DomaineTension ; son type — donc son code — vient de la regle
    appliquee, jamais d'un test refait ici.
    """
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        props = feature.get("properties") or {}
        id_cable = obtenir_id_feature(feature)
        regle = regle_applicable(props, id_cable, ids_cables_aeriens)
        if regle is None:
            continue
        geometrie = feature.get("geometry")
        longueur = calculer_longueur(geometrie)
        if longueur <= regle.seuil:
            continue
        anomalies.append(
            {
                "type_anomalie": regle.type_anomalie,
                "id_cable": id_cable,
                "domaine_tension": props.get(CHAMP_DOMAINE_TENSION),
                "longueur": round(longueur, 2),
                "seuil": regle.seuil,
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
        if regle_applicable(feature.get("properties") or {}, obtenir_id_feature(feature), ids_cables_aeriens)
        is not None
    )


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
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
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_CABLE_ELECTRIQUE,
                "id_cable": a["id_cable"],
                "domaine_tension": a["domaine_tension"],
                "longueur_m": a["longueur"],
                "seuil_m": a["seuil"],
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
# Orchestration, partagee par les deux controles
# ---------------------------------------------------------------------------


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de longueur en mode CLI.

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

    # Le moteur releve les deux domaines ; le controle appelant ne retient que
    # le sien. Les compteurs qui suivent portent donc sur son perimetre.
    anomalies = filtrer_par_type(detecter_anomalies(features, ids_cables_aeriens), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_cables_controles": compter_cables_controles(features, ids_cables_aeriens),
        "nombre_cables_aeriens_exclus": len(ids_cables_aeriens),
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_ecrit,
    }
