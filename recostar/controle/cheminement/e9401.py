#!/usr/bin/env python3
"""
Controle E-9401 : les cheminements d'un meme cable sont disjoints.

Les cheminements qui portent un meme cable doivent le recouvrir **d'un bout a
l'autre**, sans interruption : mis bout a bout, ils forment une voie continue.
Un trou entre deux d'entre eux laisse une portion de cable sans cheminement —
donc sans nature de pose, sans profondeur, sans protection declarees.

Perimetre : les cinq voies de cheminement, **tous types de cable et tous
statuts**. La regle ne porte pas sur ce que le cable est ou sur l'avancement des
travaux, mais sur la continuite de son parcours.

    RPD_Fourreau_Reco            RPD_ProtectionMecanique_Reco
    RPD_Galerie_Reco             RPD_Aerien_Reco
    RPD_PleineTerre_Reco

Pourquoi la continuite, et non le recouvrement du cable
-------------------------------------------------------
Confronter la geometrie du cable a celle de ses cheminements ne prouverait rien :
la conversion **fabrique** la premiere a partir des secondes
(`recostar_to_geojson`, heritage de geometrie par la relation Cheminement_Cables).
Le cable est, mot pour mot, l'assemblage de ses cheminements ; il les recouvre
donc toujours, par construction.

Le defaut se lit sur cet assemblage lui-meme : quand les cheminements ne se
touchent pas, l'assemblage rend un MultiLineString en plusieurs troncons au lieu
d'une ligne continue. C'est exactement ce que `line_merge` met en evidence, et
c'est le sens du libelle : « les cheminements d'un meme cable sont disjoints ».

Un code local plutot qu'E-0011
------------------------------
Le verificateur nomme ce defaut `E-0011`, « les cheminements d'un meme cable sont
superposes **ou** disjoints ». Son premier volet est deja rendu par **E-5108**,
qui signale deux cheminements superposes. Rendre E-0011 ici ferait porter au meme
code deux regles que le projet tient separees, l'une detectant un doublon de
trace, l'autre un trou. L'arbitrage metier ecarte donc le code du verificateur au
profit d'un code de la serie locale, dont le libelle ne retient que le volet
restant.

Tolerance de jonction
---------------------
Deux cheminements consecutifs partagent leur extremite. `TOLERANCE_SUPERPOSITION`
(1 mm) admet l'ecart d'arrondi : les coordonnees RecoStaR sont arrondies au
millimetre des le GML, et exiger une egalite exacte ferait sortir des voies
parfaitement continues. La valeur reste tres en deca de toute precision de leve —
un trou reel, meme centimetrique, demeure detecte.

Une anomalie par cable, non par trou : c'est la voie du cable qu'il faut
reprendre, et le nombre de troncons comme l'ecart le plus faible sont reportes
pour en dire l'ampleur.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e9401_cheminements_disjoints.geojson

Usage CLI :
    python -m recostar.controle.cheminement.e9401 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import itertools
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely import force_2d, is_valid, line_merge, union_all
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
from recostar.controle.fonctions_communes.geometrie import TOLERANCE_SUPERPOSITION
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CABLES_HREF,
    COUCHES_CHEMINEMENT,
    EXTENSION_COUCHE,
)
from recostar.controle.fonctions_communes.references_cables import extraire_ids_cables_href

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9401_cheminements_disjoints.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-9401"

# Type ecrit en clair, et non importe : le releve d'exhaustivite des codes lit
# cette cle par analyse syntaxique, et ne resout qu'une constante declaree dans
# le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"cheminements_disjoints"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cheminements_disjoints": ("Les cheminements portant ce câble ne se rejoignent pas : son parcours est interrompu."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)

# Types de geometrie lineaire acceptes, comme E-5108.
TYPES_GEOMETRIE_LINEAIRE: frozenset[str] = frozenset({"LineString", "MultiLineString"})

# Longueur minimale (metres) d'un cheminement pour entrer dans l'assemblage.
# Meme seuil qu'E-5108 : en deca, la geometrie ne decrit aucun parcours.
EPSILON_LONGUEUR: float = 0.01

# Nombre de troncons au-dela duquel la voie du cable est interrompue.
SEUIL_TRONCONS: int = 2


@dataclass(frozen=True, slots=True)
class Cheminement:
    """Cheminement lineaire, avec sa geometrie planimetrique et sa couche."""

    couche: str
    id_entite: str
    geometrie: BaseGeometry


def _cheminement_depuis_feature(feature: dict[str, Any], couche: str) -> Cheminement | None:
    """Cree un Cheminement depuis une feature, ou None si sa geometrie ne dit rien.

    Le try/except est justifie : `shape()` peut echouer sur des coordonnees
    malformees, lues depuis un fichier externe.
    """
    geometrie = feature.get("geometry")
    if geometrie is None or geometrie.get("type") not in TYPES_GEOMETRIE_LINEAIRE:
        return None
    if not geometrie.get("coordinates"):
        return None
    identifiant = obtenir_id_feature(feature)
    if identifiant is None:
        return None
    try:
        forme = force_2d(shape(geometrie))
    except Exception:
        return None
    if forme.is_empty or not is_valid(forme) or forme.length < EPSILON_LONGUEUR:
        return None
    return Cheminement(couche, identifiant, forme)


def indexer_cheminements_par_cable(
    repertoire: str,
) -> tuple[dict[str, list[Cheminement]], dict[str, Any] | None, list[str]]:
    """Regroupe par cable les cheminements des cinq couches.

    Retourne (index, crs, couches_absentes). Un cheminement portant plusieurs
    cables alimente chacun d'eux : la continuite se juge cable par cable, et un
    fourreau mutualise participe a plusieurs voies.
    """
    index: dict[str, list[Cheminement]] = defaultdict(list)
    absentes: list[str] = []
    crs: dict[str, Any] | None = None
    for couche in COUCHES_CHEMINEMENT:
        collection = lire_geojson(os.path.join(repertoire, f"{couche}{EXTENSION_COUCHE}"))
        if collection is None:
            absentes.append(couche)
            continue
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            cheminement = _cheminement_depuis_feature(feature, couche)
            if cheminement is None:
                continue
            proprietes = feature.get("properties") or {}
            for id_cable in extraire_ids_cables_href(proprietes.get(CHAMP_CABLES_HREF)):
                index[id_cable].append(cheminement)
    return dict(index), crs, absentes


def assembler(cheminements: list[Cheminement]) -> list[BaseGeometry]:
    """Recolle les cheminements et retourne les troncons continus obtenus.

    `line_merge` ne recolle que des extremites **exactement** confondues ; le
    depart des troncons obtenus est donc le decoupage brut, que la tolerance
    corrigera ensuite.
    """
    assemblage = line_merge(union_all([cheminement.geometrie for cheminement in cheminements]))
    return list(getattr(assemblage, "geoms", [assemblage]))


def ecart_minimal(troncons: list[BaseGeometry]) -> float:
    """Distance la plus faible separant deux troncons de l'assemblage."""
    return min(a.distance(b) for a, b in itertools.combinations(troncons, 2))


