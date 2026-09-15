"""
Moteur de detection : rattachement des sommets de cables aux points de leve.

Verifie que chaque sommet des cables controles est superpose a un point de leve
(RPD_PointLeveOuvrageReseau_Reco) ET que ses coordonnees X, Y et Z concordent
avec celles de ce point de leve.

Deux causes d'anomalie, evaluees par sommet :
- « point_leve_absent » : aucun point de leve n'est a portee du sommet en
  planimetrie (pas de superposition).
- « coordonnees_differentes » : un point de leve superpose existe (X, Y a
  portee) mais aucun n'a une altitude a portee (altitude divergente).

Pourquoi une tolerance, et pourquoi celle-ci
--------------------------------------------
La comparaison admettait l'egalite exacte. Elle echouait alors sur des sommets
pourtant leves, le producteur n'ecrivant pas la meme valeur des deux cotes :
un sommet a 470597.929 et son point de leve a 470597.930 decrivent la meme
mesure, arrondie differemment. TOLERANCE_POINT_LEVE vaut 2 mm — au-dela de
l'ecart d'ecriture, en deca de tout defaut de leve reel, qui se compte en
centimetres.

La recherche passe par un index spatial STRtree (`IndexPointsLeve`), l'egalite
exacte d'un dictionnaire ne sachant pas rendre les points voisins.

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

  Contact : predicat 'dwithin' planimetrique a TOLERANCE_SUPERPOSITION (interieur
  ou bord), evalue via un index spatial STRtree — meme mecanisme geometrique et
  meme tolerance que E-9201 et E-6211. La tolerance ne concerne que
  cette exemption ; la regle principale ci-dessus reste une egalite stricte.
  L'absence du fichier des geometries supplementaires n'est pas bloquante :
  aucune exemption n'est alors appliquee.

Gestion des versions RecoStaR (perimetre identique a E-5201) :
- v1.0 : RPD_CableElectrique_Reco et RPD_CableTerre_Reco.
- v1.1 : v1.0 + RPD_CableTelecommunication_Reco.
Dans toutes les versions, seules les entites dont le champ Statut vaut
« UnderCommissionning » sont controlees. La version est detectee depuis les
features de RPD_PointLeveOuvrageReseau_Reco (champ TypeLeve → v1.0 ; absence →
v1.1) par le mecanisme commun `fonctions_communes.version_recostar`, et peut etre
imposee via l'option --version.

Les cables dont l'identifiant apparait dans un cheminement aerien
(RPD_Aerien_Reco.cables_href) sont exclus du controle, comme dans E-5201.

Fichiers sources :
  - RPD_PointLeveOuvrageReseau_Reco.geojson (points de leve + detection version)
  - RPD_CableElectrique_Reco.geojson, RPD_CableTerre_Reco.geojson
    (+ RPD_CableTelecommunication_Reco.geojson en v1.1)
  - RPD_Aerien_Reco.geojson (cables exclus ; absence non bloquante)
  - RPD_GeometrieSupplementaire_Reco.geojson (exception d'extremite ;
    absence non bloquante)

"""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from shapely import STRtree, force_2d
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Extremites topologiques, partagees avec les controles de cable, et tolerance
# planimetrique de contact, partagee avec E-9201 et E-6211
from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION, extraire_extremites

# Couches sources, communes avec E-9201
from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_GEOM_SUPP,
    FICHIER_POINT_LEVE,
)

# Perimetre, filtrage par statut et exclusion aerienne, identiques a E-5201
from recostar.controle.fonctions_communes.references_cables import (
    charger_ids_cables_aeriens,
    filtrer_cables_a_controler,
    resoudre_fichiers_cables,
)
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)

# Detection de version, commune a tous les controles GeoJSON
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    resoudre_version,
)

# Tolerance de rattachement d'un sommet a son point de leve, sur les trois
# coordonnees. Elle absorbe les ecarts d'ecriture decimale entre deux
# expressions d'une meme mesure — un sommet a 470597.929 et son point de leve
# a 470597.930 — sans couvrir un defaut de leve, qui se compte en centimetres.
# Distincte de TOLERANCE_SUPERPOSITION, qui regit le contact avec les emprises.
TOLERANCE_POINT_LEVE: float = 0.002

# Libelles des deux causes d'anomalie
TYPE_ANO_ABSENT: str = "point_leve_absent"
TYPE_ANO_COORD: str = "coordonnees_differentes"


# ---------------------------------------------------------------------------
# Indexation des points de leve
# ---------------------------------------------------------------------------


