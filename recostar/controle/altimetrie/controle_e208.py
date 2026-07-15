"""
Controle E208 : rattachement des sommets de cables aux points de leve.

Verifie que chaque sommet des cables controles est en superposition exacte avec
un point de leve (RPD_PointLeveOuvrageReseau_Reco) ET que ses coordonnees X, Y et
Z sont strictement egales a celles de ce point de leve.

Deux causes d'anomalie, evaluees par sommet :
- « point_leve_absent » : aucun point de leve n'a exactement les memes X et Y que
  le sommet (pas de superposition).
- « coordonnees_differentes » : un point de leve superpose existe (memes X, Y)
  mais aucun ne partage exactement le meme Z (altitude divergente).

La comparaison est stricte (aucune tolerance) : un index
dict[(x, y) -> set(z)] des points de leve permet un test d'appartenance O(1)
par sommet.

Exception d'extremite en contact avec une geometrie supplementaire :
  Un sommet d'extremite du cable dont la position est en contact avec une entite
  RPD_GeometrieSupplementaire_Reco est exempte de l'obligation de point de leve :
  l'ouvrage y est deja leve par sa geometrie supplementaire. L'exception ne leve
  que la cause « point_leve_absent » et ne s'applique qu'aux extremites ; les
  sommets intermediaires restent soumis a la regle, et un sommet d'extremite
  superpose a un point de leve de Z divergent reste signale
  (« coordonnees_differentes »).

  Extremites : ce sont les extremites *topologiques* (extraire_extremites du
  module commun utils_geometrie), et non le premier et le dernier sommet de la
  liste concatenee. Les parties d'un MultiLineString RecoStaR n'etant ni
  ordonnees ni orientees, la lecture litterale designerait un raccord interne et
  manquerait les vrais bouts : elle diverge sur 22 des 30 cables multi-parties
  des jeux de reference.

  Contact : predicat 'intersects' planimetrique (interieur ou bord), evalue via
  un index spatial STRtree — meme mecanisme geometrique que les controles E205 et
  E209. L'absence du fichier des geometries supplementaires n'est pas bloquante :
  aucune exemption n'est alors appliquee.

Gestion des versions RecoStaR (perimetre identique a E202) :
- v1.0 : RPD_CableElectrique_Reco et RPD_CableTerre_Reco.
- v1.1 : v1.0 + RPD_CableTelecommunication_Reco.
Dans toutes les versions, seules les entites dont le champ Statut vaut
« UnderCommissionning » sont controlees. La version est detectee depuis les
features de RPD_PointLeveOuvrageReseau_Reco (champ TypeLeve → v1.0 ; absence →
v1.1), identiquement a E204/E205, et peut etre imposee via l'option --version.

Les cables dont l'identifiant apparait dans un cheminement aerien
(RPD_Aerien_Reco.cables_href) sont exclus du controle, comme dans E202.

Fichiers sources :
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve + detection version)
  - RPD_CableElectrique_Reco.geojson, RPD_CableTerre_Reco.geojson
    (+ RPD_CableTelecommunication_Reco.geojson en v1.1)
  - RPD_Aerien_Reco.geojson (cables exclus ; absence non bloquante)
  - RPD_GeometrieSupplementaire_Reco.geojson (exception d'extremite ;
    absence non bloquante)

Usage CLI :
    python controle_e208.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_point_leve_sommets_cables.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# Perimetre, filtrage par statut et exclusion aerienne, reutilises d'E202
from controle_e202 import (
    charger_ids_cables_aeriens,
    filtrer_cables_a_controler,
    resoudre_fichiers_cables,
)

# Mecanisme de detection de version partage avec E204
from controle_e204 import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)

# Noms de fichiers reutilises d'E205
from controle_e205 import FICHIER_GEOM_SUPP, FICHIER_POINT_LEVE
from shapely import STRtree, force_2d
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Extremites topologiques, partagees avec les controles de cable (E506, E507)
from utils_geometrie import extraire_extremites

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_point_leve_sommets_cables.geojson"

# Niveau de priorite : bloquant
PRIORITE_ANOMALIE: str = "bloquant"

# Libelles des deux causes d'anomalie
TYPE_ANO_ABSENT: str = "point_leve_absent"
TYPE_ANO_COORD: str = "coordonnees_differentes"


# ---------------------------------------------------------------------------
# Indexation des points de leve
# ---------------------------------------------------------------------------


def indexer_points_leve_par_xy(
    features_points: list[dict[str, Any]],
) -> dict[tuple[float, float], set[float]]:
    """Indexe les points de leve par coordonnees planimetriques exactes.

    Retourne un dict {(x, y) -> ensemble des z observes a cette position}.
    Seules les geometries Point 3D sont indexees. L'ensemble de z permet de
    verifier l'egalite altimetrique stricte en O(1) et gere le cas de plusieurs
    points de leve superposes en XY avec des Z distincts.
    """
    index: dict[tuple[float, float], set[float]] = defaultdict(set)
    for feat in features_points:
        geom = feat.get("geometry")
        if geom is None or geom.get("type") != "Point":
            continue
        coord = geom.get("coordinates")
        if not isinstance(coord, list) or len(coord) < 3:
            continue
        index[(coord[0], coord[1])].add(coord[2])
    return index


# ---------------------------------------------------------------------------
# Exception : extremites en contact avec une geometrie supplementaire
# ---------------------------------------------------------------------------


def charger_geometries_supplementaires(repertoire: str) -> list[BaseGeometry]:
    """Charge les geometries supplementaires en 2D pour le test de contact.

    Meme mecanisme qu'E205 : les Z sont supprimes (force_2d) pour un test
    planimetrique, et les geometries malformees sont ignorees sans lever
    d'exception. L'absence du fichier n'est pas bloquante : aucune exemption
    n'est alors appliquee.
    """
    collection = lire_geojson(os.path.join(repertoire, FICHIER_GEOM_SUPP))
    if collection is None:
        return []
    geometries: list[BaseGeometry] = []
    for feat in collection.get("features", []):
        geom_dict = feat.get("geometry")
        if geom_dict is None:
            continue
        try:
            geometries.append(force_2d(shape(geom_dict)))
        except Exception:  # nosec B112
            continue
    return geometries


class IndexGeomSupp:
    """Index spatial des geometries supplementaires pour le test de contact.

    Encapsule l'arbre STRtree (meme mecanisme qu'E205 / E209) et le cas ou
    aucune geometrie n'est disponible : `en_contact` retourne alors False, sans
    exemption. Un index vide est ainsi utilisable sans condition par l'appelant.
    """

    __slots__ = ("_arbre",)

    def __init__(self, geometries: list[BaseGeometry]) -> None:
        # STRtree n'accepte pas une sequence vide de facon exploitable : on
        # conserve None et le test de contact repond False.
        self._arbre = STRtree(geometries) if geometries else None

    def en_contact(self, x: float, y: float) -> bool:
        """Indique si le point (x, y) touche une geometrie supplementaire.

        Le predicat 'intersects' couvre l'interieur et le bord : un sommet pose
        sur le contour d'une geometrie est en contact.
        """
        if self._arbre is None:
            return False
        return len(self._arbre.query(Point(x, y), predicate="intersects")) > 0


# ---------------------------------------------------------------------------
# Extraction des sommets d'un cable
# ---------------------------------------------------------------------------


def _extraire_sommets_cable(geometrie: dict[str, Any]) -> list[Sequence[float]]:
    """Retourne la liste ordonnee des sommets d'un cable.

    LineString : ses sommets directs. MultiLineString : les sommets de tous ses
    troncons concatenes (sans recollage : chaque sommet est controle
    individuellement). Tout autre type de geometrie donne une liste vide.
    """
    type_geom = geometrie.get("type")
    coords = geometrie.get("coordinates")
    if type_geom == "LineString":
        return coords if isinstance(coords, list) else []
    if type_geom == "MultiLineString" and isinstance(coords, list):
        sommets: list[Sequence[float]] = []
        for troncon in coords:
            if isinstance(troncon, list):
                sommets.extend(troncon)
        return sommets
    return []


# ---------------------------------------------------------------------------
# Detection des sommets incoherents
# ---------------------------------------------------------------------------


def _classifier_sommet(
    sommet: Sequence[float],
    index_points: dict[tuple[float, float], set[float]],
) -> str | None:
    """Classe un sommet : None si conforme, sinon la cause d'anomalie.

    Un sommet est conforme s'il existe un point de leve de memes X, Y et Z. Si
    aucun point ne partage ses X et Y → point_leve_absent ; si un tel point
    existe mais sans Z egal → coordonnees_differentes.
    """
    if len(sommet) < 2:
        return None  # sommet malforme : hors perimetre (conformite 3D = E200)
    z_candidats = index_points.get((sommet[0], sommet[1]))
    if z_candidats is None:
        return TYPE_ANO_ABSENT
    if len(sommet) < 3 or sommet[2] not in z_candidats:
        return TYPE_ANO_COORD
    return None


def _est_exempte(
    sommet: Sequence[float],
    type_ano: str,
    extremites: frozenset[tuple[float, float]],
    index_geomsupp: IndexGeomSupp,
) -> bool:
    """Indique si un sommet en anomalie beneficie de l'exception d'extremite.

    Trois conditions cumulatives :
      - la cause est l'absence de point de leve (un Z divergent reste signale :
        l'ouvrage est leve, mais mal) ;
      - le sommet est une extremite topologique du cable ;
      - sa position est en contact avec une geometrie supplementaire.
    """
    if type_ano != TYPE_ANO_ABSENT:
        return False
    if (sommet[0], sommet[1]) not in extremites:
        return False
    return index_geomsupp.en_contact(sommet[0], sommet[1])


def _analyser_cable(
    cable: dict[str, Any],
    index_points: dict[tuple[float, float], set[float]],
    index_geomsupp: IndexGeomSupp,
) -> list[dict[str, Any]]:
    """Detecte les sommets non conformes d'un cable, exception d'extremite appliquee."""
    geometrie = cable.get("geometry") or {}
    sommets = _extraire_sommets_cable(geometrie)
    if not sommets:
        return []

    identifiant = obtenir_id_feature(cable)
    # Extremites calculees une fois par cable : le test d'appartenance des
    # sommets est ensuite en O(1).
    extremites = frozenset(extraire_extremites(geometrie))
    classifier = _classifier_sommet  # alias local : evite le lookup global en boucle
    exempte = _est_exempte

    anomalies: list[dict[str, Any]] = []
    for indice, sommet in enumerate(sommets):
        type_ano = classifier(sommet, index_points)
        if type_ano is None or exempte(sommet, type_ano, extremites, index_geomsupp):
            continue
        anomalies.append(
            {
                "id_cable": identifiant,
                "indice_sommet": indice,
                "coordonnees": list(sommet),
                "type_anomalie": type_ano,
            }
        )
    return anomalies


def detecter_sommets_incoherents(
    cables: list[dict[str, Any]],
    index_points: dict[tuple[float, float], set[float]],
    ids_cables_exclus: set[str],
    index_geomsupp: IndexGeomSupp | None = None,
) -> list[dict[str, Any]]:
    """Detecte les sommets de cables non rattaches a un point de leve conforme.

    Pour chaque sommet de chaque cable, verifie la superposition exacte et
    l'egalite stricte des coordonnees avec un point de leve. Les cables dont
    l'identifiant est reference par un cheminement aerien (ids_cables_exclus)
    sont ignores, comme dans E202.

    index_geomsupp porte l'exception d'extremite (cf. _est_exempte) ; omis, aucune
    exemption n'est appliquee et le comportement historique est conserve.

    Retourne une liste d'anomalies
    {id_cable, indice_sommet, coordonnees, type_anomalie}.
    """
    index = index_geomsupp if index_geomsupp is not None else IndexGeomSupp([])
    anomalies: list[dict[str, Any]] = []
    analyser = _analyser_cable  # alias local

    for cable in cables:
        if obtenir_id_feature(cable) in ids_cables_exclus:
            continue
        anomalies.extend(analyser(cable, index_points, index))

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des sommets en anomalie.

    Chaque feature est positionnee sur le sommet en anomalie (coordonnees
    conservees) pour permettre sa localisation dans QGIS. Le champ crs est
    propage depuis les fichiers sources.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_cable": a["id_cable"],
                "couche": a.get("couche"),
                "indice_sommet": a["indice_sommet"],
                "type_anomalie": a["type_anomalie"],
                "priorite": PRIORITE_ANOMALIE,
                "version": version,
            },
            "geometry": {
                "type": "Point",
                "coordinates": a["coordonnees"],
            },
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# ---------------------------------------------------------------------------
# Orchestration par couche
# ---------------------------------------------------------------------------


def controler_couches_cables(
    repertoire: str,
    fichiers_cables: Sequence[str],
    index_points: dict[tuple[float, float], set[float]],
    ids_cables_exclus: set[str],
    index_geomsupp: IndexGeomSupp | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    """Execute le controle sur chaque couche de cables presente dans le repertoire.

    Seules les entites au statut « UnderCommissionning » sont controlees ; les
    cables references par un cheminement aerien (ids_cables_exclus) sont exclus,
    comme dans E202. Les couches absentes sont ignorees silencieusement (cas
    nominal de la telecommunication en v1.0 ou sur les jeux ne la contenant pas).
    La couche d'origine est annotee sur chaque anomalie. Le CRS est propage
    depuis la premiere couche presente qui en porte un.

    Retourne (anomalies, crs, couches_traitees).
    """
    anomalies: list[dict[str, Any]] = []
    crs: dict[str, Any] | None = None
    couches_traitees: list[str] = []

    for fichier in fichiers_cables:
        collection = lire_geojson(os.path.join(repertoire, fichier))
        if collection is None:
            continue

        nom_couche = Path(fichier).stem
        couches_traitees.append(nom_couche)
        if crs is None:
            crs = collection.get("crs")

        cables = filtrer_cables_a_controler(collection.get("features", []))
        anomalies_couche = detecter_sommets_incoherents(cables, index_points, ids_cables_exclus, index_geomsupp)
        for anomalie in anomalies_couche:
            anomalie["couche"] = nom_couche
        anomalies.extend(anomalies_couche)

    return anomalies, crs, couches_traitees


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E208 en mode CLI.

    Charge les points de leve, resout la version RecoStaR (meme mecanisme
    qu'E204/E205), indexe les points par XY, determine les couches de cables a
    controler puis verifie chaque sommet. Ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_POINT_LEVE} introuvable dans {repertoire_resolu}",
        }

    features_points = collection_points.get("features", [])
    version_effective = resoudre_version(version, features_points)
    index_points = indexer_points_leve_par_xy(features_points)

    fichiers_cables = resoudre_fichiers_cables(version_effective)
    ids_exclus = charger_ids_cables_aeriens(repertoire_resolu)
    geometries_supp = charger_geometries_supplementaires(repertoire_resolu)
    anomalies, crs_cables, couches_traitees = controler_couches_cables(
        repertoire_resolu, fichiers_cables, index_points, ids_exclus, IndexGeomSupp(geometries_supp)
    )
    if not couches_traitees:
        return {
            "succes": False,
            "erreur": f"Aucune couche de cables trouvee dans {repertoire_resolu}",
        }

    crs = crs_cables if crs_cables is not None else collection_points.get("crs")
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    nb_absent = sum(1 for a in anomalies if a["type_anomalie"] == TYPE_ANO_ABSENT)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "couches_controlees": couches_traitees,
        "cables_exclus": len(ids_exclus),
        "geometries_supplementaires_indexees": len(geometries_supp),
        "nombre_anomalies": len(anomalies),
        "nombre_sommets_sans_point_leve": nb_absent,
        "nombre_sommets_coordonnees_differentes": len(anomalies) - nb_absent,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle E208."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E208 : rattachement des sommets de cables aux points de "
            "leve (superposition exacte et egalite stricte X, Y, Z)."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant les couches de cables et {FICHIER_POINT_LEVE}",
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
