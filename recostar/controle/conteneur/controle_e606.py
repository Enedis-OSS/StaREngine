"""
Controle E606 : localisation des remontees aero-souterraines.

Une entite RPD_Jonction_Reco decrivant une remontee aero-souterraine doit etre
localisable. Deux voies sont admises, et l'une des deux suffit :

    Cas 1 — geometrie propre : la jonction porte elle-meme une geometrie valide.
    Cas 2 — geometrie par le support : la jonction est rattachee a un
            RPD_Support_Reco existant, qui reference une
            RPD_GeometrieSupplementaire_Reco resolue et pourvue d'une geometrie
            valide.

Une jonction ne satisfaisant aucune des deux voies n'a aucune position
exploitable : une anomalie est emise.

Perimetre : entites RPD_Jonction_Reco remplissant les deux conditions
cumulatives suivantes :
  - TypeJonction vaut RemonteeAeroSouterraine ;
  - Statut vaut UnderCommissionning ou Functional.
Toutes les autres jonctions sont ignorees.

Ce qu'est une geometrie « propre » (indispensable)
--------------------------------------------------
Le champ `geometry` du GeoJSON ne peut pas etre teste tel quel. L'extracteur de
jonction de `recostar_to_geojson` applique la meme regle que les autres noeuds —
« heriter de la geometrie du conteneur si pas de geometrie propre » — et
renseigne donc `geometry` meme lorsque le GML n'en porte aucune.

Lire le cas 1 comme « le champ geometry est renseigne » le rendrait vrai pour
toute jonction rattachee a un conteneur, et **le cas 2 deviendrait
inatteignable** : la disjonction perdrait tout contenu. Le discriminant est donc
le meme qu'en E605 — une geometrie identique a celle du conteneur est heritee,
donc absente a la source ; une geometrie differente, ou portee sans conteneur
resolu, est propre a la jonction.

Verifie sur les jeux de reference : les deux voies sont effectivement
empruntees, 2 jonctions par le cas 1 et 7 par le cas 2.

Le cas 2 exige un RPD_Support_Reco, non un conteneur quelconque : une remontee
aero-souterraine est portee par un support. Un rattachement a un coffret ou a un
batiment technique ne satisfait donc pas le cas 2.

Anomalie : un seul type, `localisation_absente` — la regle est une disjonction,
son echec est unique. La propriete `motif` precise ou la voie du support s'est
interrompue, afin que le diagnostic reste possible sans multiplier les types.

Versions : les champs de relation sont identiques en RecoStaR V1.0 et V1.1 ; le
controle est agnostique de version.

Priorite : bloquant.

Usage CLI :
    python controle_e606.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e606_remontee_localisation_absente.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features

# Definition de la geometrie valide, index des geometries supplementaires et
# champs de relation mutualises avec E605 : les deux controles evaluent la meme
# chaine de localisation, sur des entites differentes.
from controle_e605 import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_GEOMSUPP_HREF,
    COUCHES_CONTENEUR,
    EXTENSION,
    Conteneur,
    _reference,
    geometrie_ecart,
    geometrie_valide,
    indexer_geometries_supplementaires,
)
from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source des entites controlees
FICHIER_JONCTION: str = "RPD_Jonction_Reco.geojson"

# Couche de support, seule admise par le cas 2
COUCHE_SUPPORT: str = "RPD_Support_Reco"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e606_remontee_localisation_absente.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E606"

# Type d'anomalie unique : la regle est une disjonction, son echec est unique.
TYPE_LOCALISATION_ABSENTE: str = "localisation_absente"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_LOCALISATION_ABSENTE: (
        "La remontée aéro-souterraine n'a ni géométrie propre ni support porteur d'une géométrie valide."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction", "id_support"),
)

# Niveau de priorite affecte a toutes les anomalies. Bloquant : une remontee
# sans position exploitable ne peut pas etre reportee sur le terrain, le
# recolement n'est pas utilisable en l'etat (cf. PRIORITES_DECLASSANTES dans
# synthese_controles).
PRIORITE_ANOMALIE: str = "bloquant"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_TYPE_JONCTION: str = "TypeJonction"

# Perimetre du controle
TYPE_JONCTION_CONTROLE: str = "RemonteeAeroSouterraine"
STATUTS_CONTROLES: frozenset[str] = frozenset({"UnderCommissionning", "Functional"})

# Motifs d'echec de la voie du support, exposes au diagnostic
MOTIF_SUPPORT_ABSENT: str = "support_absent"
MOTIF_SUPPORT_INTROUVABLE: str = "support_introuvable"
MOTIF_CONTENEUR_NON_SUPPORT: str = "conteneur_non_support"
MOTIF_GEOMSUPP_ABSENTE: str = "geometrie_supplementaire_absente"
MOTIF_GEOMSUPP_INTROUVABLE: str = "geometrie_supplementaire_introuvable"
MOTIF_GEOMSUPP_INVALIDE: str = "geometrie_supplementaire_invalide"


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def indexer_conteneurs_autorises(
    repertoire: str,
    couches_autorisees: frozenset[str],
) -> tuple[dict[str, Conteneur], frozenset[str], list[str]]:
    """Indexe les conteneurs et distingue ceux des couches autorisees.

    Retourne (conteneurs, identifiants_autorises, couches_absentes). Les quatre
    couches de conteneur sont indexees : elles servent a reconnaitre une
    geometrie heritee, quelle que soit la nature du conteneur. Seuls les
    conteneurs des couches autorisees sont retenus dans le second ensemble, la
    voie du conteneur n'admettant qu'eux.

    Les deux index sont construits en une passe : relire les couches autorisees
    pour les separer serait sans benefice.

    Les couches autorisees sont un parametre et non une constante : E606
    n'admet que les supports, E607 les coffrets et batiments techniques. La
    mecanique d'indexation, elle, est la meme.
    """
    conteneurs: dict[str, Conteneur] = {}
    autorises: set[str] = set()
    absentes: list[str] = []
    for couche in COUCHES_CONTENEUR:
        features, _, absente = _charger_features(repertoire, f"{couche}{EXTENSION}")
        if absente:
            absentes.append(couche)
            continue
        for feature in features:
            identifiant = obtenir_id_feature(feature)
            if identifiant is None:
                continue
            proprietes = feature.get("properties") or {}
            conteneurs[identifiant] = Conteneur(
                feature.get("geometry"),
                _reference(proprietes, CHAMP_GEOMSUPP_HREF),
            )
            if couche in couches_autorisees:
                autorises.add(identifiant)
    return conteneurs, frozenset(autorises), absentes


def indexer_conteneurs_et_supports(
    repertoire: str,
) -> tuple[dict[str, Conteneur], frozenset[str], list[str]]:
    """Indexe les conteneurs et distingue ceux qui sont des supports.

    Specialisation de `indexer_conteneurs_autorises` a la seule couche admise
    par le cas 2 de ce controle.
    """
    return indexer_conteneurs_autorises(repertoire, frozenset({COUCHE_SUPPORT}))


# ---------------------------------------------------------------------------
# Regles metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_controler(proprietes: Mapping[str, Any]) -> bool:
    """Indique si une jonction entre dans le perimetre du controle.

    Deux conditions cumulatives : TypeJonction RemonteeAeroSouterraine et Statut
    UnderCommissionning ou Functional.
    """
    if proprietes.get(CHAMP_TYPE_JONCTION) != TYPE_JONCTION_CONTROLE:
        return False
    return proprietes.get(CHAMP_STATUT) in STATUTS_CONTROLES


def possede_geometrie_propre(
    geometrie: Any,
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
) -> bool:
    """Cas 1 : la jonction porte-t-elle une geometrie qui lui est propre ?

    Une geometrie identique a celle du conteneur a ete injectee par l'export,
    elle est donc absente a la source. Une geometrie portee sans conteneur
    resolu ne peut venir de nulle part ailleurs : elle est propre.
    """
    if not geometrie_valide(geometrie):
        return False
    conteneur = conteneurs.get(reference) if reference is not None else None
    if conteneur is None:
        return True
    return geometrie != conteneur.geometrie


def motif_echec_support(
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
    supports: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Cas 2 : parcourt la voie du support et retourne le motif de sa rupture.

    Retourne None lorsque la voie aboutit a une geometrie valide. Les motifs
    distinguent un rattachement absent, un support introuvable, un conteneur qui
    n'est pas un support, et les trois ruptures de la chaine de geometrie
    supplementaire.
    """
    if reference is None:
        return MOTIF_SUPPORT_ABSENT
    if reference not in conteneurs:
        return MOTIF_SUPPORT_INTROUVABLE
    if reference not in supports:
        return MOTIF_CONTENEUR_NON_SUPPORT
    href = conteneurs[reference].href_geomsupp
    if href is None:
        return MOTIF_GEOMSUPP_ABSENTE
    if href not in geometries_supplementaires:
        return MOTIF_GEOMSUPP_INTROUVABLE
    if not geometrie_valide(geometries_supplementaires[href]):
        return MOTIF_GEOMSUPP_INVALIDE
    return None