class IndexPointsLeve:
    """Index spatial des points de leve, interroge a TOLERANCE_POINT_LEVE.

    Encapsule l'arbre STRtree et les altitudes observees a chaque position, sur
    le modele d'`IndexGeomSupp`. Un index vide repond sans candidat, ce qui rend
    l'appelant inconditionnel.

    Plusieurs points de leve peuvent tomber dans la tolerance d'un meme sommet :
    `z_candidats` les rend tous, le sommet etant conforme des qu'une de ces
    altitudes convient.
    """

    __slots__ = ("_arbre", "_altitudes")

    def __init__(self, positions: list[tuple[float, float, float]]) -> None:
        # STRtree n'accepte pas une sequence vide de facon exploitable : on
        # conserve None et la recherche ne rend aucun candidat.
        self._arbre = STRtree([Point(x, y) for x, y, _ in positions]) if positions else None
        self._altitudes = [z for _, _, z in positions]

    def z_candidats(self, x: float, y: float) -> set[float]:
        """Altitudes des points de leve situes a portee du point (x, y)."""
        if self._arbre is None:
            return set()
        indices = self._arbre.query(Point(x, y), predicate="dwithin", distance=TOLERANCE_POINT_LEVE)
        return {self._altitudes[indice] for indice in indices}


def indexer_points_leve(features_points: list[dict[str, Any]]) -> IndexPointsLeve:
    """Construit l'index spatial des points de leve.

    Seules les geometries Point 3D sont retenues : un point sans altitude ne
    peut servir de reference a la comparaison altimetrique.
    """
    positions: list[tuple[float, float, float]] = []
    for feat in features_points:
        geom = feat.get("geometry")
        if geom is None or geom.get("type") != "Point":
            continue
        coord = geom.get("coordinates")
        if not isinstance(coord, list) or len(coord) < 3:
            continue
        positions.append((coord[0], coord[1], coord[2]))
    return IndexPointsLeve(positions)


# ---------------------------------------------------------------------------
# Exception : extremites en contact avec une geometrie supplementaire
# ---------------------------------------------------------------------------


