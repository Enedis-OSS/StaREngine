"""
Controle E602 : unicite des identifiants de materiel entre jonctions.

Verifie qu'un couple d'identifiants (NumeroLot, NumeroSerie) ne designe qu'une
seule RPD_Jonction_Reco. Un meme materiel physique ne peut pas etre pose a deux
endroits : si ses identifiants apparaissent sur plusieurs jonctions, c'est qu'il
a ete saisi plusieurs fois, ou que deux materiels distincts portent par erreur
les memes references.

Regle de gestion :
  - Regrouper les entites RPD_Materiel_Reco par couple (NumeroLot, NumeroSerie) ;
  - resoudre la jonction de chacune via l'index inverse d'E601 ;
  - un couple rattache a **deux jonctions distinctes ou plus** est en conflit :
    une anomalie est emise pour chacune de ses occurrences.

Le **couple**, et non chaque champ pris isolement
-------------------------------------------------
NumeroLot est un numero de fabrication : toutes les boites issues d'un meme lot
le partagent, et sont posees a des jonctions differentes — c'est le cas normal,
pas un defaut. Le jeu Echantillon2 en donne l'exemple : le lot « 123654654 »
equipe deux jonctions, avec deux NumeroSerie distincts. Controler NumeroLot
seul inonderait le rapport de faux positifs. Seul le couple identifie une unite
physique, et seul le couple est donc controle.

Perimetre : les entites RPD_Materiel_Reco remplissant les deux conditions :
  - **les deux** identifiants sont renseignes. Un couple incomplet n'identifie
    aucune unite : si NumeroSerie manquait, tous les materiels d'un meme lot
    partageraient le couple (lot, vide) et seraient signales a tort. L'exigence
    de renseignement des champs releve du controle de structuration (E114), pas
    d'E602 ;
  - une jonction identifiee les reference. Un materiel orphelin n'est associe a
    aucune jonction, il ne peut donc pas l'etre a plusieurs : le defaut est
    celui d'E601, qui le signale a ce titre.

Materiel reference par plusieurs jonctions : son couple designe alors a lui seul
plusieurs jonctions et le conflit est signale, la regle ne distinguant pas selon
le nombre de materiels en cause. Le rattachement multiple est par ailleurs
signale par E601 — les deux constats sont exacts et repondent a des questions
differentes.

Deux materiels partageant un couple **sur la meme jonction** ne sont pas
signales : la regle porte sur la pluralite des jonctions, pas des
enregistrements. Le doublon strict releve du controle de structuration.

Comparaison : les identifiants sont des saisies libres, comparees normalisees
(casse ignoree, suites d'espaces repliees), meme convention qu'E600.

Geometrie des ecarts : RPD_Materiel_Reco n'ayant pas de geometrie propre, chaque
feature porte le Point de la jonction concernee — le conflit est ainsi visible
sur toutes les positions qu'il met en cause.

Versions : materiel et jonction ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : majeur.

Usage CLI :
    python controle_e602.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e602_materiel_identifiants_partages.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Fichiers source et chargement mutualises avec E600, index inverse avec E601 :
# les trois controles exploitent la meme relation jonction / materiel.
from controle_e600 import (
    FICHIER_JONCTION,
    FICHIER_MATERIEL,
    _charger_features,
    normaliser_valeur,
)
from controle_e601 import LienJonction, indexer_jonctions_par_materiel
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e602_materiel_identifiants_partages.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E602"

# Type d'anomalie unique produit par ce controle
TYPE_IDENTIFIANTS_PARTAGES: str = "identifiants_materiel_partages"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_IDENTIFIANTS_PARTAGES: ("Le couple NumeroLot / NumeroSerie du matériel est associé à plusieurs jonctions."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_materiel", "id_jonction"),
)

# Niveau de priorite affecte a toutes les anomalies. Majeur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "majeur"

# Noms des champs d'identifiant dans les proprietes du materiel
CHAMP_NUMERO_LOT: str = "NumeroLot"
CHAMP_NUMERO_SERIE: str = "NumeroSerie"

# Nombre de jonctions a partir duquel un couple est en conflit.
SEUIL_JONCTIONS_EN_CONFLIT: int = 2

# Separateur des identifiants de jonction listes dans les proprietes de sortie,
# aligne sur la convention des champs *_href de RecoStaR.
SEPARATEUR_JONCTIONS: str = ","


@dataclass(frozen=True, slots=True)
class OccurrenceMateriel:
    """Apparition d'un couple d'identifiants sur une jonction donnee.

    Un materiel produit autant d'occurrences que de jonctions le referencant —
    une seule dans le cas nominal. Les valeurs brutes des identifiants sont
    conservees : le regroupement s'opere sur leur forme normalisee, mais le
    diagnostic doit montrer ce que la donnee contient reellement.
    """

    id_materiel: str | None
    id_jonction: str
    numero_lot: Any
    numero_serie: Any
    geometrie: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Regroupement par couple d'identifiants
# ---------------------------------------------------------------------------


def couple_identifiants(proprietes: Mapping[str, Any]) -> tuple[str, str] | None:
    """Retourne le couple normalise (NumeroLot, NumeroSerie), ou None.

    None signale un couple inexploitable : l'un au moins des deux identifiants
    est absent ou vide. Un tel couple n'identifie aucune unite physique et ne
    peut donc fonder aucun constat d'unicite — le retenir ferait converger tous
    les materiels d'un meme lot vers une meme cle.
    """
    lot = normaliser_valeur(proprietes.get(CHAMP_NUMERO_LOT))
    serie = normaliser_valeur(proprietes.get(CHAMP_NUMERO_SERIE))
    if lot is None or serie is None:
        return None
    return lot, serie


def _occurrences_du_materiel(
    feature: dict[str, Any],
    liens: list[LienJonction],
) -> list[OccurrenceMateriel]:
    """Construit les occurrences d'un materiel, une par jonction identifiee.

    Les jonctions depourvues d'identifiant sont ecartees : indiscernables entre
    elles, elles gonfleraient artificiellement le compte de jonctions distinctes
    et provoqueraient un conflit fictif. Leur absence d'identifiant releve du
    controle de structuration.
    """
    proprietes = feature.get("properties") or {}
    id_materiel = obtenir_id_feature(feature)
    lot, serie = proprietes.get(CHAMP_NUMERO_LOT), proprietes.get(CHAMP_NUMERO_SERIE)
    return [
        OccurrenceMateriel(id_materiel, lien.id_jonction, lot, serie, lien.geometrie)
        for lien in liens
        if lien.id_jonction is not None
    ]


def grouper_occurrences_par_couple(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> dict[tuple[str, str], list[OccurrenceMateriel]]:
    """Regroupe les occurrences de materiel par couple d'identifiants normalise.

    Les materiels hors perimetre — couple incomplet, ou aucune jonction
    identifiee les referencant — n'apparaissent dans aucun groupe.
    """
    groupes: defaultdict[tuple[str, str], list[OccurrenceMateriel]] = defaultdict(list)
    for feature in features_materiel:
        couple = couple_identifiants(feature.get("properties") or {})
        if couple is None:
            continue
        id_materiel = obtenir_id_feature(feature)
        liens = liens_par_materiel.get(id_materiel) if id_materiel is not None else None
        if not liens:
            continue
        occurrences = _occurrences_du_materiel(feature, liens)
        if occurrences:
            groupes[couple].extend(occurrences)
    return dict(groupes)


def jonctions_en_conflit(occurrences: list[OccurrenceMateriel]) -> list[str]:
    """Retourne les jonctions distinctes d'un groupe, triees, si elles sont en conflit.

    Une liste vide signale un groupe conforme : le couple ne designe qu'une
    seule jonction, quel que soit le nombre d'enregistrements qui le portent.
    Le tri rend la sortie stable d'une execution a l'autre.
    """
    identifiants = sorted({occurrence.id_jonction for occurrence in occurrences})
    if len(identifiants) < SEUIL_JONCTIONS_EN_CONFLIT:
        return []
    return identifiants


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> list[dict[str, Any]]:
    """Detecte les couples d'identifiants partages entre plusieurs jonctions.

    Une anomalie est emise **par occurrence** du couple en conflit, et non une
    par couple : le conflit se corrige sur le terrain, a chacune des positions
    qu'il met en cause. Chaque feature porte donc le Point de sa propre jonction
    et la liste complete des jonctions concernees.
    """
    anomalies: list[dict[str, Any]] = []
    for occurrences in grouper_occurrences_par_couple(features_materiel, liens_par_materiel).values():
        identifiants = jonctions_en_conflit(occurrences)
        if not identifiants:
            continue
        liste = SEPARATEUR_JONCTIONS.join(identifiants)
        anomalies.extend(
            {
                "type_anomalie": TYPE_IDENTIFIANTS_PARTAGES,
                "id_materiel": occurrence.id_materiel,
                "id_jonction": occurrence.id_jonction,
                "numero_lot": occurrence.numero_lot,
                "numero_serie": occurrence.numero_serie,
                "nombre_jonctions": len(identifiants),
                "jonctions_en_conflit": liste,
                "geometrie": occurrence.geometrie,
            }
            for occurrence in occurrences
        )
    return anomalies


def compter_couples_en_conflit(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> int:
    """Compte les couples d'identifiants rattaches a plusieurs jonctions."""
    groupes = grouper_occurrences_par_couple(features_materiel, liens_par_materiel)
    return sum(1 for occurrences in groupes.values() if jonctions_en_conflit(occurrences))