def regrouper_a_la_tolerance(troncons: list[BaseGeometry]) -> int:
    """Compte les groupes de troncons que la tolerance de jonction reunit.

    `line_merge` exigeant des extremites exactement confondues, deux
    cheminements ecartes d'un arrondi millimetrique en ressortent separes. Ce
    regroupement rattrape cet ecart : deux troncons distants d'au plus
    `TOLERANCE_SUPERPOSITION` appartiennent a la meme voie.

    Parcours en O(n²) assume : un cable compte quelques troncons, jamais des
    milliers, et batir un index spatial couterait plus que la comparaison.
    """
    groupes: list[list[BaseGeometry]] = []
    for troncon in troncons:
        voisins = [g for g in groupes if any(troncon.dwithin(autre, TOLERANCE_SUPERPOSITION) for autre in g)]
        if not voisins:
            groupes.append([troncon])
            continue
        # Le troncon peut souder plusieurs groupes jusqu'ici separes.
        fusion = [troncon]
        for groupe in voisins:
            fusion.extend(groupe)
            groupes.remove(groupe)
        groupes.append(fusion)
    return len(groupes)


def detecter_anomalies(index: dict[str, list[Cheminement]]) -> list[dict[str, Any]]:
    """Detecte les cables dont les cheminements ne forment pas une voie continue.

    Une anomalie par cable : c'est sa voie qu'il faut reprendre, non chacun des
    trous pris a part. Le tri rend l'ordre des ecarts deterministe.
    """
    anomalies: list[dict[str, Any]] = []
    for id_cable in sorted(index):
        cheminements = index[id_cable]
        troncons = assembler(cheminements)
        if len(troncons) < SEUIL_TRONCONS or regrouper_a_la_tolerance(troncons) < SEUIL_TRONCONS:
            continue
        anomalies.append(
            {
                "type_anomalie": "cheminements_disjoints",
                "id_cable": id_cable,
                "nombre_cheminements": len(cheminements),
                "nombre_troncons": len(troncons),
                "ecart_minimal_m": round(ecart_minimal(troncons), 3),
                "couches": sorted({cheminement.couche for cheminement in cheminements}),
                "ids_cheminements": sorted(cheminement.id_entite for cheminement in cheminements),
                "geometrie": mapping(union_all([c.geometrie for c in cheminements])),
            }
        )
    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des voies de cable interrompues.

    La geometrie de chaque feature est l'assemblage des cheminements du cable :
    c'est la voie entiere qu'il faut examiner, le trou n'ayant lui-meme aucune
    geometrie a montrer.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "id_cable": a["id_cable"],
                "nombre_cheminements": a["nombre_cheminements"],
                "nombre_troncons": a["nombre_troncons"],
                "ecart_minimal_m": a["ecart_minimal_m"],
                "couches": ", ".join(a["couches"]),
                "ids_cheminements": ", ".join(a["ids_cheminements"]),
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-9401 et ecrit ses ecarts."""
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    index, crs, couches_absentes = indexer_cheminements_par_cable(repertoire_resolu)

    anomalies = detecter_anomalies(index)
    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, FICHIER_SORTIE))

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_cables_controles": len(index),
        "nombre_cheminements_indexes": sum(len(c) for c in index.values()),
        "tolerance_jonction_m": TOLERANCE_SUPERPOSITION,
        "couches_absentes": couches_absentes,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-9401."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-9401 : les cheminements portant un meme cable doivent "
            "former une voie continue, sans interruption. Tous types de cable, "
            "tous statuts, sur les cinq couches de cheminement."
        )
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les fichiers GeoJSON")
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
