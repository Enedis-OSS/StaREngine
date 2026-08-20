"""
Controle E502 : coherence de la designation des cables electriques avec le referentiel.

Verifie que la combinaison des caracteristiques d'une entite RPD_CableElectrique_Reco
correspond a une entree valide du referentiel des designations normalisees :

    recostar/referentiels/cables/verificateur_designation_normal.json

Champs de designation compares (dans cet ordre) :
    DomaineTension, HierarchieBT, NombreConducteurs, Section, SectionNeutre,
    Isolant, Materiau.

Perimetre :
  - Uniquement les entites RPD_CableElectrique_Reco.
  - Uniquement celles dont Statut == UnderCommissionning.
  - Compatible RecoStaR V1.0 et V1.1 (memes champs, referentiel independant
    de la version).

Normalisation (indispensable) :
  Le referentiel et l'export GeoJSON n'utilisent pas les memes conventions de
  serialisation. La comparaison s'effectue sur des valeurs normalisees :
    - chaines : minuscules, espaces de bord supprimes (casse ignoree) ;
      ex. "Reseau" (GeoJSON) <-> "reseau" (referentiel) ;
    - flottants entiers : convertis en entiers ; ex. 70.0 <-> 70 ;
    - valeurs absentes (None) : remplacees par la sentinelle du referentiel
      (HierarchieBT -> "0", Section / SectionNeutre -> 0).

Neutralisation de HierarchieBT en HTA :
  Le champ HierarchieBT ne qualifie que les cables BT ; les entrees HTA du
  referentiel portent toutes la sentinelle "0". Sa valeur est donc ignoree
  (ramenee a "0") quand DomaineTension vaut HTA, des deux cotes de la
  comparaison. Un HierarchieBT renseigne sur un cable HTA reste signale, mais
  par E501 seul (anomalie hierarchie_bt_interdite), dont c'est la regle.

Regle : si la cle normalisee des 7 champs n'existe dans aucune entree du
referentiel, une anomalie E502 est generee pour l'entite.

Usage CLI :
    python controle_e502.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e502_designation_normalisee.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source des cables electriques
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Referentiel des designations normalisees, resolu depuis la position du module
# (.../recostar/controle/cable/ -> .../recostar/referentiels/cables/)
CHEMIN_REFERENTIEL: str = str(
    Path(__file__).parents[2] / "referentiels" / "cables" / "verificateur_designation_normal.json"
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e502_designation_normalisee.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E502"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "designation_non_referencee": ("La désignation du câble ne correspond à aucune entrée du référentiel."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Type d'anomalie unique produit par ce controle
TYPE_ANOMALIE: str = "designation_non_referencee"

# Statut des entites a controler
CHAMP_STATUT: str = "Statut"
STATUT_CONTROLE: str = "UnderCommissionning"

# Champs de designation compares (ordre stable = ordre de la cle)
CHAMPS_DESIGNATION: tuple[str, ...] = (
    "DomaineTension",
    "HierarchieBT",
    "NombreConducteurs",
    "Section",
    "SectionNeutre",
    "Isolant",
    "Materiau",
)

# Sentinelles du referentiel pour les champs optionnels absents (None)
_SENTINELLES_NONE: dict[str, Any] = {
    "HierarchieBT": "0",
    "Section": 0,
    "SectionNeutre": 0,
}

# Domaines de tension pour lesquels HierarchieBT n'est pas discriminant. Le champ
# ne qualifie que les cables BT : les 162 entrees HTA du referentiel portent
# toutes la sentinelle « 0 ». Une valeur presente dans la donnee est donc
# neutralisee avant comparaison, faute de quoi un cable HTA par ailleurs conforme
# serait signale a tort par E502 — le renseignement indu de HierarchieBT relevant
# du seul controle E501 (type d'anomalie hierarchie_bt_interdite).
DOMAINES_HIERARCHIE_IGNOREE: frozenset[str] = frozenset({"hta"})


# ---------------------------------------------------------------------------
# Normalisation et construction de la cle de designation
# ---------------------------------------------------------------------------


def _normaliser_valeur(champ: str, valeur: Any) -> Any:
    """Normalise une valeur de champ pour aligner referentiel et donnees GeoJSON.

    - None -> sentinelle du referentiel (HierarchieBT='0', Section/SectionNeutre=0) ;
    - chaine -> minuscules sans espaces de bord (comparaison insensible a la casse) ;
    - flottant entier -> entier (150.0 -> 150) ;
    - autre valeur -> inchangee.
    """
    if valeur is None:
        return _SENTINELLES_NONE.get(champ)
    if isinstance(valeur, str):
        return valeur.strip().lower()
    if isinstance(valeur, float) and valeur.is_integer():
        return int(valeur)
    return valeur


def construire_cle(source: dict[str, Any]) -> tuple[Any, ...]:
    """Construit la cle normalisee des 7 champs de designation.

    Applicable indifferemment a une entree du referentiel ou aux proprietes
    d'une feature GeoJSON (memes noms de champs), ce qui garantit que la meme
    neutralisation s'applique des deux cotes de la comparaison.

    En domaine HTA, HierarchieBT est ramene a la sentinelle du referentiel :
    le champ n'y est pas discriminant (cf. DOMAINES_HIERARCHIE_IGNOREE).
    """
    valeurs = {champ: _normaliser_valeur(champ, source.get(champ)) for champ in CHAMPS_DESIGNATION}
    if valeurs["DomaineTension"] in DOMAINES_HIERARCHIE_IGNOREE:
        valeurs["HierarchieBT"] = _SENTINELLES_NONE["HierarchieBT"]
    return tuple(valeurs[champ] for champ in CHAMPS_DESIGNATION)


def charger_referentiel(chemin: str) -> tuple[set[tuple[Any, ...]], str | None]:
    """Charge le referentiel une seule fois et construit l'index des cles valides.

    Retourne (index, erreur). L'index est un set de cles normalisees permettant
    un test d'appartenance en O(1). Les doublons de designation (memes 7 champs,
    identifiants SIG differents) sont dedupliques par le set.
    """
    if not os.path.isfile(chemin):
        return set(), f"Referentiel introuvable : {chemin}"
    try:
        with open(chemin, encoding="utf-8") as fichier:
            entrees = json.load(fichier)
    except (json.JSONDecodeError, OSError):
        return set(), f"Referentiel illisible : {chemin}"
    index = {construire_cle(entree) for entree in entrees}
    return index, None


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def _est_a_controler(props: dict[str, Any]) -> bool:
    """Indique si une entite doit etre controlee (Statut UnderCommissionning)."""
    return props.get(CHAMP_STATUT) == STATUT_CONTROLE


def detecter_anomalies(
    features: list[dict[str, Any]],
    index: set[tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Detecte les cables dont la designation n'existe pas dans le referentiel.

    Seules les entites au statut UnderCommissionning sont controlees. Les
    valeurs brutes des 7 champs sont conservees pour le diagnostic.
    """
    anomalies: list[dict[str, Any]] = []
    construire = construire_cle  # alias local
    for feature in features:
        props = feature.get("properties") or {}
        if not _est_a_controler(props):
            continue
        if construire(props) in index:
            continue
        anomalies.append(
            {
                "id_cable": obtenir_id_feature(feature),
                "valeurs": {champ: props.get(champ) for champ in CHAMPS_DESIGNATION},
                "geometrie": feature.get("geometry"),
            }
        )
    return anomalies


