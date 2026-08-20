"""
Controle E605 : chaine de localisation des noeuds sans geometrie propre.

Certains noeuds du reseau ne portent pas de geometrie : leur position est celle
du conteneur qui les heberge, et l'emprise de ce conteneur est decrite par une
geometrie supplementaire. Le controle verifie que cette chaine est complete et
resolue de bout en bout :

    noeud (sans geometrie propre)
      -> conteneur_href                -> conteneur
      -> geometriesupplementaire_href  -> RPD_GeometrieSupplementaire_Reco
      -> geometrie valide

Entites controlees :
    RPD_CoupeCircuitAFusibles_Reco   RPD_SupportModules_Reco
    RPD_JeuBarres_Reco               RPD_Terre_Reco
    RPD_ModuleRaccordement_Reco      RPD_PosteElectrique_Reco

Aucune autre entite n'est controlee.

Detection de la geometrie directe (indispensable)
-------------------------------------------------
Le champ `geometry` du GeoJSON ne peut pas etre teste tel quel. Les sept
extracteurs de `recostar_to_geojson` appliquent la meme regle — « heriter de la
geometrie du conteneur si pas de geometrie propre » — et renseignent donc
`geometry` meme lorsque le GML n'en porte aucune. Tester la simple presence
d'une geometrie signalerait la totalite des entites et mesurerait le
convertisseur, non la donnee.

Le discriminant est l'**egalite avec la geometrie du conteneur** : une geometrie
identique a celle du conteneur est heritee, donc absente a la source ; une
geometrie differente est propre a l'entite, donc directe. Verifie sur les jeux
de reference : 114 des 115 entites portent une geometrie strictement identique a
celle de leur conteneur.

Conteneurs reconnus : RPD_Coffret_Reco, RPD_Support_Reco,
RPD_BatimentTechnique_Reco et RPD_EnceinteCloturee_Reco — les quatre couches qui
alimentent le cache de geometries du convertisseur, donc les seules dont un
noeud puisse heriter sa position.

Regles de gestion, evaluees en cascade :
  - conteneur_absent                       : conteneur_href n'est pas renseigne ;
  - conteneur_introuvable                  : il ne resout aucun conteneur connu ;
  - geometrie_directe_presente             : la geometrie du noeud differe de
                                             celle de son conteneur, elle lui est
                                             donc propre ;
  - geometrie_supplementaire_absente       : le conteneur ne porte pas de
                                             geometriesupplementaire_href ;
  - geometrie_supplementaire_introuvable   : cette reference ne resout aucune
                                             RPD_GeometrieSupplementaire_Reco ;
  - geometrie_supplementaire_invalide      : l'entite existe mais sa geometrie
                                             est absente ou vide.

L'absence de conteneur interrompt la cascade : sans conteneur, ni la comparaison
de geometrie ni la suite de la chaine ne sont evaluables, et les signaler
produirait des anomalies redondantes issues d'une meme cause. Meme parti qu'E600
pour un domaine de tension inconnu. La geometrie directe, elle, est un defaut
propre au noeud : elle n'interrompt pas la verification de la chaine du
conteneur, les deux pouvant coexister.

Un conteneur fautif rend non conformes **tous** les noeuds qu'il heberge : la
regle qualifie l'entite, pas le conteneur, et chaque noeud est effectivement
privee de localisation.

Versions : les champs de relation sont identiques en RecoStaR V1.0 et V1.1 ; le
controle est agnostique de version.

Priorite : bloquant.

Usage CLI :
    python controle_e605.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e605_noeud_localisation_incomplete.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features
from utils_geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Couches controlees
COUCHES_CIBLES: tuple[str, ...] = (
    "RPD_CoupeCircuitAFusibles_Reco",
    "RPD_JeuBarres_Reco",
    "RPD_ModuleRaccordement_Reco",
    "RPD_SupportModules_Reco",
    "RPD_Terre_Reco",
    "RPD_PosteElectrique_Reco",
)

# Couches de conteneur : les quatre dont un noeud peut heriter sa position
COUCHES_CONTENEUR: tuple[str, ...] = (
    "RPD_Coffret_Reco",
    "RPD_Support_Reco",
    "RPD_BatimentTechnique_Reco",
    "RPD_EnceinteCloturee_Reco",
)

# Couche des geometries supplementaires
COUCHE_GEOMETRIE_SUPPLEMENTAIRE: str = "RPD_GeometrieSupplementaire_Reco"

# Extension ajoutee aux noms de couche pour obtenir leur fichier
EXTENSION: str = ".geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e605_noeud_localisation_incomplete.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E605"

# Types d'anomalie produits par ce controle
TYPE_CONTENEUR_ABSENT: str = "conteneur_absent"
TYPE_CONTENEUR_INTROUVABLE: str = "conteneur_introuvable"
TYPE_GEOMETRIE_DIRECTE: str = "geometrie_directe_presente"
TYPE_GEOMSUPP_ABSENTE: str = "geometrie_supplementaire_absente"
TYPE_GEOMSUPP_INTROUVABLE: str = "geometrie_supplementaire_introuvable"
TYPE_GEOMSUPP_INVALIDE: str = "geometrie_supplementaire_invalide"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_CONTENEUR_ABSENT: ("Le nœud n'est rattaché à aucun conteneur."),
    TYPE_CONTENEUR_INTROUVABLE: ("Le conteneur référencé par le nœud n'existe pas."),
    TYPE_GEOMETRIE_DIRECTE: ("Le nœud porte une géométrie propre alors qu'il doit tenir sa position du conteneur."),
    TYPE_GEOMSUPP_ABSENTE: ("Le conteneur du nœud ne référence aucune géométrie supplémentaire."),
    TYPE_GEOMSUPP_INTROUVABLE: ("La géométrie supplémentaire référencée par le conteneur n'existe pas."),
    TYPE_GEOMSUPP_INVALIDE: ("La géométrie supplémentaire référencée existe mais ne porte pas de géométrie valide."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_noeud", "id_conteneur"),
)

# Niveau de priorite affecte a toutes les anomalies. Bloquant : une chaine de
# localisation rompue prive le noeud de toute position exploitable, le
# recolement ne peut pas etre utilise en l'etat (cf. PRIORITES_DECLASSANTES
# dans synthese_controles).
PRIORITE_ANOMALIE: str = "bloquant"

# Noms des champs de relation
CHAMP_CONTENEUR_HREF: str = "conteneur_href"
CHAMP_GEOMSUPP_HREF: str = "geometriesupplementaire_href"

# Cles de la geometrie GeoJSON
CLE_TYPE: str = "type"
CLE_COORDONNEES: str = "coordinates"
CLE_GEOMETRIES: str = "geometries"
TYPE_COLLECTION: str = "GeometryCollection"


@dataclass(frozen=True, slots=True)
class Conteneur:
    """Conteneur susceptible d'heberger un noeud sans geometrie propre."""

    geometrie: dict[str, Any] | None
    href_geomsupp: str | None


