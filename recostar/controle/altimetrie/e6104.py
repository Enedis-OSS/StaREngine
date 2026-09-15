"""
Controle E-6104 : Présence d'un PLOR de type ChargeGeneratrice sans PLOR de type AltitudeGeneratrice superposé

Un leve de ChargeGeneratrice mesure une charge mecanique en un point ; il ne dit
rien de l'altitude de ce point. Un leve d'AltitudeGeneratrice doit donc lui
repondre a la meme position : sans lui, la charge est relevee en un lieu dont
l'altitude n'est pas connue, et le couple ne decrit qu'une moitie de mesure.

La regle porte sur le leve de charge, non sur celui d'altitude : un leve
d'altitude isole est parfaitement normal — c'est le cas courant — et n'appelle
aucun leve de charge.

Superposition geographique
--------------------------
La superposition est **planimetrique** : les deux leves mesurent deux grandeurs
differentes au meme endroit, et rien n'impose que leurs altitudes coincident —
c'est meme la charge qui n'en porte pas de significative.

Le predicat est `dwithin` a TOLERANCE_SUPERPOSITION (1 mm), la convention de la
famille pour un contact de mesure nulle : E-6211 l'applique deja au meme type de
leve, E-9201 et E-9202 aux geometries supplementaires. Un index STRtree porte les
leves d'altitude : la confrontation est sinon quadratique, et un jeu en compte
plusieurs milliers.

Le GML source fait foi
----------------------
Comme E-6207, ce controle lit le **GML d'entree**. `conversion_V1_1` normalise un
GML V1.0 vers le modele V1.1 et supprime `TypeLeve` : le GeoJSON ne distingue
plus les deux types de leve, et la regle y serait sans objet faute de pouvoir les
separer. La lecture est partagee avec E-6207
(`fonctions_communes.points_leve_gml`).

Sans GML, le controle se replie sur les GeoJSON : ils portent `TypeLeve`
lorsqu'ils viennent du convertisseur `conversion_V1`. Le repli est signale par
`source` dans le rapport, afin qu'un resultat vide ne soit jamais pris pour une
verification.

Restreint a la RecoStaR V1.0
----------------------------
`TypeLeve` n'existe qu'en V1.0. La V1.1 porte un attribut `ChargeGeneratrice`
directement sur le point leve, sans type a confronter : la regle est alors
**sans objet**, et le controle le declare tel quel plutot que de retourner un
faux conforme. Meme parti qu'E-6207.

Un leve de charge sans geometrie exploitable est ignore : sans position, la
superposition n'est pas jugeable, et l'absence de coordonnees releve d'E-5107.

Regle de gestion : une anomalie par leve de charge orphelin. Deux charges au meme
endroit, toutes deux sans altitude, portent deux anomalies : chacune est a
completer pour elle-meme.

Usage CLI :
    python -m recostar.controle.altimetrie.e6104 --repertoire <chemin> [--sortie <chemin>]
                                                 [--gml <fichier.gml>] [--version {auto,1.0,1.1}]

Sortie : ecarts_e6104_charge_sans_altitude.geojson
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from shapely import STRtree
from shapely.geometry import Point

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_TYPE_LEVE,
    FICHIER_POINT_LEVE,
    TYPE_LEVE_ALTITUDE,
    TYPE_LEVE_CHARGE,
)
from recostar.controle.fonctions_communes.points_leve_gml import (
    VERSION_LEVE,
    charger_points_leve,
)
from recostar.controle.fonctions_communes.proprietes import valeur_numerique
from recostar.controle.fonctions_communes.resultats import (
    motif_couche_absente,
    rapport_sans_objet,
)
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    resoudre_version,
)
from recostar.controle.xsd_structuration.detection_version import detecter_version

# Fichier source analyse par ce controle
FICHIER_SOURCE: str = FICHIER_POINT_LEVE

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6104_charge_sans_altitude.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6104"

# Type d'anomalie unique produit par ce controle
TYPE_CHARGE_SANS_ALTITUDE: str = "charge_sans_altitude_superposee"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_CHARGE_SANS_ALTITUDE: (
        "Le point levé de type ChargeGeneratrice n'a aucun point levé "
        "de type AltitudeGeneratrice superposé géographiquement."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_point_leve",),
    couche_source=FICHIER_SOURCE,
)


# ---------------------------------------------------------------------------
# Regle metier (fonctions pures, testables sans I/O)
# ---------------------------------------------------------------------------


def type_leve(feature: dict[str, Any]) -> str | None:
    """Retourne le TypeLeve porte par un point leve."""
    return (feature.get("properties") or {}).get(CHAMP_TYPE_LEVE)


def point_planimetrique(feature: dict[str, Any]) -> Point | None:
    """Retourne la position planimetrique d'un point leve, ou None.

    Le Z est ecarte : la superposition de deux leves de nature differente est
    planimetrique, leurs altitudes n'ayant pas vocation a coincider.
    """
    geometrie = feature.get("geometry")
    if not geometrie or geometrie.get("type") != "Point":
        return None
    coordonnees = geometrie.get("coordinates") or []
    if len(coordonnees) < 2:
        return None
    x = valeur_numerique(coordonnees[0])
    y = valeur_numerique(coordonnees[1])
    if x is None or y is None:
        return None
    return Point(x, y)


def filtrer_par_type(features: list[dict[str, Any]], type_attendu: str) -> list[dict[str, Any]]:
    """Restreint les points leves a ceux d'un type donne."""
    return [feature for feature in features if type_leve(feature) == type_attendu]


