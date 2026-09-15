"""
Controle E-5108 : superpositions geometriques entre cheminements Recostar.

Detecte les chevauchements spatiaux (totaux ou partiels) entre les entites
lineaires des fichiers de cheminement suivants :
  - RPD_Fourreau_Reco.geojson
  - RPD_Galerie_Reco.geojson
  - RPD_PleineTerre_Reco.geojson
  - RPD_ProtectionMecanique_Reco.geojson
  - RPD_Aerien_Reco.geojson

Deux niveaux de controle :
  1. Intra-couche : superpositions entre entites d'un meme fichier.
  2. Inter-couches : superpositions entre entites de fichiers differents.

La detection est planimetrique (2D). Les valeurs Z sont ignorees afin de
signaler les superpositions physiques independamment des ecarts altimetriques.

**Qualification attributaire.** La seule superposition geometrique ne suffit
pas : deux cheminements distincts peuvent legitimement se recouvrir s'ils
portent des cables differents. L'anomalie visee est le *doublon de saisie* —
un meme cable trace sur deux cheminements qui se recouvrent. La paire n'est
donc retenue que si les deux entites partagent au moins un identifiant de
cable dans leur champ `cables_href`.

Corollaire : une paire dont l'un des deux cheminements ne porte aucune
reference de cable n'est pas signalee, l'intersection des references etant
vide. Rien ne permettrait d'y etablir le doublon que le controle recherche.

Usage CLI :
    python -m recostar.controle.cheminement.e5108 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e5108_superpositions_cheminements.geojson
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely import STRtree, force_2d, is_valid
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    FICHIERS_CHEMINEMENT,
)
from recostar.controle.fonctions_communes.references_cables import extraire_ids_cables_href as _extraire_ids_cables_href

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5108_superpositions_cheminements.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E-5108"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "superposition_cheminements": ("Deux cheminements portant le même câble se superposent géométriquement."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite_a", "id_entite_b"),
)


# Longueur minimale (metres) d'un chevauchement pour etre signale
EPSILON_LONGUEUR: float = 0.01

# Ratio de recouvrement au-dela duquel la superposition est classifiee totale.
# Une superposition est totale si le chevauchement couvre >= 99 % de la plus
# courte des deux entites comparees.
SEUIL_SUPERPOSITION_TOTALE: float = 0.99

# Types de geometries lineaires acceptes pour ce controle
TYPES_GEOMETRIE_LINEAIRE: frozenset[str] = frozenset({"LineString", "MultiLineString"})


@dataclass(slots=True)
class EntiteCheminement:
    """Entite lineaire d'un fichier de cheminement avec sa geometrie 2D Shapely."""

    couche: str
    id_entite: str | None
    geometrie: BaseGeometry  # geometrie planimetrique (force 2D)
    # References cables du champ `cables_href`. frozenset : l'intersection de
    # deux entites est l'operation du filtre attributaire, executee sur chaque
    # paire candidate de la boucle de detection.
    ids_cables: frozenset[str]


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def _creer_entite_depuis_feature(
    feature: dict[str, Any],
    couche: str,
) -> "EntiteCheminement | None":
    """Cree une EntiteCheminement depuis une feature GeoJSON.

    Retourne None si la geometrie est absente, non lineaire, invalide
    ou de longueur negligeable. Le try/except est justifie : shape() peut
    echouer sur des coordonnees malformees (lecture depuis fichier externe).
    """
    geom_dict = feature.get("geometry")
    if geom_dict is None or geom_dict.get("type") not in TYPES_GEOMETRIE_LINEAIRE:
        return None
    if not geom_dict.get("coordinates"):
        return None

    try:
        geom = force_2d(shape(geom_dict))
    except Exception:
        return None

    if geom.is_empty or not is_valid(geom) or geom.length < EPSILON_LONGUEUR:
        return None

    proprietes = feature.get("properties") or {}
    return EntiteCheminement(
        couche=couche,
        id_entite=obtenir_id_feature(feature),
        geometrie=geom,
        ids_cables=frozenset(_extraire_ids_cables_href(proprietes.get(CHAMP_CABLES_HREF))),
    )