# ---------------------------------------------------------------------------
# Validite d'une geometrie
# ---------------------------------------------------------------------------


def geometrie_valide(geometrie: Any) -> bool:
    """Indique si une geometrie GeoJSON est exploitable.

    Une geometrie valide porte un type et un contenu : des coordonnees non
    vides, ou des geometries non vides pour une GeometryCollection. Une
    geometrie nulle, sans type, ou aux coordonnees vides ne localise rien — la
    reference existe alors sans rien decrire.
    """
    if not isinstance(geometrie, dict) or not geometrie.get(CLE_TYPE):
        return False
    if geometrie.get(CLE_TYPE) == TYPE_COLLECTION:
        return bool(geometrie.get(CLE_GEOMETRIES))
    return bool(geometrie.get(CLE_COORDONNEES))


def geometrie_ecart(geometrie: Any, conteneur: "Conteneur | None") -> dict[str, Any] | None:
    """Geometrie a porter par une feature d'ecart, avec repli sur le conteneur.

    L'entite en anomalie est prioritaire : c'est elle que l'operateur cherche.
    Lorsqu'elle n'a pas de position, celle de son conteneur prend le relais afin
    que l'ecart reste localisable dans QGIS ; sans conteneur resolu non plus,
    la feature est ecrite sans geometrie, ce que le format GeoJSON admet.

    Mutualise par les trois controles de chaine de localisation (E605, E606,
    E607), qui appliquent la meme regle de repli.
    """
    if geometrie is not None:
        return geometrie
    return conteneur.geometrie if conteneur is not None else None


