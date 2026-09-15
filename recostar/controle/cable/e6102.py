"""
Controle E-6102 : Le câble n'est pas coupé à chaque nœud

Un noeud du reseau pose sur le trace d'un cable doit l'interrompre : le cable
doit s'y terminer, et un second cable repartir de la. Un cable qui traverse un
noeud sans etre scinde decrit une topologie fausse — le reseau y parait continu
alors qu'il y a un ouvrage.

Perimetre : RPD_CableElectrique_Reco au Statut UnderCommissionning, et les
noeuds qui les referencent par leur champ `cables_href`. Meme perimetre de cable
que les controles de raccordement, dont celui-ci est le complement topologique.

Frontiere avec E-6111
---------------------
Les deux controles parcourent la meme relation, en sens inverse :

  - E-6111 part des **extremites** : un bout de cable que ne couvre aucun noeud
    est signale ;
  - E-6102 part des **noeuds** : un noeud pose sur le trace, mais a aucune
    extremite, est signale.

Un noeud qui n'est ni a une extremite ni sur le trace est donc **hors perimetre
de ce controle** : il decrit un noeud lie au cable sans en toucher la geometrie,
ce qu'E-6111 qualifie deja. Le signaler ici produirait une seconde anomalie pour
une meme cause, contre la regle du projet : un defaut, un code.

Ce qui vaut « le cable est coupe a ce noeud »
---------------------------------------------
La position d'un noeud n'est pas toujours celle a laquelle le cable doit
s'arreter. Le modele chaine trois maillons :

    noeud -> conteneur_href -> conteneur -> geometriesupplementaire_href
                                         -> RPD_GeometrieSupplementaire_Reco

Un noeud heberge dans un poste ou un batiment technique tient sa position du
conteneur, dont l'emprise reelle est decrite par une geometrie supplementaire.
Le cable s'arrete alors au bord de cette emprise, non au point du conteneur :
exiger la coincidence avec le point ferait ressortir tout un poste en anomalie.

Deux voies valent donc conformite, et l'une des deux suffit :

    Cas 1 — une extremite du cable coincide avec la position du noeud ;
    Cas 2 — une extremite du cable touche la geometrie supplementaire du
            conteneur du noeud.

Le cas 2 n'est evalue que si la chaine aboutit a une geometrie valide ; sa
rupture releve d'E-6106, non de ce controle.

Tolerance : `TOLERANCE_SUPERPOSITION` (1 mm), la constante du projet pour les
contacts de mesure nulle — point sur une ligne, point sur un contour. Elle
couvre exactement l'arrondi millimetrique de la donnee source et rien de plus.
Un noeud reellement decale, meme au centimetre, reste detecte.

Regle de gestion : une anomalie est emise **par couple (cable, noeud)** fautif,
convention des controles de relation du projet. Un cable traversant deux noeuds
porte deux anomalies : chaque coupure manquante est a realiser pour elle-meme.

Geometrie des ecarts : le point du noeud traverse, qui localise la coupure a
realiser.

Versions : les champs exploites sont identiques en RecoStaR V1.0 et V1.1 ; le
controle est agnostique de version.

Usage CLI :
    python -m recostar.controle.cable.e6102 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6102_cable_non_coupe_au_noeud.geojson
"""

import argparse
import json
import math
import os
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.geometrie import (
    TOLERANCE_SUPERPOSITION,
    distance_au_point,
    extraire_extremites,
    extraire_point_xy,
    forme_shapely,
)
from recostar.controle.fonctions_communes.localisation_conteneur import (
    indexer_conteneurs,
    indexer_geometries_supplementaires,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    CHAMP_CONTENEUR_HREF,
    EXTENSION_COUCHE,
    FICHIER_CABLE_ELECTRIQUE,
)
from recostar.controle.fonctions_communes.proprietes import reference_href
from recostar.controle.fonctions_communes.references_cables import (
    charger_types_noeuds_reseau,
    extraire_ids_cables_href,
    filtrer_cables_a_controler,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6102_cable_non_coupe_au_noeud.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6102"

# Type d'anomalie unique produit par ce controle
TYPE_CABLE_NON_COUPE: str = "cable_non_coupe_au_noeud"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_CABLE_NON_COUPE: ("Le câble traverse le nœud sans y être coupé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable", "id_noeud"),
)