def charger_entites_couche(
    chemin: str,
    nom_couche: str,
) -> tuple[list["EntiteCheminement"], dict[str, Any] | None]:
    """Charge les entites lineaires d'un fichier de cheminement.

    Retourne (entites, crs). Le CRS est extrait depuis la FeatureCollection
    et propage vers la sortie pour assurer l'affichage correct dans QGIS.
    """
    collection = lire_geojson(chemin)
    if collection is None:
        return [], None

    crs = collection.get("crs")
    entites: list[EntiteCheminement] = []
    for feature in collection.get("features", []):
        entite = _creer_entite_depuis_feature(feature, nom_couche)
        if entite is not None:
            entites.append(entite)

    return entites, crs


def _charger_toutes_entites(
    repertoire: str,
) -> tuple[list["EntiteCheminement"], dict[str, Any] | None, list[str]]:
    """Charge l'ensemble des entites depuis les fichiers de cheminement presents.

    Retourne (entites, crs, fichiers_absents). Le CRS est celui du premier
    fichier trouve ; les fichiers manquants sont listes sans erreur.
    """
    toutes_entites: list[EntiteCheminement] = []
    crs: dict[str, Any] | None = None
    fichiers_absents: list[str] = []

    for nom_fichier in FICHIERS_CHEMINEMENT:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        entites, crs_couche = charger_entites_couche(chemin, nom_fichier)
        if crs is None:
            crs = crs_couche
        toutes_entites.extend(entites)

    return toutes_entites, crs, fichiers_absents


# ---------------------------------------------------------------------------
# Detection des superpositions
# ---------------------------------------------------------------------------


def _est_chevauchement_lineaire(intersection: BaseGeometry) -> bool:
    """Verifie si une geometrie d'intersection constitue un chevauchement lineaire.

    Un chevauchement est lineaire (et significatif) si sa longueur depasse
    EPSILON_LONGUEUR. Les intersections ponctuelles (croisements en T ou X)
    sont ainsi ecartees.
    """
    return not intersection.is_empty and intersection.length > EPSILON_LONGUEUR


def _classifier_superposition(
    intersection: BaseGeometry,
    geom_a: BaseGeometry,
    geom_b: BaseGeometry,
) -> str:
    """Classifie la superposition en 'totale' ou 'partielle'.

    La superposition est totale si le chevauchement couvre au moins
    SEUIL_SUPERPOSITION_TOTALE de la longueur de la plus courte des deux
    entites. Ce ratio tolere les imprecisions de calcul geometrique.
    """
    longueur_min = min(geom_a.length, geom_b.length)
    if longueur_min < EPSILON_LONGUEUR:
        return "partielle"
    ratio = intersection.length / longueur_min
    return "totale" if ratio >= SEUIL_SUPERPOSITION_TOTALE else "partielle"


def cables_partages(
    entite_a: "EntiteCheminement",
    entite_b: "EntiteCheminement",
) -> frozenset[str]:
    """Retourne les cables references par les deux cheminements a la fois.

    Un seul identifiant commun suffit a etablir le lien attributaire : c'est ce
    cable-la qui est trace deux fois. Un ensemble vide signifie soit des cables
    distincts, soit une reference absente d'au moins un des deux cheminements —
    deux situations ou le doublon ne peut pas etre etabli.
    """
    return entite_a.ids_cables & entite_b.ids_cables