def classifier_jonction(
    geometrie: Any,
    reference: str | None,
    conteneurs: Mapping[str, Conteneur],
    supports: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Retourne le motif d'echec de la jonction, ou None si elle est localisable.

    Le cas 1 est evalue en premier : une geometrie propre suffit, la voie du
    support n'a alors pas a etre parcourue. Le motif retourne decrit donc
    toujours l'echec du cas 2, seul restant a examiner.
    """
    if possede_geometrie_propre(geometrie, reference, conteneurs):
        return None
    return motif_echec_support(reference, conteneurs, supports, geometries_supplementaires)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    features: list[dict[str, Any]],
    conteneurs: Mapping[str, Conteneur],
    supports: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les remontees aero-souterraines depourvues de localisation.

    La geometrie de l'ecart est celle de la jonction si elle existe, a defaut
    celle de son conteneur : une jonction sans position ne serait sinon pas
    localisable dans QGIS.
    """
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_jonction  # alias local
    for feature in features:
        proprietes = feature.get("properties") or {}
        if not est_a_controler(proprietes):
            continue
        reference = _reference(proprietes, CHAMP_CONTENEUR_HREF)
        geometrie = feature.get("geometry")
        motif = classifier(geometrie, reference, conteneurs, supports, geometries_supplementaires)
        if motif is None:
            continue
        conteneur = conteneurs.get(reference) if reference is not None else None
        anomalies.append(
            {
                "type_anomalie": TYPE_LOCALISATION_ABSENTE,
                "id_jonction": obtenir_id_feature(feature),
                "id_support": reference,
                "motif": motif,
                "geometrie": geometrie_ecart(geometrie, conteneur),
            }
        )
    return anomalies


def compter_jonctions_a_controler(features: list[dict[str, Any]]) -> int:
    """Compte les jonctions entrant dans le perimetre du controle."""
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
    """Construit un FeatureCollection des remontees sans localisation.

    La propriete `motif` porte le diagnostic : le type d'anomalie etant unique,
    c'est elle qui indique ou la voie du support s'est interrompue.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_JONCTION,
                "id_jonction": a["id_jonction"],
                "id_support": a["id_support"],
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


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de localisation des remontees en mode CLI.

    Indexe les conteneurs, les supports et les geometries supplementaires,
    controle chaque remontee du perimetre et ecrit le fichier d'ecarts GeoJSON.
    L'absence d'un fichier source est signalee sans bloquer.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    conteneurs, supports, couches_conteneur_absentes = indexer_conteneurs_et_supports(repertoire_resolu)
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire_resolu)

    features, crs, jonction_absente = _charger_features(repertoire_resolu, FICHIER_JONCTION)

    anomalies = detecter_anomalies(features, conteneurs, supports, geometries_supplementaires)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_motif": _compter_par_motif(anomalies),
        "nombre_jonctions_analysees": len(features),
        "nombre_jonctions_controlees": compter_jonctions_a_controler(features),
        "nombre_supports": len(supports),
        "nombre_geometries_supplementaires": len(geometries_supplementaires),
        "fichier_jonction_absent": jonction_absente,
        "couches_conteneur_absentes": couches_conteneur_absentes,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de localisation des remontees."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E606 : les RPD_Jonction_Reco de TypeJonction "
            "RemonteeAeroSouterraine au statut UnderCommissionning ou Functional "
            "doivent porter une geometrie propre, ou etre rattachees a un "
            "RPD_Support_Reco pourvu d'une geometrie supplementaire valide."
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