@dataclass(frozen=True, slots=True)
class NoeudTraverse:
    """Noeud referencant un cable, avec de quoi juger la coupure.

    `emprise` est la forme shapely de la geometrie supplementaire du conteneur
    du noeud, deja convertie : elle est confrontee a chaque extremite de chaque
    cable que le noeud reference, et la reconstruire a chaque comparaison serait
    le cout dominant du controle.
    """

    couche: str
    identifiant: str | None
    point: tuple[float, float]
    emprise: Any | None


# ---------------------------------------------------------------------------
# Chargement de l'index des noeuds
# ---------------------------------------------------------------------------


def resoudre_emprise(
    proprietes: Mapping[str, Any],
    conteneurs: Mapping[str, Any],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
    formes: dict[str, Any | None],
) -> Any | None:
    """Retourne l'emprise du conteneur d'un noeud, ou None si la chaine n'aboutit pas.

    Parcourt `noeud -> conteneur -> geometrie supplementaire`. Chaque emprise
    n'est convertie en forme shapely qu'une fois, `formes` servant de cache
    indexe par identifiant de geometrie supplementaire : un poste heberge
    plusieurs noeuds, qui partagent la meme emprise.

    Une rupture de la chaine — pas de conteneur, conteneur introuvable, pas de
    geometrie supplementaire, geometrie invalide — retourne None : elle releve
    d'E-6105 et d'E-6106, pas de ce controle.
    """
    reference = reference_href(proprietes, CHAMP_CONTENEUR_HREF)
    if reference is None:
        return None
    conteneur = conteneurs.get(reference)
    if conteneur is None or conteneur.href_geomsupp is None:
        return None
    identifiant = conteneur.href_geomsupp
    if identifiant not in formes:
        formes[identifiant] = forme_shapely(geometries_supplementaires.get(identifiant))
    return formes[identifiant]


def indexer_noeuds_par_cable(repertoire: str) -> tuple[dict[str, list[NoeudTraverse]], list[str]]:
    """Construit l'index {id_cable: [noeuds]} depuis toutes les couches de noeud.

    Retourne (index, couches_absentes). Les types de noeuds proviennent du module
    de conversion, source de verite unique — meme parti que les controles de
    raccordement. Un noeud
    depourvu de geometrie Point est ecarte : sans position, la coupure n'est pas
    jugeable, et son defaut de localisation releve d'E-6105 a E-6109.
    """
    conteneurs, _ = indexer_conteneurs(repertoire)
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire)
    formes_emprises: dict[str, Any | None] = {}

    index: dict[str, list[NoeudTraverse]] = {}
    couches_absentes: list[str] = []
    extraire_ids = extraire_ids_cables_href  # alias locaux (boucle)
    extraire_point = extraire_point_xy
    for couche in charger_types_noeuds_reseau():
        features, _, absente = charger_features(repertoire, f"{couche}{EXTENSION_COUCHE}")
        if absente:
            couches_absentes.append(couche)
            continue
        for feature in features:
            proprietes = feature.get("properties") or {}
            ids_cables = extraire_ids(proprietes.get(CHAMP_CABLES_HREF))
            if not ids_cables:
                continue
            point = extraire_point(feature.get("geometry"))
            if point is None:
                continue
            noeud = NoeudTraverse(
                couche=couche,
                identifiant=obtenir_id_feature(feature),
                point=point,
                emprise=resoudre_emprise(proprietes, conteneurs, geometries_supplementaires, formes_emprises),
            )
            for id_cable in ids_cables:
                index.setdefault(id_cable, []).append(noeud)
    return index, couches_absentes


# ---------------------------------------------------------------------------
# Regle metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def est_a_une_extremite(noeud: NoeudTraverse, extremites: list[tuple[float, float]]) -> bool:
    """Indique si le cable est coupe au droit du noeud.

    Deux voies, l'une des deux suffisant : une extremite coincide avec le point
    du noeud (cas 1), ou une extremite touche l'emprise de son conteneur
    (cas 2). Le cas 1 est evalue en premier : c'est le plus courant et le moins
    couteux, l'emprise n'ayant alors pas a etre confrontee.
    """
    distance = math.dist  # alias local (boucle)
    for extremite in extremites:
        if distance(noeud.point, extremite) <= TOLERANCE_SUPERPOSITION:
            return True
    if noeud.emprise is None:
        return False
    for extremite in extremites:
        ecart = distance_au_point(noeud.emprise, extremite)
        if ecart is not None and ecart <= TOLERANCE_SUPERPOSITION:
            return True
    return False


