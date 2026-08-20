"""
Controle E607 : localisation des points de comptage et ouvrages collectifs.

Les entites RPD_PointDeComptage_Reco et RPD_OuvrageCollectifBranchement_Reco
doivent etre localisables. Deux voies sont admises, et l'une des deux suffit :

    Cas 1 — geometrie propre : l'entite porte elle-meme une geometrie valide.
    Cas 2 — geometrie par le conteneur : l'entite est rattachee a un
            RPD_Coffret_Reco ou a un RPD_BatimentTechnique_Reco existant, qui
            reference une RPD_GeometrieSupplementaire_Reco resolue et pourvue
            d'une geometrie valide.

Une entite ne satisfaisant aucune des deux voies n'a aucune position
exploitable : une anomalie est emise.

Perimetre : les entites des deux couches dont le Statut vaut
UnderCommissionning ou Functional. Les ouvrages d'un autre statut — Projected en
particulier — sont ignores : un ouvrage a l'etat de projet n'a pas a etre
localisable sur le terrain.

Ce qu'est une geometrie « propre »
----------------------------------
Le champ `geometry` du GeoJSON ne peut pas etre teste tel quel : les
extracteurs de `recostar_to_geojson` heritent la geometrie du conteneur quand
l'entite n'en porte pas, et renseignent donc `geometry` meme lorsque le GML est
muet. Lire le cas 1 comme « le champ geometry est renseigne » le rendrait vrai
pour toute entite rattachee et rendrait le cas 2 inatteignable.

Le discriminant, mutualise avec E606 (`possede_geometrie_propre`), est
l'egalite avec la geometrie du conteneur : identique = heritee donc absente a
la source, differente ou portee sans conteneur resolu = propre a l'entite.

Verifie sur les jeux de reference : les deux voies sont effectivement
empruntees, 32 entites par le cas 1 et 3 par le cas 2.

Couches de conteneur autorisees par le cas 2 : RPD_Coffret_Reco et
RPD_BatimentTechnique_Reco. Un rattachement a un support ou a une enceinte
cloturee ne satisfait donc pas le cas 2, meme si la chaine de geometrie
supplementaire y aboutit — c'est le motif `conteneur_non_autorise`.

Anomalie : un seul type, `localisation_absente` — la regle est une disjonction,
son echec est unique. La propriete `motif` precise ou la voie du conteneur s'est
interrompue, afin que le diagnostic reste possible sans multiplier les types.

Versions : les champs de relation sont identiques en RecoStaR V1.0 et V1.1 ; le
controle est agnostique de version.

Priorite : bloquant.

Usage CLI :
    python controle_e607.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e607_ouvrage_localisation_absente.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features

# Chaine de geometrie supplementaire, structure de conteneur et champs de
# relation mutualises avec E605 ; discriminant de geometrie propre et
# indexation des conteneurs mutualises avec E606. Les trois controles evaluent
# la meme chaine de localisation, sur des entites et des conteneurs differents.
from controle_e605 import (
    CHAMP_CONTENEUR_HREF,
    EXTENSION,
    Conteneur,
    _classifier_chaine_conteneur,
    _reference,
    geometrie_ecart,
    indexer_geometries_supplementaires,
)
from controle_e606 import indexer_conteneurs_autorises, possede_geometrie_propre
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Couches controlees
COUCHES_CIBLES: tuple[str, ...] = (
    "RPD_PointDeComptage_Reco",
    "RPD_OuvrageCollectifBranchement_Reco",
)

# Couches de conteneur admises par le cas 2
COUCHES_CONTENEUR_AUTORISEES: frozenset[str] = frozenset(
    {
        "RPD_Coffret_Reco",
        "RPD_BatimentTechnique_Reco",
    }
)

# Nom du champ de statut et statuts controles (frozenset -> appartenance O(1))
CHAMP_STATUT: str = "Statut"
STATUTS_CONTROLES: frozenset[str] = frozenset({"UnderCommissionning", "Functional"})

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e607_ouvrage_localisation_absente.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E607"

# Type d'anomalie unique : la regle est une disjonction, son echec est unique.
TYPE_LOCALISATION_ABSENTE: str = "localisation_absente"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_LOCALISATION_ABSENTE: (
        "L'ouvrage n'a ni géométrie propre ni conteneur autorisé porteur d'une géométrie valide."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_ouvrage", "id_conteneur"),
)

# Niveau de priorite affecte a toutes les anomalies. Bloquant : un ouvrage sans
# position exploitable ne peut pas etre retrouve sur le terrain, le recolement
# n'est pas utilisable en l'etat (cf. PRIORITES_DECLASSANTES dans
# synthese_controles).
PRIORITE_ANOMALIE: str = "bloquant"

# Motifs d'echec de la voie du conteneur, exposes au diagnostic. Les trois
# ruptures de la chaine de geometrie supplementaire sont produites par
# `_classifier_chaine_conteneur`, mutualise avec E605.
MOTIF_CONTENEUR_ABSENT: str = "conteneur_absent"
MOTIF_CONTENEUR_INTROUVABLE: str = "conteneur_introuvable"
MOTIF_CONTENEUR_NON_AUTORISE: str = "conteneur_non_autorise"


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_controler(proprietes: Mapping[str, Any]) -> bool:
    """Indique si un ouvrage entre dans le perimetre du controle.

    Seuls les statuts UnderCommissionning et Functional sont controles : un
    ouvrage a l'etat de projet ou depose n'a pas a etre localisable sur le
    terrain. Meme perimetre de statut qu'E604 et E606.
    """
    return proprietes.get(CHAMP_STATUT) in STATUTS_CONTROLES


def motif_echec_conteneur(
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
    autorises: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Cas 2 : parcourt la voie du conteneur et retourne le motif de sa rupture.

    Retourne None lorsque la voie aboutit a une geometrie valide. Les trois
    premiers motifs qualifient le rattachement lui-meme ; les trois suivants
    proviennent de `_classifier_chaine_conteneur`, la chaine de geometrie
    supplementaire etant identique a celle d'E605 et d'E606.
    """
    if reference is None:
        return MOTIF_CONTENEUR_ABSENT
    if reference not in conteneurs:
        return MOTIF_CONTENEUR_INTROUVABLE
    if reference not in autorises:
        return MOTIF_CONTENEUR_NON_AUTORISE
    return _classifier_chaine_conteneur(conteneurs[reference], geometries_supplementaires)