def indexer_altitudes(features: list[dict[str, Any]]) -> STRtree:
    """Construit l'index spatial des leves d'altitude localises.

    Un STRtree plutot qu'une confrontation deux a deux : un jeu compte plusieurs
    milliers de points leves, et le produit cartesien serait le cout dominant du
    controle. Les leves sans position exploitable sont ecartes — ils ne peuvent
    repondre a aucune charge.
    """
    points = [point for feature in features if (point := point_planimetrique(feature)) is not None]
    return STRtree(points)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detecte les leves de charge sans leve d'altitude superpose.

    Un leve de charge prive de position est ignore : la superposition n'est pas
    jugeable, et l'absence de coordonnees releve d'E-5107.
    """
    arbre = indexer_altitudes(filtrer_par_type(features, TYPE_LEVE_ALTITUDE))
    interroger = arbre.query  # alias local (boucle)
    tolerance = TOLERANCE_SUPERPOSITION  # idem : constante lue une seule fois

    anomalies: list[dict[str, Any]] = []
    for feature in filtrer_par_type(features, TYPE_LEVE_CHARGE):
        point = point_planimetrique(feature)
        if point is None:
            continue
        if len(interroger(point, predicate="dwithin", distance=tolerance)) > 0:
            continue
        anomalies.append(
            {
                "type_anomalie": TYPE_CHARGE_SANS_ALTITUDE,
                "id_point_leve": obtenir_id_feature(feature),
                "geometrie": feature.get("geometry"),
            }
        )
    return anomalies


def compter_points_controles(features: list[dict[str, Any]]) -> int:
    """Compte les leves de charge, seules entites que la regle qualifie."""
    return len(filtrer_par_type(features, TYPE_LEVE_CHARGE))


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des leves de charge orphelins.

    La geometrie de l'ecart est celle du leve de charge : c'est a son endroit
    qu'un leve d'altitude manque et doit etre ajoute.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_SOURCE,
                "id_point_leve": a["id_point_leve"],
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


def charger_source(
    repertoire: Path,
    chemin_gml: Path | None,
    version_demandee: str,
) -> tuple[list[dict[str, Any]] | None, str, str | None, dict[str, Any] | None]:
    """Choisit la source, en lit les points leves et resout la version.

    La lecture est partagee avec E-6207 (`fonctions_communes.points_leve_gml`) ;
    seule la resolution de version reste ici : elle se lit dans l'en-tete du GML
    quand il y en a un, et se deduit du contenu sinon.
    """
    features, source, gml_lu, crs = charger_points_leve(repertoire, chemin_gml)
    if features is None:
        return None, source, None, None
    if gml_lu is not None:
        version_gml = detecter_version(gml_lu)
        version = version_demandee if version_demandee != JETON_AUTO else (version_gml or VERSION_LEVE)
        return features, source, version, crs
    return features, source, resoudre_version(version_demandee, features), crs


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6104 et ecrit ses ecarts.

    Lit les points leves depuis le GML source — seule source distinguant les
    deux types de leve apres conversion — et n'applique la regle qu'en V1.0.
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

    anomalies = detecter_anomalies(features)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else str(repertoire_resolu)
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "source": source,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": {TYPE_CHARGE_SANS_ALTITUDE: len(anomalies)} if anomalies else {},
        "nombre_points_controles": compter_points_controles(features),
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-6104."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-6104 : en RecoStaR V1.0, un PLOR de type ChargeGeneratrice "
            "doit avoir un PLOR de type AltitudeGeneratrice superposé."
        )
    )
    parseur.add_argument("--repertoire", required=True, help=f"Repertoire contenant {FICHIER_SOURCE}")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--gml",
        default=None,
        help="Fichier GML source (defaut : le GML present dans le repertoire, s'il est unique)",
    )
    parseur.add_argument(
        "--version",
        default=JETON_AUTO,
        choices=choix_version,
        help="Version RecoStaR du jeu (defaut : detection automatique)",
    )
    arguments = parseur.parse_args()
    chemin_gml = Path(arguments.gml) if arguments.gml is not None else None
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version, chemin_gml)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