def est_sur_le_trace(trace: Any | None, noeud: NoeudTraverse) -> bool:
    """Indique si le noeud est pose sur le trace du cable.

    C'est la condition qui distingue une coupure manquante d'un simple defaut de
    jointure : le cable passe bien par le noeud, mais n'y est pas scinde. Un
    noeud a l'ecart du trace releve d'E-6111.
    """
    ecart = distance_au_point(trace, noeud.point)
    return ecart is not None and ecart <= TOLERANCE_SUPERPOSITION


def classifier_noeud(noeud: NoeudTraverse, extremites: list[tuple[float, float]], trace: Any | None) -> bool:
    """Indique si le cable traverse le noeud sans y etre coupe.

    L'appartenance au trace est evaluee en second : la grande majorite des
    noeuds sont a une extremite, et la mesure de distance a la geometrie est
    plus couteuse que la comparaison a deux points.
    """
    if est_a_une_extremite(noeud, extremites):
        return False
    return est_sur_le_trace(trace, noeud)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_cable(
    feature: dict[str, Any],
    noeuds: list[NoeudTraverse],
) -> list[dict[str, Any]]:
    """Detecte les noeuds qu'un cable traverse sans y etre coupe.

    Les extremites et la forme du trace sont resolues une fois par cable, hors
    de la boucle des noeuds : un cable en heberge potentiellement plusieurs.

    Un cable sans extremite — geometrie fermee ou absente — n'est pas jugeable :
    aucune position ne peut y valoir coupure, et signaler tous ses noeuds
    reviendrait a mesurer la geometrie du cable, ce que font E-6110 et E-6111.
    """
    geometrie = feature.get("geometry")
    extremites = extraire_extremites(geometrie)
    if not extremites:
        return []
    trace = forme_shapely(geometrie)
    id_cable = obtenir_id_feature(feature)
    return [
        {
            "type_anomalie": TYPE_CABLE_NON_COUPE,
            "id_cable": id_cable,
            "id_noeud": noeud.identifiant,
            "couche_noeud": noeud.couche,
            "geometrie": {"type": "Point", "coordinates": [noeud.point[0], noeud.point[1]]},
        }
        for noeud in noeuds
        if classifier_noeud(noeud, extremites, trace)
    ]


def parcourir_cables(
    features: list[dict[str, Any]],
    index_noeuds: Mapping[str, list[NoeudTraverse]],
) -> Iterator[tuple[dict[str, Any], list[NoeudTraverse]]]:
    """Parcourt les cables controles accompagnes des noeuds qui les referencent.

    Un cable que ne reference aucun noeud est ecarte : sans noeud, aucune
    coupure ne peut manquer.
    """
    for feature in features:
        identifiant = obtenir_id_feature(feature)
        noeuds = index_noeuds.get(identifiant) if identifiant is not None else None
        if noeuds:
            yield feature, noeuds


def compter_cables_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les cables distincts portant au moins une anomalie."""
    return len({anomalie["id_cable"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des coupures manquantes.

    `couche_noeud` nomme le type du noeud traverse : c'est l'ouvrage au droit
    duquel la coupure est a realiser, et l'information serait sinon perdue, tous
    les types partageant le meme fichier d'ecarts.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_CABLE_ELECTRIQUE,
                "id_cable": a["id_cable"],
                "id_noeud": a["id_noeud"],
                "couche_noeud": a["couche_noeud"],
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
    """Execute le controle E-6102 et ecrit ses ecarts.

    Indexe les noeuds par cable, parcourt les cables electriques en cours de
    mise en service et ecrit le fichier d'ecarts GeoJSON. Les couches de noeud
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

    index_noeuds, couches_absentes = indexer_noeuds_par_cable(repertoire_resolu)
    features, crs, cable_absent = charger_features(repertoire_resolu, FICHIER_CABLE_ELECTRIQUE)
    cables = filtrer_cables_a_controler(features)

    anomalies: list[dict[str, Any]] = []
    for feature, noeuds in parcourir_cables(cables, index_noeuds):
        anomalies.extend(detecter_anomalies_cable(feature, noeuds))

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_cables_controles": len(cables),
        "nombre_cables_non_conformes": compter_cables_non_conformes(anomalies),
        "couches_noeuds_absentes": couches_absentes,
        "fichier_cable_absent": cable_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-6102."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6102 : un câble ne doit pas traverser un nœud sans y être coupé."
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
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