def _reference(proprietes: Mapping[str, Any], champ: str) -> str | None:
    """Retourne la reference portee par un champ href, ou None si absente."""
    valeur = proprietes.get(champ)
    if valeur is None:
        return None
    reference = str(valeur).strip()
    return reference or None


# ---------------------------------------------------------------------------
# Chargement des index
# ---------------------------------------------------------------------------


def indexer_conteneurs(repertoire: str) -> tuple[dict[str, Conteneur], list[str]]:
    """Indexe les conteneurs des quatre couches reconnues.

    Retourne (index, couches_absentes). Un noeud ne peut heriter sa position que
    d'un conteneur de ces couches : ce sont celles qui alimentent le cache de
    geometries du convertisseur.
    """
    index: dict[str, Conteneur] = {}
    absentes: list[str] = []
    for couche in COUCHES_CONTENEUR:
        features, _, absent = _charger_features(repertoire, f"{couche}{EXTENSION}")
        if absent:
            absentes.append(couche)
            continue
        for feature in features:
            identifiant = obtenir_id_feature(feature)
            if identifiant is None:
                continue
            proprietes = feature.get("properties") or {}
            index[identifiant] = Conteneur(
                feature.get("geometry"),
                _reference(proprietes, CHAMP_GEOMSUPP_HREF),
            )
    return index, absentes


def indexer_geometries_supplementaires(repertoire: str) -> dict[str, dict[str, Any] | None]:
    """Indexe les RPD_GeometrieSupplementaire_Reco par identifiant."""
    features, _, _ = _charger_features(repertoire, f"{COUCHE_GEOMETRIE_SUPPLEMENTAIRE}{EXTENSION}")
    index: dict[str, dict[str, Any] | None] = {}
    for feature in features:
        identifiant = obtenir_id_feature(feature)
        if identifiant is not None:
            index[identifiant] = feature.get("geometry")
    return index


def est_a_controler(couche: str) -> bool:
    """Indique si une couche entre dans le perimetre du controle.

    Les six couches cibles y entrent sans condition : toutes leurs entites
    tiennent leur position d'un conteneur.
    """
    return couche in COUCHES_CIBLES


def parcourir_noeuds(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]], bool]]:
    """Parcourt les couches controlees, une seule chargee a la fois.

    Retourne (couche, features, absente). Les couches absentes du repertoire
    sont remontees pour le rapport, sans interrompre le controle : un jeu ne
    contient pas necessairement tous les types de noeuds.
    """
    for couche in COUCHES_CIBLES:
        features, _, absente = _charger_features(repertoire, f"{couche}{EXTENSION}")
        yield couche, features, absente


# ---------------------------------------------------------------------------
# Regle metier (fonction pure, testable sans I/O)
# ---------------------------------------------------------------------------


