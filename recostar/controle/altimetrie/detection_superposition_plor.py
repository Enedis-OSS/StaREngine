"""
Moteur de detection des points leves superposes de meme type de leve.

Deux points leves poses au meme endroit et mesurant la **meme grandeur** font
double emploi : l'un des deux est une saisie en trop, et rien ne dit lequel des
deux releves fait foi. Deux leves superposes de types differents sont en revanche
normaux — une charge et une altitude se mesurent au meme point, c'est meme ce
qu'E-6104 exige.

Le verificateur decline la regle sous deux codes, qui different par la seule
maille de la superposition :

    E-3300  superposition complete, X, Y et Z          niveau basse
    E-6206  superposition en X, Y, Z quelconque        niveau moyenne

E-6206 **englobe** E-3300 : deux leves superposes en X, Y, Z le sont a fortiori
en X, Y. Un meme groupe peut donc porter les deux anomalies, sous deux codes de
niveaux differents — arbitrage metier. Ce n'est pas un doublon de signalement :
le verificateur nomme deux defauts distincts, le second plus large et plus grave,
et masquer l'un sous l'autre priverait le rapport d'une des deux mailles.

Le GML source fait foi
----------------------
Le moteur lit le **GML d'entree**, comme E-6104 et E-6207 et par la meme
mecanique (`fonctions_communes.points_leve_gml`). `conversion_V1_1` supprime
`TypeLeve` : sur un GeoJSON issu du pipeline, la regle serait inapplicable — les
types de leve n'y sont plus distinguables, quelle que soit la version reelle du
jeu.

Sans GML, le moteur se replie sur les GeoJSON : ils portent `TypeLeve` lorsqu'ils
viennent du convertisseur `conversion_V1`. Le repli est signale par `source` dans
le rapport.

Restreint a la RecoStaR V1.0
----------------------------
`TypeLeve` n'existe qu'en V1.0. En V1.1, aucun type ne qualifie plus un point
leve : la regle est **sans objet**, et les controles le declarent tel quel plutot
que de comparer des coordonnees nues, ce qui serait une autre regle. Meme parti
qu'E-6104 et E-6207.

Egalite stricte des coordonnees : elles sortent du meme document et du meme
analyseur, et aucune tolerance ne couvrirait d'artefact numerique. Meme parti
que le moteur des sommets de cables, dont l'egalite exacte X/Y/Z ne doit pas
etre relachee.

Regle de gestion : une anomalie **par groupe** de points superposes, et non par
point. Le groupe est l'unite a corriger — c'est lui qui porte le doublon — et ses
identifiants sont tous reportes a l'ecart.

Controles issus de ce moteur : e3300, e6206.

"""

import os
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.ecarts import filtrer_par_type
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_anomalies_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_TYPE_LEVE,
    FICHIER_POINT_LEVE,
)
from recostar.controle.fonctions_communes.points_leve_gml import (
    VERSION_LEVE,
    charger_points_leve,
)
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    resoudre_version,
)
from recostar.controle.xsd_structuration.detection_version import detecter_version

# Fichier source analyse par ce moteur
FICHIER_SOURCE: str = FICHIER_POINT_LEVE


# Types d'anomalie produits, un par maille de superposition.
TYPE_SUPERPOSITION_COMPLETE: str = "plor_superpose_meme_type"
TYPE_SUPERPOSITION_XY: str = "plor_superpose_xy_meme_type"

# Nombre de points a partir duquel un groupe est un doublon.
TAILLE_DOUBLON: int = 2

# Nombre de coordonnees retenues par la maille planimetrique.
RANG_PLANIMETRIQUE: int = 2


# ---------------------------------------------------------------------------
# Cles de groupement (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def _coordonnees_point(feature: dict[str, Any]) -> tuple[float, ...] | None:
    """Retourne les coordonnees d'un point leve, ou None s'il n'en a pas.

    Une entite sans geometrie ponctuelle n'est pas comparable : sa position ne
    peut etre confrontee a aucune autre.
    """
    geometrie = feature.get("geometry")
    if not geometrie or geometrie.get("type") != "Point":
        return None
    coordonnees = geometrie.get("coordinates")
    if not coordonnees:
        return None
    return tuple(coordonnees)


def cle_complete(feature: dict[str, Any]) -> tuple[tuple[float, ...], str | None] | None:
    """Cle de la maille E-3300 : coordonnees completes et TypeLeve."""
    coordonnees = _coordonnees_point(feature)
    if coordonnees is None:
        return None
    return (coordonnees, (feature.get("properties") or {}).get(CHAMP_TYPE_LEVE))


def cle_planimetrique(feature: dict[str, Any]) -> tuple[tuple[float, ...], str | None] | None:
    """Cle de la maille E-6206 : X, Y et TypeLeve, le Z etant indifferent.

    Un point a deux coordonnees est admis tel quel : sa planimetrie est
    complete, et l'absence de Z releve d'E-5107.
    """
    coordonnees = _coordonnees_point(feature)
    if coordonnees is None:
        return None
    if len(coordonnees) < RANG_PLANIMETRIQUE:
        return None
    return (coordonnees[:RANG_PLANIMETRIQUE], (feature.get("properties") or {}).get(CHAMP_TYPE_LEVE))