def _analyser_paire(
    entite_a: "EntiteCheminement",
    entite_b: "EntiteCheminement",
) -> dict[str, Any] | None:
    """Construit l'anomalie d'une paire de cheminements, si elle en constitue une.

    Retourne None lorsque les deux entites ne partagent aucun cable, ou lorsque
    leur intersection n'est pas un chevauchement lineaire significatif.

    Le filtre attributaire precede le calcul geometrique : il compare deux
    ensembles de quelques elements, la ou `intersection()` est l'operation
    couteuse de la boucle de detection.
    """
    cables_communs = cables_partages(entite_a, entite_b)
    if not cables_communs:
        return None

    intersection = entite_a.geometrie.intersection(entite_b.geometrie)
    if not _est_chevauchement_lineaire(intersection):
        return None

    niveau = "intra_couche" if entite_a.couche == entite_b.couche else "inter_couches"
    type_superposition = _classifier_superposition(intersection, entite_a.geometrie, entite_b.geometrie)

    return {
        "niveau": niveau,
        "couche_a": entite_a.couche,
        "id_entite_a": entite_a.id_entite,
        "couche_b": entite_b.couche,
        "id_entite_b": entite_b.id_entite,
        "type_superposition": type_superposition,
        "longueur_chevauchement_m": round(intersection.length, 3),
        # Tri : rend la sortie deterministe d'une execution a l'autre, un
        # frozenset n'ayant pas d'ordre stable.
        "cables_communs": sorted(cables_communs),
        "geometrie_intersection": mapping(intersection),
    }


def detecter_toutes_superpositions(
    entites: list["EntiteCheminement"],
) -> list[dict[str, Any]]:
    """Detecte toutes les superpositions intra et inter-couches.

    Construit un STRtree global sur l'ensemble des entites, puis pour chaque
    entite interroge l'index avec le predicat 'intersects'. Chaque paire
    (i, j) avec i < j est traitee une seule fois, ce qui evite les doublons
    et l'auto-comparaison sans gestion de set supplementaire.
    """
    if len(entites) < 2:
        return []

    geometries = [e.geometrie for e in entites]
    arbre = STRtree(geometries)
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_paire  # alias local : evite le lookup global en boucle

    for i, entite_a in enumerate(entites):
        indices = arbre.query(entite_a.geometrie, predicate="intersects")
        for j in indices:
            if j <= i:
                continue
            anomalie = analyser(entite_a, entites[j])
            if anomalie is not None:
                anomalies.append(anomalie)

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _construire_feature_anomalie(anomalie: dict[str, Any]) -> dict[str, Any]:
    """Construit une feature GeoJSON depuis une anomalie de superposition.

    La geometrie de la feature est la portion de chevauchement calculee,
    ce qui permet une localisation precise dans QGIS.
    """
    id_a = anomalie["id_entite_a"]
    id_b = anomalie["id_entite_b"]
    return {
        "type": "Feature",
        "properties": {
            "niveau": anomalie["niveau"],
            "couche_a": anomalie["couche_a"],
            "id_entite_a": str(id_a) if id_a is not None else None,
            "couche_b": anomalie["couche_b"],
            "id_entite_b": str(id_b) if id_b is not None else None,
            "type_superposition": anomalie["type_superposition"],
            "longueur_chevauchement_m": anomalie["longueur_chevauchement_m"],
            # Cables a l'origine du signalement : sans eux, l'ecart ne serait
            # pas exploitable en retour terrain.
            "cables_communs": ",".join(anomalie["cables_communs"]),
            "type_anomalie": "superposition_cheminements",
        },
        "geometry": anomalie["geometrie_intersection"],
    }


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des superpositions detectees.

    Chaque feature represente une paire de cheminements en superposition ;
    sa geometrie est la portion de chevauchement calculee par Shapely.
    Le champ crs est propage depuis les fichiers sources pour QGIS.
    """
    features = [_construire_feature_anomalie(a) for a in anomalies]
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
    """Execute le controle de superpositions de cheminements en mode CLI.

    Charge les fichiers de cheminement presents dans le repertoire, detecte les
    superpositions intra et inter-couches entre cheminements partageant un
    cable, puis ecrit le fichier d'ecarts GeoJSON dans le dossier de sortie.
    Les fichiers absents ne bloquent pas l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    toutes_entites, crs, fichiers_absents = _charger_toutes_entites(repertoire_resolu)
    anomalies = detecter_toutes_superpositions(toutes_entites)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_entites_analysees": len(toutes_entites),
        "fichiers_absents": fichiers_absents,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle de superpositions de cheminements."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-5108 : detection des superpositions geometriques entre "
            "cheminements Recostar portant un meme cable (Fourreau, PleineTerre, "
            "Aerien, ProtectionMecanique)."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers de cheminement GeoJSON",
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