def compter_cables_a_controler(features: list[dict[str, Any]]) -> int:
    """Compte les entites au statut UnderCommissionning."""
    return sum(1 for feature in features if _est_a_controler(feature.get("properties") or {}))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des designations non referencees.

    La geometrie de chaque feature est celle du cable concerne (localisation
    QGIS). Les valeurs brutes des 7 champs sont exposees sous leur nom d'origine.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": TYPE_ANOMALIE,
                "fichier_source": FICHIER_CABLE_ELECTRIQUE,
                "id_cable": a["id_cable"],
                **a["valeurs"],
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
    """Execute le controle de designation normalisee des cables en mode CLI.

    Charge le referentiel une seule fois, controle chaque cable electrique au
    statut UnderCommissionning et ecrit le fichier d'ecarts GeoJSON. L'absence
    du referentiel est une erreur bloquante ; l'absence du fichier cable est
    signalee sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    index, erreur = charger_referentiel(CHEMIN_REFERENTIEL)
    if erreur is not None:
        return {"succes": False, "erreur": erreur}

    chemin_cable = os.path.join(repertoire_resolu, FICHIER_CABLE_ELECTRIQUE)
    collection = lire_geojson(chemin_cable) if os.path.isfile(chemin_cable) else None
    fichier_cable_absent = collection is None
    features = collection.get("features", []) if collection is not None else []
    crs = collection.get("crs") if collection is not None else None

    anomalies = detecter_anomalies(features, index)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_controles": compter_cables_a_controler(features),
        "nombre_entrees_referentiel": len(index),
        "fichier_cable_absent": fichier_cable_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de designation normalisee des cables."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E502 : coherence de la designation des cables electriques "
            "(RPD_CableElectrique_Reco au statut UnderCommissionning) avec le "
            "referentiel verificateur_designation_normal.json."
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
