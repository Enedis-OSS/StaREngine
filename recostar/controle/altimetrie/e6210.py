"""
Controle E-6210 : point de leve sur les sommets des geometries supplementaires
de batiments techniques rattaches a un poste electrique.

Pour chaque geometrie supplementaire liee a un batiment technique lui-meme
rattache a un poste electrique eligible, verifie qu'au moins un point de leve
(RPD_PointLeveOuvrageReseau_Reco) est en superposition planimetrique (2D) avec
l'un des SOMMETS de cette geometrie supplementaire.

Difference avec E-9201 :
- E-9201 verifie la superposition sur l'ENSEMBLE de la geometrie supplementaire
  (segments et surface) via un STRtree Shapely et le predicat 'intersects'.
- E-6210 verifie la superposition UNIQUEMENT sur les SOMMETS de la geometrie
  supplementaire, par test d'appartenance a un ensemble de coordonnees.

Chaine de references controlee :
  Poste (Statut == UnderCommissionning)
    --conteneur_href-->            BatimentTechnique.id
  BatimentTechnique
    --geometriesupplementaire_href--> GeometrieSupplementaire.id

Seuls les postes electriques dont l'attribut Statut vaut « UnderCommissionning »
sont pris en compte, pour les versions 1.0 et 1.1. La version RecoStaR est
detectee automatiquement depuis les features de RPD_PointLeveOuvrageReseau_Reco
(presence du champ TypeLeve -> v1.0 ; absence -> v1.1), identiquement au
mecanisme commun `fonctions_communes.version_recostar`. Elle peut etre imposee
via l'option --version.

Fichiers sources :
  - RPD_PosteElectrique_Reco.geojson (filtrage par Statut + lien vers batiment)
  - RPD_BatimentTechnique_Reco.geojson (lien vers geometrie supplementaire)
  - RPD_GeometrieSupplementaire_Reco.geojson (polygones a controler)
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve)

Usage CLI :
    python -m recostar.controle.altimetrie.e6210 --repertoire <chemin> [--sortie <chemin>]
                                                 [--version {auto,1.0,1.1}]

Sortie : ecarts_e6210_point_leve_sommets_geom_supp.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_GEOMSUPP_HREF,
    CHAMP_STATUT,
    FICHIER_BATIMENT,
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
    FICHIER_POSTE,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)

# Mecanisme de detection de version partage avec e0204
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6210_point_leve_sommets_geom_supp.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E-6210"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_sommet_absent": (
        "Un sommet de la géométrie supplémentaire de bâtiment technique n'est superposé à aucun point levé."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source=FICHIER_GEOM_SUPP,
)


# Champ du batiment technique referencant sa geometrie supplementaire

# Champ et valeur de filtrage des postes eligibles (v1.0 et v1.1)
VALEUR_STATUT_ELIGIBLE: str = STATUT_MISE_EN_SERVICE

# Precision de snapping des coordonnees pour le test d'appartenance (decimales).
# Les points de leve et les sommets proviennent de la meme source et coincident
# a la precision des donnees (2 decimales = centimetre). Le snapping neutralise
# le bruit de representation flottante sans introduire de tolerance metier.
PRECISION_COORD: int = 2


# ---------------------------------------------------------------------------
# Extraction des references Poste -> Batiment -> Geometrie supplementaire
# ---------------------------------------------------------------------------


def _hrefs_depuis_champ(valeur: Any) -> list[str]:
    """Decompose un champ href en identifiants (support des listes séparées par des virgules).

    Retourne une liste vide si la valeur n'est pas une chaine exploitable.
    """
    if not isinstance(valeur, str):
        return []
    return [href for href in valeur.split(",") if href]


def extraire_ids_batiments_de_postes_eligibles(
    features_postes: list[dict[str, Any]],
) -> frozenset[str]:
    """Extrait les identifiants de batiments techniques rattaches a un poste eligible.

    Un poste est eligible si son champ Statut vaut VALEUR_STATUT_ELIGIBLE
    (regle commune aux versions 1.0 et 1.1). Le lien vers le batiment est porte
    par conteneur_href. Retourne un frozenset pour le lookup O(1) en aval.
    """
    ids_batiments: set[str] = set()
    for feat in features_postes:
        props = feat.get("properties") or {}
        if props.get(CHAMP_STATUT) != VALEUR_STATUT_ELIGIBLE:
            continue
        ids_batiments.update(_hrefs_depuis_champ(props.get(CHAMP_CONTENEUR_HREF)))
    return frozenset(ids_batiments)


def extraire_hrefs_geomsupp_de_batiments(
    features_batiments: list[dict[str, Any]],
    ids_batiments_eligibles: frozenset[str],
) -> frozenset[str]:
    """Extrait les geometries supplementaires liees aux batiments eligibles.

    Seuls les batiments dont l'id figure dans ids_batiments_eligibles sont
    retenus. Retourne un frozenset des identifiants de geometries
    supplementaires pour le lookup O(1) en aval.
    """
    hrefs: set[str] = set()
    for feat in features_batiments:
        props = feat.get("properties") or {}
        id_batiment = props.get("id")
        if not isinstance(id_batiment, str) or id_batiment not in ids_batiments_eligibles:
            continue
        hrefs.update(_hrefs_depuis_champ(props.get(CHAMP_GEOMSUPP_HREF)))
    return frozenset(hrefs)


# ---------------------------------------------------------------------------
# Chargement des coordonnees des points de leve (ensemble d'appartenance)
# ---------------------------------------------------------------------------


def _snapper(x: float, y: float) -> tuple[float, float]:
    """Snappe une coordonnee 2D a la precision PRECISION_COORD.

    Assure la comparaison exacte entre points de leve et sommets en
    neutralisant le bruit de representation flottante.
    """
    return (round(x, PRECISION_COORD), round(y, PRECISION_COORD))


def charger_coordonnees_points_leve(
    features: list[dict[str, Any]],
) -> frozenset[tuple[float, float]]:
    """Construit l'ensemble des coordonnees planimetriques des points de leve.

    Seules les geometries de type Point sont traitees ; la composante Z est
    ignoree (comparaison planimetrique). Retourne un frozenset pour un test
    d'appartenance O(1) lors de la detection.
    """
    coordonnees: set[tuple[float, float]] = set()
    for feat in features:
        geom = feat.get("geometry")
        if geom is None or geom.get("type") != "Point":
            continue
        position = geom.get("coordinates")
        if not isinstance(position, list) or len(position) < 2:
            continue
        coordonnees.add(_snapper(position[0], position[1]))
    return frozenset(coordonnees)


# ---------------------------------------------------------------------------
# Extraction des sommets d'une geometrie supplementaire
# ---------------------------------------------------------------------------


def _est_position(element: Any) -> bool:
    """Indique si un element des coordinates GeoJSON est une position [x, y, ...]."""
    return isinstance(element, list) and len(element) >= 2 and isinstance(element[0], (int, float))


def _collecter_sommets(coords: Any, accumulateur: set[tuple[float, float]]) -> None:
    """Parcourt recursivement les coordinates imbriquees et accumule les sommets 2D.

    Gere indifferemment Polygon et MultiPolygon (listes imbriquees a
    profondeur variable). Le snapping deduplique naturellement le sommet de
    fermeture des anneaux (premier == dernier).
    """
    if not isinstance(coords, list) or not coords:
        return
    if _est_position(coords):
        accumulateur.add(_snapper(coords[0], coords[1]))
        return
    for sous_coords in coords:
        _collecter_sommets(sous_coords, accumulateur)


def extraire_sommets_2d(geom_dict: dict[str, Any]) -> set[tuple[float, float]]:
    """Extrait l'ensemble des sommets planimetriques (snappes) d'une geometrie.

    Retourne un set de coordonnees 2D. La composante Z eventuelle est ignoree.
    """
    sommets: set[tuple[float, float]] = set()
    _collecter_sommets(geom_dict.get("coordinates"), sommets)
    return sommets


# ---------------------------------------------------------------------------
# Detection spatiale sur les sommets
# ---------------------------------------------------------------------------


def detecter_geomsupp_sans_point_leve_sur_sommets(
    features_geomsupp: list[dict[str, Any]],
    ids_lies: frozenset[str],
    coords_points_leve: frozenset[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Detecte les geometries supplementaires sans point de leve sur leurs sommets.

    Seules les geometries dont l'id figure dans ids_lies sont verifiees. Une
    anomalie E-6210 est produite lorsque aucun des sommets de la geometrie ne
    coincide avec un point de leve (test d'appartenance a l'ensemble des
    coordonnees de leve, via set.isdisjoint).

    La detection est planimetrique : sommets et points de leve sont compares en
    2D. Les geometries sans sommet exploitable sont ignorees (donnee malformee).

    Retourne une liste d'anomalies {id_geomsupp, geometrie}.
    """
    anomalies: list[dict[str, Any]] = []

    for feat in features_geomsupp:
        props = feat.get("properties") or {}
        id_gs = props.get("id")
        if not isinstance(id_gs, str) or id_gs not in ids_lies:
            continue
        geom_dict = feat.get("geometry")
        if geom_dict is None:
            continue
        sommets = extraire_sommets_2d(geom_dict)
        if not sommets:
            continue
        if sommets.isdisjoint(coords_points_leve):
            anomalies.append({"id_geomsupp": id_gs, "geometrie": geom_dict})

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des geometries supplementaires en anomalie.

    Chaque feature conserve la geometrie du polygone de la geometrie
    supplementaire pour permettre la localisation dans QGIS.
    Le champ crs est propage depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": a["id_geomsupp"],
                "type_anomalie": "point_leve_sommet_absent",
                "version": version,
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
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E-6210 en mode CLI.

    Charge les quatre fichiers sources, resout la version RecoStaR depuis les
    features de RPD_PointLeveOuvrageReseau_Reco (mecanisme commun),
    remonte la chaine Poste -> Batiment -> Geometrie supplementaire, verifie la
    presence d'un point de leve sur les sommets, puis ecrit le fichier d'ecarts.
    """
    repertoire_resolu = str(Path(repertoire).resolve())

    collection_poste = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POSTE))
    if collection_poste is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_POSTE, repertoire_resolu))

    collection_batiment = lire_geojson(os.path.join(repertoire_resolu, FICHIER_BATIMENT))
    if collection_batiment is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_BATIMENT, repertoire_resolu))

    collection_geomsupp = lire_geojson(os.path.join(repertoire_resolu, FICHIER_GEOM_SUPP))
    if collection_geomsupp is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_GEOM_SUPP, repertoire_resolu))

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_POINT_LEVE, repertoire_resolu))

    features_postes = collection_poste.get("features", [])
    features_batiments = collection_batiment.get("features", [])
    features_geomsupp = collection_geomsupp.get("features", [])
    features_points = collection_points.get("features", [])
    crs = collection_poste.get("crs")

    # Detection de version commune (TypeLeve dans PointLeve)
    version_effective = resoudre_version(version, features_points)

    ids_batiments = extraire_ids_batiments_de_postes_eligibles(features_postes)
    ids_lies = extraire_hrefs_geomsupp_de_batiments(features_batiments, ids_batiments)
    coords_points_leve = charger_coordonnees_points_leve(features_points)
    anomalies = detecter_geomsupp_sans_point_leve_sur_sommets(features_geomsupp, ids_lies, coords_points_leve)
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_geomsupp_controlees": len(ids_lies),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-6210."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-6210 : detection des geometries supplementaires de "
            "batiments techniques (rattaches a un poste) sans point de leve sur "
            "leurs sommets."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=(f"Repertoire contenant {FICHIER_POSTE}, {FICHIER_BATIMENT}, {FICHIER_GEOM_SUPP} et {FICHIER_POINT_LEVE}"),
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=choix_version,
        default=JETON_AUTO,
        help=(
            "Version RecoStaR a controler. 'auto' (defaut) la deduit des "
            "proprietes GeoJSON (TypeLeve dans PointLeve) ; sinon imposer "
            "'1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