def charger_geometries_supplementaires(repertoire: str) -> list[BaseGeometry]:
    """Charge les geometries supplementaires en 2D pour le test de contact.

    Meme mecanisme qu'E-9201 : les Z sont supprimes (force_2d) pour un test
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

    Encapsule l'arbre STRtree (meme mecanisme qu'E-9201 / E-6211) et le cas ou
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

        Le predicat 'dwithin' a TOLERANCE_SUPERPOSITION couvre l'interieur et le
        bord : un sommet pose sur le contour d'une geometrie est en contact.
        Sans cette tolerance, le contact avec le contour — de mesure nulle — est
        rompu par l'arrondi millimetrique de la posList GML, et l'exemption
        d'extremite serait manquee alors que l'ouvrage est bien leve.

        La tolerance ne porte que sur cette exemption : la regle principale
        du moteur reste l'egalite stricte X/Y/Z, sans tolerance (cf. _classifier_sommet).
        """
        if self._arbre is None:
            return False
        return len(self._arbre.query(Point(x, y), predicate="dwithin", distance=TOLERANCE_SUPERPOSITION)) > 0


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
    index_points: IndexPointsLeve,
) -> str | None:
    """Classe un sommet : None si conforme, sinon la cause d'anomalie.

    Un sommet est conforme s'il existe un point de leve a portee en X, Y et Z.
    Si aucun point n'est a portee en planimetrie → point_leve_absent ; si un tel
    point existe mais qu'aucun n'a une altitude a portee → coordonnees_differentes.

    La comparaison admet TOLERANCE_POINT_LEVE sur les trois coordonnees : le
    sommet et son point de leve decrivent la meme mesure, et un ecart d'ecriture
    decimale entre les deux ne vaut pas defaut de rattachement.
    """
    if len(sommet) < 2:
        return None  # sommet malforme : hors perimetre (conformite 3D = E-5107)
    z_candidats = index_points.z_candidats(sommet[0], sommet[1])
    if not z_candidats:
        return TYPE_ANO_ABSENT
    if len(sommet) < 3 or not any(abs(sommet[2] - z) <= TOLERANCE_POINT_LEVE for z in z_candidats):
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
    index_points: IndexPointsLeve,
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
    index_points: IndexPointsLeve,
    ids_cables_exclus: set[str],
    index_geomsupp: IndexGeomSupp | None = None,
) -> list[dict[str, Any]]:
    """Detecte les sommets de cables non rattaches a un point de leve conforme.

    Pour chaque sommet de chaque cable, verifie la superposition exacte et
    l'egalite stricte des coordonnees avec un point de leve. Les cables dont
    l'identifiant est reference par un cheminement aerien (ids_cables_exclus)
    sont ignores, comme dans E-5201.

    index_geomsupp porte l'exception d'extremite (cf. _est_exempte) ; omis, aucune
    exemption n'est appliquee : tout sommet est alors juge sur la seule regle
    principale.

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
# Constat de jeu : altimetrie des points de leve rattaches aux cables
# ---------------------------------------------------------------------------

# Altitude consideree comme non renseignee.
ALTITUDE_NULLE: float = 0.0

# Type d'anomalie du constat par cable.
TYPE_ANO_CABLE_NON_ALTIMETRE: str = "cable_points_leve_altitude_nulle"


def altitudes_points_leve_intermediaires(cable: dict[str, Any], index_points: IndexPointsLeve) -> list[float]:
    """Altitudes des points de leve superposes aux sommets intermediaires d'un cable.

    Les extremites sont ecartees : un cable s'y raccorde a un ouvrage, dont le
    point de leve peut tenir son altitude d'ailleurs. Les sommets intermediaires,
    eux, ne sont leves que pour decrire le trace : leur altitude est la mesure du
    terrain, et c'est elle qui atteste que le cable est altimetre.

    Les extremites sont **topologiques** (`extraire_extremites`), et non le
    premier et le dernier sommet de la liste : les parties d'un MultiLineString
    n'etant ni ordonnees ni orientees, la lecture litterale designerait un
    raccord interne.
    """
    geometrie = cable.get("geometry") or {}
    sommets = _extraire_sommets_cable(geometrie)
    if not sommets:
        return []

    extremites = frozenset(extraire_extremites(geometrie))
    altitudes: list[float] = []
    for sommet in sommets:
        if len(sommet) < 2 or (sommet[0], sommet[1]) in extremites:
            continue
        altitudes.extend(index_points.z_candidats(sommet[0], sommet[1]))
    return altitudes


def cable_non_altimetre(altitudes: list[float]) -> bool:
    """Indique si toutes les altitudes relevees sur un cable sont nulles.

    Une liste vide ne constate rien : aucun point de leve n'est rattache aux
    sommets intermediaires, et l'absence de rattachement releve d'E-5102.
    """
    return bool(altitudes) and all(altitude == ALTITUDE_NULLE for altitude in altitudes)


def detecter_cables_non_altimetres(
    cables: list[dict[str, Any]],
    index_points: IndexPointsLeve,
    ids_cables_exclus: set[str],
) -> list[dict[str, Any]]:
    """Releve les cables dont tous les points de leve rattaches sont a zero.

    Une anomalie par cable : le defaut se corrige cable par cable, en reprenant
    le leve de son trace. Un cable altimetre, meme partiellement, n'en porte
    aucune — une seule mesure reelle atteste que son trace a ete leve.
    """
    anomalies: list[dict[str, Any]] = []
    for cable in cables:
        if obtenir_id_feature(cable) in ids_cables_exclus:
            continue
        altitudes = altitudes_points_leve_intermediaires(cable, index_points)
        if not cable_non_altimetre(altitudes):
            continue
        anomalies.append(
            {
                "id_cable": obtenir_id_feature(cable),
                "couche": cable.get("_couche"),
                "type_anomalie": TYPE_ANO_CABLE_NON_ALTIMETRE,
                "nombre_points_leve": len(altitudes),
                "geometrie": cable.get("geometry"),
            }
        )
    return anomalies


def _charger_cables(repertoire: str, fichiers_cables: Sequence[str]) -> list[dict[str, Any]]:
    """Rassemble les cables a controler des couches presentes.

    Meme perimetre que `controler_couches_cables` : seules les entites au statut
    « UnderCommissionning » entrent, les couches absentes sont ignorees.
    """
    cables: list[dict[str, Any]] = []
    for fichier in fichiers_cables:
        collection = lire_geojson(os.path.join(repertoire, fichier))
        if collection is None:
            continue
        nom_couche = Path(fichier).stem
        for cable in filtrer_cables_a_controler(collection.get("features", [])):
            # La couche d'origine suit le cable jusqu'au fichier d'ecarts, comme
            # pour les anomalies de sommets.
            cables.append({**cable, "_couche": nom_couche})
    return cables


def construire_geojson_cables_non_altimetres(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le FeatureCollection des cables non altimetres.

    Chaque feature porte le trace du cable en cause, et non un point : le defaut
    vaut pour le cable entier, aucun sommet n'etant plus fautif qu'un autre.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_cable": a["id_cable"],
                "couche": a.get("couche"),
                "type_anomalie": a["type_anomalie"],
                "nombre_points_leve": a["nombre_points_leve"],
                "version": version,
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


def analyser_cables_non_altimetres(
    repertoire: str,
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Releve les cables dont les points de leve rattaches sont tous a zero.

    Reprend le chargement du moteur — points de leve indexes, couches de cables
    du profil de version, exclusion des cables aeriens — et rend une anomalie
    par cable en defaut.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_POINT_LEVE, repertoire_resolu))

    features_points = collection_points.get("features", [])
    version_effective = resoudre_version(version, features_points)
    index_points = indexer_points_leve(features_points)

    cables = _charger_cables(repertoire_resolu, resoudre_fichiers_cables(version_effective))
    if not cables:
        return rapport_sans_objet(f"Aucun cable a controler dans {repertoire_resolu}")

    ids_exclus = charger_ids_cables_aeriens(repertoire_resolu)
    anomalies = detecter_cables_non_altimetres(cables, index_points, ids_exclus)
    geojson_ecarts = construire_geojson_cables_non_altimetres(
        anomalies, profil, version_effective, collection_points.get("crs")
    )

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, fichier_sortie))

    return {
        "succes": True,
        "version_detectee": version_effective,
        "cables_controles": len(cables) - len(ids_exclus & {obtenir_id_feature(c) for c in cables}),
        "cables_exclus": len(ids_exclus),
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "sortie": chemin_ecrit,
    }


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
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
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration par couche
# ---------------------------------------------------------------------------


def controler_couches_cables(
    repertoire: str,
    fichiers_cables: Sequence[str],
    index_points: IndexPointsLeve,
    ids_cables_exclus: set[str],
    index_geomsupp: IndexGeomSupp | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[str]]:
    """Execute le controle sur chaque couche de cables presente dans le repertoire.

    Seules les entites au statut « UnderCommissionning » sont controlees ; les
    cables references par un cheminement aerien (ids_cables_exclus) sont exclus,
    comme dans E-5201. Les couches absentes sont ignorees silencieusement (cas
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


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute l'analyse en mode CLI, pour le compte du controle appelant.

    Charge les points de leve, resout la version RecoStaR, indexe les points par
    XY, determine les couches de cables a controler puis verifie chaque sommet.
    Ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    collection_points = lire_geojson(os.path.join(repertoire_resolu, FICHIER_POINT_LEVE))
    if collection_points is None:
        return rapport_sans_objet(motif_couche_absente(FICHIER_POINT_LEVE, repertoire_resolu))

    features_points = collection_points.get("features", [])
    version_effective = resoudre_version(version, features_points)
    index_points = indexer_points_leve(features_points)

    fichiers_cables = resoudre_fichiers_cables(version_effective)
    ids_exclus = charger_ids_cables_aeriens(repertoire_resolu)
    geometries_supp = charger_geometries_supplementaires(repertoire_resolu)
    anomalies, crs_cables, couches_traitees = controler_couches_cables(
        repertoire_resolu, fichiers_cables, index_points, ids_exclus, IndexGeomSupp(geometries_supp)
    )
    if not couches_traitees:
        return rapport_sans_objet(f"Aucune couche de cables dans {repertoire_resolu} : aucun element a controler")

    crs = crs_cables if crs_cables is not None else collection_points.get("crs")
    # Le moteur a releve toutes les anomalies ; le controle appelant ne
    # retient que celles de son code. Les compteurs qui suivent portent donc
    # sur son perimetre, non sur celui du moteur.
    anomalies = filtrer_par_type(anomalies, types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, version_effective, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    nb_absent = sum(1 for a in anomalies if a["type_anomalie"] == TYPE_ANO_ABSENT)

    return {
        "succes": True,
        "version_detectee": version_effective,
        "couches_controlees": couches_traitees,
        "cables_exclus": len(ids_exclus),
        "geometries_supplementaires_indexees": len(geometries_supp),
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_sommets_sans_point_leve": nb_absent,
        "nombre_sommets_coordonnees_differentes": len(anomalies) - nb_absent,
        "sortie": chemin_ecrit,
    }