def compter_materiels_controles(
    features_materiel: list[dict[str, Any]],
    liens_par_materiel: Mapping[str, list[LienJonction]],
) -> int:
    """Compte les materiels entrant dans le perimetre du controle."""
    groupes = grouper_occurrences_par_couple(features_materiel, liens_par_materiel)
    return len({occurrence.id_materiel for occurrences in groupes.values() for occurrence in occurrences})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des identifiants de materiel partages.

    La geometrie de chaque feature est le Point de la jonction concernee ; le
    champ `jonctions_en_conflit` permet de retrouver les autres positions
    depuis n'importe laquelle d'entre elles.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_MATERIEL,
                "id_materiel": a["id_materiel"],
                "id_jonction": a["id_jonction"],
                "numero_lot": a["numero_lot"],
                "numero_serie": a["numero_serie"],
                "nombre_jonctions": a["nombre_jonctions"],
                "jonctions_en_conflit": a["jonctions_en_conflit"],
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
    """Execute le controle d'unicite des identifiants de materiel en mode CLI.

    Indexe les references des jonctions, regroupe les materiels par couple
    d'identifiants et ecrit le fichier d'ecarts GeoJSON. L'absence d'un fichier
    source est signalee sans bloquer : sans jonction, aucun couple n'est
    rattache et le controle est sans objet.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    features_materiel, _, materiel_absent = _charger_features(repertoire_resolu, FICHIER_MATERIEL)
    features_jonction, crs, jonction_absent = _charger_features(repertoire_resolu, FICHIER_JONCTION)
    liens_par_materiel = indexer_jonctions_par_materiel(features_jonction)

    anomalies = detecter_anomalies(features_materiel, liens_par_materiel)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_couples_en_conflit": compter_couples_en_conflit(features_materiel, liens_par_materiel),
        "nombre_materiels_analyses": len(features_materiel),
        "nombre_materiels_controles": compter_materiels_controles(features_materiel, liens_par_materiel),
        "nombre_jonctions_analysees": len(features_jonction),
        "fichier_materiel_absent": materiel_absent,
        "fichier_jonction_absent": jonction_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle d'unicite des identifiants de materiel."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E602 : unicite du couple NumeroLot / NumeroSerie des "
            "RPD_Materiel_Reco entre les RPD_Jonction_Reco."
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