def _classifier_chaine_conteneur(
    conteneur: Conteneur,
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> str | None:
    """Classe la chaine conteneur -> geometrie supplementaire.

    Retourne le code d'anomalie de la premiere rupture rencontree, ou None si la
    chaine aboutit a une geometrie valide.
    """
    if conteneur.href_geomsupp is None:
        return TYPE_GEOMSUPP_ABSENTE
    if conteneur.href_geomsupp not in geometries_supplementaires:
        return TYPE_GEOMSUPP_INTROUVABLE
    if not geometrie_valide(geometries_supplementaires[conteneur.href_geomsupp]):
        return TYPE_GEOMSUPP_INVALIDE
    return None


def classifier_noeud(
    geometrie: Any,
    reference_conteneur: str | None,
    conteneurs: Mapping[str, Conteneur],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[str]:
    """Retourne les codes d'anomalie d'un noeud au regard de sa chaine.

    L'absence de conteneur interrompt la cascade : sans conteneur, ni la
    comparaison de geometrie ni la suite de la chaine ne sont evaluables.

    La geometrie directe n'interrompt pas la verification : c'est un defaut
    propre au noeud, qui peut coexister avec une chaine de conteneur rompue.
    Une geometrie egale a celle du conteneur est heritee, donc absente a la
    source — c'est le seul moyen de distinguer les deux depuis le GeoJSON.
    """
    if reference_conteneur is None:
        return [TYPE_CONTENEUR_ABSENT]
    conteneur = conteneurs.get(reference_conteneur)
    if conteneur is None:
        return [TYPE_CONTENEUR_INTROUVABLE]

    anomalies: list[str] = []
    if geometrie is not None and geometrie != conteneur.geometrie:
        anomalies.append(TYPE_GEOMETRIE_DIRECTE)
    rupture = _classifier_chaine_conteneur(conteneur, geometries_supplementaires)
    if rupture is not None:
        anomalies.append(rupture)
    return anomalies


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    conteneurs: Mapping[str, Conteneur],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les chaines de localisation rompues d'une couche donnee.

    Une couche hors perimetre ne peut produire aucune anomalie : elle est ecartee
    sans etre parcourue.

    La geometrie de l'ecart est celle du noeud si elle existe, a defaut celle de
    son conteneur : un noeud sans position ne serait sinon pas localisable.
    """
    if not est_a_controler(couche):
        return []
    anomalies: list[dict[str, Any]] = []
    classifier = classifier_noeud  # alias local
    for feature in features:
        proprietes = feature.get("properties") or {}
        reference = _reference(proprietes, CHAMP_CONTENEUR_HREF)
        geometrie = feature.get("geometry")
        conteneur = conteneurs.get(reference) if reference is not None else None
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "couche_noeud": couche,
                "id_noeud": obtenir_id_feature(feature),
                "id_conteneur": reference,
                "id_geometrie_supplementaire": conteneur.href_geomsupp if conteneur is not None else None,
                "geometrie": geometrie_ecart(geometrie, conteneur),
            }
            for type_anomalie in classifier(geometrie, reference, conteneurs, geometries_supplementaires)
        )
    return anomalies


def compter_noeuds_a_controler(couche: str, features: list[dict[str, Any]]) -> int:
    """Compte les entites d'une couche entrant dans le perimetre."""
    return len(features) if est_a_controler(couche) else 0


def compter_noeuds_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les noeuds distincts portant au moins une anomalie."""
    return len({(anomalie["couche_noeud"], anomalie["id_noeud"]) for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des chaines de localisation rompues.

    `couche_noeud` nomme le type du noeud : les six couches controlees partagent
    le meme fichier d'ecarts, l'information serait sinon perdue.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": f"{a['couche_noeud']}{EXTENSION}",
                "couche_noeud": a["couche_noeud"],
                "id_noeud": a["id_noeud"],
                "id_conteneur": a["id_conteneur"],
                "id_geometrie_supplementaire": a["id_geometrie_supplementaire"],
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
    """Execute le controle de la chaine de localisation des noeuds en mode CLI.

    Indexe les conteneurs et les geometries supplementaires, parcourt les six
    couches controlees et ecrit le fichier d'ecarts GeoJSON. Les couches
    absentes sont remontees au rapport sans bloquer : un jeu ne contient pas
    necessairement tous les types de noeuds.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    conteneurs, conteneurs_absents = indexer_conteneurs(repertoire_resolu)
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire_resolu)

    anomalies: list[dict[str, Any]] = []
    noeuds_controles = 0
    couches_absentes: list[str] = []
    for couche, features, absente in parcourir_noeuds(repertoire_resolu):
        if absente:
            couches_absentes.append(couche)
            continue
        noeuds_controles += compter_noeuds_a_controler(couche, features)
        anomalies.extend(detecter_anomalies_couche(couche, features, conteneurs, geometries_supplementaires))

    geojson_ecarts = construire_geojson_ecarts(anomalies, _resoudre_crs(repertoire_resolu))

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_noeuds_controles": noeuds_controles,
        "nombre_noeuds_non_conformes": compter_noeuds_non_conformes(anomalies),
        "nombre_conteneurs": len(conteneurs),
        "nombre_geometries_supplementaires": len(geometries_supplementaires),
        "couches_absentes": couches_absentes,
        "couches_conteneur_absentes": conteneurs_absents,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de la chaine de localisation des noeuds."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E605 : les noeuds sans geometrie propre doivent etre "
            "rattaches a un conteneur porteur d'une geometrie supplementaire "
            "valide."
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