def classifier_ouvrage(
    geometrie: Any,
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
    autorises: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Retourne le motif d'echec de l'ouvrage, ou None s'il est localisable.

    Le cas 1 est evalue en premier : une geometrie propre suffit, la voie du
    conteneur n'a alors pas a etre parcourue. Le motif retourne decrit donc
    toujours l'echec du cas 2, seul restant a examiner.
    """
    if possede_geometrie_propre(geometrie, reference, conteneurs):
        return None
    return motif_echec_conteneur(reference, conteneurs, autorises, geometries_supplementaires)


# ---------------------------------------------------------------------------
# Parcours des couches
# ---------------------------------------------------------------------------


def parcourir_ouvrages(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]], bool]]:
    """Parcourt les couches controlees, une seule chargee a la fois.

    Retourne (couche, features, absente). Les couches absentes sont remontees
    pour le rapport sans interrompre le controle : un jeu ne contient pas
    necessairement les deux types d'ouvrage.
    """
    for couche in COUCHES_CIBLES:
        features, _, absente = _charger_features(repertoire, f"{couche}{EXTENSION}")
        yield couche, features, absente


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    conteneurs: Mapping[str, Conteneur],
    autorises: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les ouvrages d'une couche depourvus de localisation.

    Seuls les ouvrages du perimetre sont evalues. La geometrie de l'ecart est
    celle de l'ouvrage si elle existe, a defaut celle de son conteneur, afin
    qu'il reste localisable dans QGIS.
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_ouvrage  # alias local
    for feature in features:
        proprietes = feature.get("properties") or {}
        if not est_a_controler(proprietes):
            continue
        reference = _reference(proprietes, CHAMP_CONTENEUR_HREF)
        geometrie = feature.get("geometry")
        motif = classifier(geometrie, reference, conteneurs, autorises, geometries_supplementaires)
        if motif is None:
            continue
        conteneur = conteneurs.get(reference) if reference is not None else None
        anomalies.append(
            {
                "type_anomalie": TYPE_LOCALISATION_ABSENTE,
                "couche_ouvrage": couche,
                "id_ouvrage": obtenir_id_feature(feature),
                "id_conteneur": reference,
                "motif": motif,
                "geometrie": geometrie_ecart(geometrie, conteneur),
            }
        )
    return anomalies


def compter_ouvrages_a_controler(features: list[dict[str, Any]]) -> int:
    """Compte les ouvrages d'une couche entrant dans le perimetre."""
    return sum(1 for feature in features if est_a_controler(feature.get("properties") or {}))


def _compter_par_motif(anomalies: list[dict[str, Any]]) -> dict[str, int]:
    """Ventile les anomalies par motif pour le rapport JSON."""
    comptes: defaultdict[str, int] = defaultdict(int)
    for anomalie in anomalies:
        comptes[anomalie["motif"]] += 1
    return dict(comptes)


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des ouvrages sans localisation.

    `couche_ouvrage` nomme le type de l'entite : les deux couches partagent le
    meme fichier d'ecarts, l'information serait sinon perdue. La propriete
    `motif` porte le diagnostic, le type d'anomalie etant unique.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": f"{a['couche_ouvrage']}{EXTENSION}",
                "couche_ouvrage": a["couche_ouvrage"],
                "id_ouvrage": a["id_ouvrage"],
                "id_conteneur": a["id_conteneur"],
                "motif": a["motif"],
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


def _resoudre_crs(repertoire: str) -> dict[str, Any] | None:
    """Retourne le crs de la premiere couche cible presente.

    Les couches d'un meme jeu partagent leur systeme de coordonnees ; la
    premiere renseignee suffit a le propager au fichier d'ecarts.
    """
    for couche in COUCHES_CIBLES:
        _, crs, absente = _charger_features(repertoire, f"{couche}{EXTENSION}")
        if not absente and crs is not None:
            return crs
    return None


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de localisation des ouvrages en mode CLI.

    Indexe les conteneurs et les geometries supplementaires, parcourt les deux
    couches controlees et ecrit le fichier d'ecarts GeoJSON. Les couches
    absentes sont remontees au rapport sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    conteneurs, autorises, couches_conteneur_absentes = indexer_conteneurs_autorises(
        repertoire_resolu, COUCHES_CONTENEUR_AUTORISEES
    )
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire_resolu)

    anomalies: list[dict[str, Any]] = []
    ouvrages_controles = 0
    couches_absentes: list[str] = []
    for couche, features, absente in parcourir_ouvrages(repertoire_resolu):
        if absente:
            couches_absentes.append(couche)
            continue
        ouvrages_controles += compter_ouvrages_a_controler(features)
        anomalies.extend(detecter_anomalies_couche(couche, features, conteneurs, autorises, geometries_supplementaires))

    geojson_ecarts = construire_geojson_ecarts(anomalies, _resoudre_crs(repertoire_resolu))

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_motif": _compter_par_motif(anomalies),
        "nombre_ouvrages_controles": ouvrages_controles,
        "nombre_conteneurs_autorises": len(autorises),
        "nombre_geometries_supplementaires": len(geometries_supplementaires),
        "couches_absentes": couches_absentes,
        "couches_conteneur_absentes": couches_conteneur_absentes,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de localisation des ouvrages."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E607 : les RPD_PointDeComptage_Reco et "
            "RPD_OuvrageCollectifBranchement_Reco au statut UnderCommissionning "
            "ou Functional doivent porter une geometrie propre, ou etre "
            "rattaches a un RPD_Coffret_Reco ou RPD_BatimentTechnique_Reco "
            "pourvu d'une geometrie supplementaire valide."
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