# Association type d'anomalie -> cle de groupement, dans l'ordre d'analyse.
CLES_PAR_TYPE: tuple[tuple[str, Callable[[dict[str, Any]], Any]], ...] = (
    (TYPE_SUPERPOSITION_COMPLETE, cle_complete),
    (TYPE_SUPERPOSITION_XY, cle_planimetrique),
)


def grouper_par_cle(
    features: list[dict[str, Any]],
    extraire_cle: Callable[[dict[str, Any]], Any],
) -> dict[Any, list[str | None]]:
    """Groupe les identifiants des points leves par cle de superposition.

    Ne retourne que les groupes en doublon : un point seul sur sa cle est le cas
    normal, et le conserver ferait porter le filtrage a l'appelant.
    """
    obtenir_id = obtenir_id_feature  # alias local (boucle)
    groupes: dict[Any, list[str | None]] = defaultdict(list)
    for feature in features:
        cle = extraire_cle(feature)
        if cle is None:
            continue
        groupes[cle].append(obtenir_id(feature))
    return {cle: ids for cle, ids in groupes.items() if len(ids) >= TAILLE_DOUBLON}


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detecte les groupes superposes, aux deux mailles.

    Un meme groupe peut ressortir sous les deux types : une superposition
    complete en est une en X, Y. C'est l'arbitrage retenu — E-6206 englobe
    E-3300 —, chaque code gardant sa maille et son niveau.
    """
    anomalies: list[dict[str, Any]] = []
    for type_anomalie, extraire_cle in CLES_PAR_TYPE:
        anomalies.extend(
            {
                "type_anomalie": type_anomalie,
                "coordonnees": list(coordonnees),
                "type_leve": type_leve,
                "ids_entites": ids,
                "nb_points": len(ids),
            }
            for (coordonnees, type_leve), ids in grouper_par_cle(features, extraire_cle).items()
        )
    return anomalies


def compter_points_controles(features: list[dict[str, Any]]) -> int:
    """Compte les points leves comparables, seuls a entrer dans le groupement."""
    return sum(1 for feature in features if _coordonnees_point(feature) is not None)


def compter_points_en_doublon(anomalies: list[dict[str, Any]]) -> int:
    """Compte les points portes par les groupes en anomalie."""
    return sum(anomalie["nb_points"] for anomalie in anomalies)


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    profil: ProfilEcarts,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des groupes superposes.

    Une feature par groupe, positionnee aux coordonnees de sa cle : completes
    pour la maille E-3300, planimetriques pour E-6206. La geometrie decrit ainsi
    exactement ce que le groupe a en commun, et rien de plus.

    Les identifiants du groupe sont joints en une chaine : un ecart nomme tous
    les points a arbitrer, l'operateur ayant a choisir lequel conserver.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_SOURCE,
                "ids_entites": ",".join(str(i) for i in a["ids_entites"] if i is not None),
                "nb_points": a["nb_points"],
                CHAMP_TYPE_LEVE: a["type_leve"],
            },
            "geometry": {"type": "Point", "coordinates": a["coordonnees"]},
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, profil)


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def charger_source(
    repertoire: Path,
    chemin_gml: Path | None,
    version_demandee: str,
) -> tuple[list[dict[str, Any]] | None, str, str | None, dict[str, Any] | None]:
    """Choisit la source, en lit les points leves et resout la version.

    La lecture est partagee avec E-6104 et E-6207
    (`fonctions_communes.points_leve_gml`) ; seule la resolution de version reste
    ici : elle se lit dans l'en-tete du GML quand il y en a un, et se deduit du
    contenu sinon.
    """
    features, source, gml_lu, crs = charger_points_leve(repertoire, chemin_gml)
    if features is None:
        return None, source, None, None
    if gml_lu is not None:
        version_gml = detecter_version(gml_lu)
        version = version_demandee if version_demandee != JETON_AUTO else (version_gml or VERSION_LEVE)
        return features, source, version, crs
    return features, source, resoudre_version(version_demandee, features), crs


def executer_analyse(
    repertoire: str,
    types_retenus: frozenset[str],
    profil: ProfilEcarts,
    fichier_sortie: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute la detection des superpositions et ecrit les ecarts d'un controle.

    Le moteur releve les deux mailles ; le controle appelant ne retient que
    celle de son code. Les compteurs qui suivent portent donc sur son perimetre.
    """
    repertoire_resolu = Path(repertoire).resolve()
    features, source, version_effective, crs = charger_source(repertoire_resolu, chemin_gml, version)
    if features is None:
        return rapport_sans_objet(
            motif_couche_absente(FICHIER_SOURCE, str(repertoire_resolu)),
            source=source,
            nombre_points_controles=0,
        )

    if version_effective != VERSION_LEVE:
        return rapport_sans_objet(
            f"Jeu en RecoStaR V{version_effective} : le champ TypeLeve n'existe qu'en V{VERSION_LEVE}",
            source=source,
            version_detectee=version_effective,
            nombre_points_controles=0,
        )

    anomalies = filtrer_par_type(detecter_anomalies(features), types_retenus)
    geojson_ecarts = construire_geojson_ecarts(anomalies, profil, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else str(repertoire_resolu)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, fichier_sortie)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "source": source,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_anomalies_par_type(anomalies),
        "nombre_points_controles": compter_points_controles(features),
        "nombre_points_en_doublon": compter_points_en_doublon(anomalies),
        "sortie": chemin_ecrit,
    }
