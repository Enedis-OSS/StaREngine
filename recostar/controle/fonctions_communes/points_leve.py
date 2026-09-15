"""
Rattachement des geometries supplementaires de conteneur a un point de leve.

Une geometrie supplementaire decrit l'emprise au sol d'un conteneur. La regle
verifiee est la meme quel que soit le conteneur : au moins un point de leve doit
se superposer a cette emprise. Seule change la couche de conteneur interrogee —
les coffrets pour E-9201, les supports pour E-9202 — et l'identite de l'ecart
emis. La regle n'appartient a aucun des deux : chacun l'applique a sa couche.

La superposition est evaluee par le predicat « dwithin » a
TOLERANCE_SUPERPOSITION metres, et non par un contact strict : un point pose sur
le **contour** du polygone realise un contact de mesure nulle, que l'arrondi
millimetrique de la posList GML suffit a rompre.
"""

from typing import Any

from shapely import STRtree, force_2d
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from recostar.controle.fonctions_communes.geojson import ProfilEcarts, normaliser_geojson_ecarts
from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_GEOMSUPP_HREF,
    CHAMP_STATUT,
    STATUT_MISE_EN_SERVICE,
)

# Type d'anomalie emis : la geometrie supplementaire n'est couverte par aucun
# point de leve. Identique pour les deux controles, seul leur code differe.
TYPE_ANOMALIE: str = "point_leve_absent"


def extraire_hrefs_geomsupp_liees(features_conteneurs: list[dict[str, Any]], version: str) -> frozenset[str]:
    """Identifiants des geometries supplementaires referencees par des conteneurs.

    En V1.1, seuls les conteneurs en cours de mise en service sont retenus : le
    recolement ne porte que sur ce qu'il declare poser. En V1.0, le champ Statut
    n'etant pas exploitable, tous les conteneurs portant une reference sont
    inclus.

    frozenset : le rattachement est ensuite teste geometrie par geometrie, donc
    en O(1) par test.
    """
    hrefs: set[str] = set()
    for feature in features_conteneurs:
        proprietes = feature.get("properties") or {}
        if version == "1.1" and proprietes.get(CHAMP_STATUT) != STATUT_MISE_EN_SERVICE:
            continue
        href = proprietes.get(CHAMP_GEOMSUPP_HREF)
        if isinstance(href, str) and href:
            hrefs.add(href)
    return frozenset(hrefs)


def charger_points_leve(features: list[dict[str, Any]]) -> list[BaseGeometry]:
    """Convertit les entites ponctuelles en geometries Shapely planimetriques.

    Les Z sont supprimes (force_2d) : le rattachement est planimetrique, l'ecart
    altimetrique relevant des controles d'altimetrie. Une geometrie malformee est
    ignoree plutot que de faire echouer le controle entier.
    """
    points: list[BaseGeometry] = []
    for feature in features:
        geometrie = feature.get("geometry")
        if geometrie is None or geometrie.get("type") != "Point":
            continue
        try:
            points.append(force_2d(shape(geometrie)))
        except Exception:  # nosec B112
            continue
    return points


def detecter_geomsupp_sans_point_leve(
    features_geomsupp: list[dict[str, Any]],
    ids_lies: frozenset[str],
    points_leve: list[BaseGeometry],
) -> list[dict[str, Any]]:
    """Detecte les emprises liees a un conteneur mais sans point de leve.

    Seules les geometries dont l'identifiant figure dans `ids_lies` sont
    verifiees : les autres ne decrivent pas un conteneur du perimetre.

    Retourne une liste d'anomalies {id_geomsupp, geometrie}.
    """
    arbre = STRtree(points_leve)
    interroger = arbre.query  # alias local : evite le lookup global en boucle
    tolerance = TOLERANCE_SUPERPOSITION  # idem : constante lue une seule fois
    anomalies: list[dict[str, Any]] = []

    for feature in features_geomsupp:
        proprietes = feature.get("properties") or {}
        identifiant = proprietes.get("id")
        if not isinstance(identifiant, str) or identifiant not in ids_lies:
            continue
        geometrie = feature.get("geometry")
        if geometrie is None:
            continue
        try:
            geometrie_2d = force_2d(shape(geometrie))
        except Exception:  # nosec B112
            continue
        if len(interroger(geometrie_2d, predicate="dwithin", distance=tolerance)) == 0:
            anomalies.append({"id_geomsupp": identifiant, "geometrie": geometrie})

    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le FeatureCollection des emprises sans point de leve.

    Chaque feature conserve le polygone de la geometrie supplementaire, ce qui
    permet de localiser l'ecart dans un SIG. Le CRS est propage depuis les
    couches sources.

    `profil` porte l'identite de l'ecart : c'est le seul point par lequel les
    deux controles se distinguent, et il est donc requis plutot que defaut —
    un defaut designerait arbitrairement l'un des deux.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "id_entite": anomalie["id_geomsupp"],
                "type_anomalie": TYPE_ANOMALIE,
                "version": version,
            },
            "geometry": anomalie["geometrie"],
        }
        for anomalie in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)
