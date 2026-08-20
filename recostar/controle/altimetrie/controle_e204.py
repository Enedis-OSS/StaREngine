"""
Controle des doublons spatiaux dans RPD_PointLeveOuvrageReseau_Reco.

Detecte les entites ponctuelles partageant exactement les memes coordonnees.
La logique de detection varie selon la version Recostar :
- v1.1 : doublon si memes coordonnees, sans distinction de type.
- v1.0 : doublon si memes coordonnees ET meme champ TypeLeve.

Usage CLI :
    python controle_e204.py --repertoire <chemin> [--sortie <chemin>]
                            [--version {auto,1.0,1.1}]

Sortie : ecarts_e204_doublons_spatiaux.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils_geojson import (
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source analyse par ce controle
FICHIER_SOURCE: str = "RPD_PointLeveOuvrageReseau_Reco.geojson"

# Fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e204_doublons_spatiaux.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E204"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "doublons_spatiaux": ("Plusieurs points levés partagent exactement les mêmes coordonnées."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("ids_entites",),
)


# Niveau de priorite : mineur — l'ecart est signale et compte dans le rapport,
# mais ne declasse pas la famille (cf. PRIORITES_DECLASSANTES dans
# synthese_controles).
PRIORITE_ANOMALIE: str = "mineur"

# Gestion des versions RecoStaR (meme convention que xsd_structuration)
VERSION_DEFAUT: str = "1.1"
VERSIONS_SUPPORTEES: tuple[str, ...] = ("1.0", "1.1")
JETON_AUTO: str = "auto"

# Champ discriminant present uniquement en version 1.0
CHAMP_TYPE_LEVE: str = "TypeLeve"

# Fichier interroge pour deduire la version dans les controles dont
# RPD_PointLeveOuvrageReseau_Reco n'est pas une source (E202, E203). Pour E204
# il coincide avec sa propre source.
FICHIER_DETECTION_VERSION: str = FICHIER_SOURCE


# ---------------------------------------------------------------------------
# Detection de la version depuis le contenu GeoJSON
# ---------------------------------------------------------------------------


def detecter_version_depuis_features(features: list[dict[str, Any]]) -> str | None:
    """Deduit la version RecoStaR depuis les proprietes des entites.

    Si au moins une entite possede le champ TypeLeve, la collection est
    considered de version 1.0 (champ absent en v1.1). Retourne None si
    la version ne peut pas etre determinee (repli vers VERSION_DEFAUT).
    """
    for feature in features:
        props = feature.get("properties") or {}
        if CHAMP_TYPE_LEVE in props:
            return "1.0"
    return None


def resoudre_version(
    version_demandee: str,
    features: list[dict[str, Any]],
) -> str:
    """Resout la version effective a appliquer pour ce controle.

    En mode auto, deduit la version depuis les proprietes GeoJSON et se
    replie sur VERSION_DEFAUT si la detection echoue. En mode explicite,
    applique directement la version demandee.
    """
    if version_demandee != JETON_AUTO:
        return version_demandee

    version_detectee = detecter_version_depuis_features(features)
    if version_detectee is None:
        print(
            f"Version non detectee dans les features : repli sur {VERSION_DEFAUT}.",
            file=sys.stderr,
        )
        return VERSION_DEFAUT
    return version_detectee


def determiner_version_depuis_repertoire(
    repertoire: str,
    version_demandee: str,
) -> str:
    """Resout la version RecoStaR en lisant le fichier de detection du repertoire.

    Helper partage par les controles dont RPD_PointLeveOuvrageReseau_Reco n'est
    pas une source (E202, E203). En mode explicite, la version demandee est
    appliquee telle quelle sans lecture disque. En mode auto, la detection
    reutilise resoudre_version sur les entites du fichier de detection ; ce
    fichier n'etant pas une source de ces controles, son absence n'est pas
    bloquante et entraine le repli sur VERSION_DEFAUT.
    """
    if version_demandee != JETON_AUTO:
        return version_demandee
    collection = lire_geojson(os.path.join(repertoire, FICHIER_DETECTION_VERSION))
    features = collection.get("features", []) if collection is not None else []
    return resoudre_version(version_demandee, features)


# ---------------------------------------------------------------------------
# Construction des cles de doublon selon la version
# ---------------------------------------------------------------------------


def _cle_doublon_v1_1(
    geom: dict[str, Any],
    _props: dict[str, Any],
) -> tuple[float, ...] | None:
    """Cle de doublon pour la version 1.1 : coordonnees seules."""
    coordonnees = geom.get("coordinates")
    if coordonnees is None:
        return None
    return tuple(coordonnees)


def _cle_doublon_v1_0(
    geom: dict[str, Any],
    props: dict[str, Any],
) -> tuple[tuple[float, ...], str | None] | None:
    """Cle de doublon pour la version 1.0 : coordonnees + TypeLeve."""
    coordonnees = geom.get("coordinates")
    if coordonnees is None:
        return None
    return (tuple(coordonnees), props.get(CHAMP_TYPE_LEVE))


# Registre : code de version -> extracteur de cle de doublon
_EXTRACTEURS_CLE: dict[str, Callable[..., Any]] = {
    "1.0": _cle_doublon_v1_0,
    "1.1": _cle_doublon_v1_1,
}


# ---------------------------------------------------------------------------
# Detection des doublons
# ---------------------------------------------------------------------------


def _indexer_points_par_cle(
    features: list[dict[str, Any]],
    extraire_cle: Callable[..., Any],
) -> dict[Any, list[str | None]]:
    """Groupe les identifiants de features par leur cle de doublon.

    Seules les geometries de type Point sont analysees.
    Retourne un dict {cle: [id1, id2, ...]} ne contenant que les groupes en doublon.
    """
    obtenir_id = obtenir_id_feature  # alias local : evite le lookup global en boucle
    groupes: dict[Any, list[str | None]] = defaultdict(list)

    for feature in features:
        geom = feature.get("geometry")
        if not geom or geom.get("type") != "Point":
            continue
        props = feature.get("properties") or {}
        cle = extraire_cle(geom, props)
        if cle is None:
            continue
        groupes[cle].append(obtenir_id(feature))

    return {cle: ids for cle, ids in groupes.items() if len(ids) > 1}


def _construire_anomalie_v1_1(
    cle: tuple[float, ...],
    ids: list[str | None],
) -> dict[str, Any]:
    """Construit une anomalie pour la version 1.1 (coordonnees seules)."""
    return {
        "coordonnees": list(cle),
        "ids_entites": ids,
        "nb_points": len(ids),
    }


def _construire_anomalie_v1_0(
    cle: tuple[tuple[float, ...], str | None],
    ids: list[str | None],
) -> dict[str, Any]:
    """Construit une anomalie pour la version 1.0 (coordonnees + TypeLeve)."""
    coordonnees, type_leve = cle
    return {
        "coordonnees": list(coordonnees),
        "ids_entites": ids,
        "nb_points": len(ids),
        "type_leve": type_leve,
    }


def detecter_doublons_spatiaux(
    features: list[dict[str, Any]],
    version: str,
) -> list[dict[str, Any]]:
    """Detecte les groupes de points en doublon spatial.

    Retourne une anomalie par groupe de points partageant la meme cle de doublon.
    La cle depend de la version : coordonnees seules (v1.1) ou coordonnees + TypeLeve (v1.0).
    """
    extraire_cle = _EXTRACTEURS_CLE.get(version, _cle_doublon_v1_1)
    groupes = _indexer_points_par_cle(features, extraire_cle)

    if version == "1.0":
        return [_construire_anomalie_v1_0(cle, ids) for cle, ids in groupes.items()]
    return [_construire_anomalie_v1_1(cle, ids) for cle, ids in groupes.items()]


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _construire_proprietes_feature(
    anomalie: dict[str, Any],
    version: str,
) -> dict[str, Any]:
    """Construit les proprietes d'une feature GeoJSON pour une anomalie."""
    ids_str = ",".join(str(i) for i in anomalie["ids_entites"] if i is not None)
    props: dict[str, Any] = {
        "ids_entites": ids_str,
        "nb_points": anomalie["nb_points"],
        "type_anomalie": "doublons_spatiaux",
        "priorite": PRIORITE_ANOMALIE,
        "version": version,
    }
    if version == "1.0" and "type_leve" in anomalie:
        props[CHAMP_TYPE_LEVE] = anomalie["type_leve"]
    return props


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    version: str,
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection Point des groupes de doublons.

    Une feature est produite par groupe, positionnee aux coordonnees communes.
    Le champ crs est propage depuis le fichier source pour QGIS.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": _construire_proprietes_feature(anomalie, version),
            "geometry": {
                "type": "Point",
                "coordinates": anomalie["coordonnees"],
            },
        }
        for anomalie in anomalies
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
    """Execute le controle des doublons spatiaux en mode CLI.

    Charge le fichier source, resout la version, detecte les doublons
    et ecrit le fichier d'ecarts GeoJSON.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    chemin_source = os.path.join(repertoire_resolu, FICHIER_SOURCE)
    collection = lire_geojson(chemin_source)
    if collection is None:
        return {
            "succes": False,
            "erreur": f"Fichier {FICHIER_SOURCE} introuvable dans {repertoire_resolu}",
        }

    features = collection.get("features", [])
    crs = collection.get("crs")
    version_effective = resoudre_version(version, features)

    anomalies = detecter_doublons_spatiaux(features, version_effective)
    geojson_ecarts = construire_geojson_ecarts(anomalies, version_effective, crs)

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    nb_points_en_doublon = sum(a["nb_points"] for a in anomalies)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "version_detectee": version_effective,
        "nombre_anomalies": len(anomalies),
        "nombre_points_en_doublon": nb_points_en_doublon,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle des doublons spatiaux."""
    choix_version = (JETON_AUTO,) + VERSIONS_SUPPORTEES
    parseur = argparse.ArgumentParser(
        description=("Controle E204 : detection des doublons spatiaux dans RPD_PointLeveOuvrageReseau_Reco")
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help=f"Repertoire contenant {FICHIER_SOURCE}",
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
            "proprietes GeoJSON ; sinon imposer '1.0' ou '1.1'."
        ),
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
