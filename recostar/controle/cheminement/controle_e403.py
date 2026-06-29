"""
Controle E403 : coherence du mode d'implantation des cables electriques.

Verifie qu'un meme cable electrique n'est pas simultanement associe a un
cheminement aerien et a un cheminement souterrain. Un cable ne peut pas
etre a la fois aerien et physiquement enfoui dans le sol.

Cheminements aeriens :
    RPD_Aerien_Reco.geojson

Cheminements souterrains :
    RPD_Fourreau_Reco.geojson
    RPD_PleineTerre_Reco.geojson
    RPD_ProtectionMecanique_Reco.geojson

Regle metier :
    Tout cable electrique dont l'identifiant apparait a la fois dans les
    cables_href d'un cheminement aerien ET dans les cables_href d'un
    cheminement souterrain est signale comme anomalie.

L'algorithme construit deux index inverses (aerien, souterrain) en un seul
parcours des cheminements, puis detecte les cables presents dans les deux
index sans jamais produire de produit cartesien.

Usage CLI :
    python controle_e403.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_cable_electrique_implantation_incoherente.geojson
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils_geojson import ecrire_geojson, lire_geojson, obtenir_id_feature

# Fichier source des cables electriques
FICHIER_CABLE_ELECTRIQUE: str = "RPD_CableElectrique_Reco.geojson"

# Fichier de cheminement aerien
FICHIER_AERIEN: str = "RPD_Aerien_Reco.geojson"

# Fichiers de cheminements souterrains
FICHIERS_SOUTERRAIN: tuple[str, ...] = (
    "RPD_Fourreau_Reco.geojson",
    "RPD_PleineTerre_Reco.geojson",
    "RPD_ProtectionMecanique_Reco.geojson",
)

# Ensemble des fichiers de cheminement analyses (aerien + souterrains)
FICHIERS_CHEMINEMENT: tuple[str, ...] = (FICHIER_AERIEN,) + FICHIERS_SOUTERRAIN

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_cable_electrique_implantation_incoherente.geojson"

# Niveau de priorite affecte a toutes les anomalies
PRIORITE_ANOMALIE: str = "bloquant"

# Identifiant du type d'anomalie produit par ce controle
TYPE_ANOMALIE: str = "cable_electrique_implantation_incoherente"

# Nom du champ de relation dans les proprietes des cheminements
CHAMP_CABLES_HREF: str = "cables_href"


@dataclass(slots=True)
class EntiteCable:
    """Entite cable electrique avec son identifiant et sa geometrie de sortie."""

    id_entite: str
    geometrie: dict[str, Any] | None


@dataclass(slots=True)
class EntiteCheminement:
    """Entite de cheminement avec ses references cables et son fichier source."""

    id_entite: str | None
    fichier: str
    ids_cables: list[str]  # identifiants extraits du champ cables_href


@dataclass(slots=True)
class ReferenceCheminement:
    """Reference legere vers un cheminement : identifiant et fichier source."""

    id_cheminement: str | None
    fichier: str


# ---------------------------------------------------------------------------
# Parsing du champ cables_href
# ---------------------------------------------------------------------------


def _extraire_ids_cables_href(valeur: Any) -> list[str]:
    """Extrait les identifiants cables depuis le champ cables_href.

    Gere les formes presentes dans les donnees Recostar :
    - chaine unique  : "id<uuid>"
    - chaine multiple separee par virgules : "id<uuid1>,id<uuid2>"
    - liste          : ["id<uuid1>", "id<uuid2>"]
    - null ou absent : liste vide
    """
    if isinstance(valeur, str) and valeur:
        return [cid.strip() for cid in valeur.split(",") if cid.strip()]
    if isinstance(valeur, list):
        return [str(cid) for cid in valeur if cid is not None]
    return []


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_cables_electriques(
    repertoire: str,
) -> tuple[dict[str, EntiteCable], bool]:
    """Charge les entites cable electrique depuis le fichier source.

    Retourne ({id: EntiteCable}, fichier_absent). La geometrie est conservee
    car elle est utilisee comme geometrie de sortie dans les anomalies.
    Les entites sans identifiant sont ignorees silencieusement.
    """
    chemin = os.path.join(repertoire, FICHIER_CABLE_ELECTRIQUE)
    if not os.path.isfile(chemin):
        return {}, True
    collection = lire_geojson(chemin)
    if collection is None:
        return {}, False
    cables: dict[str, EntiteCable] = {}
    for feature in collection.get("features", []):
        id_entite = obtenir_id_feature(feature)
        if id_entite is not None:
            cables[id_entite] = EntiteCable(
                id_entite=id_entite,
                geometrie=feature.get("geometry"),
            )
    return cables, False


def _creer_entite_cheminement(
    feature: dict[str, Any],
    nom_fichier: str,
) -> EntiteCheminement:
    """Cree une EntiteCheminement depuis une feature GeoJSON."""
    props = feature.get("properties") or {}
    return EntiteCheminement(
        id_entite=obtenir_id_feature(feature),
        fichier=nom_fichier,
        ids_cables=_extraire_ids_cables_href(props.get(CHAMP_CABLES_HREF)),
    )


def charger_cheminements(
    repertoire: str,
) -> tuple[list[EntiteCheminement], list[str], dict[str, Any] | None]:
    """Charge les entites de cheminement des quatre fichiers analyses.

    Retourne (cheminements, fichiers_absents, crs). Les cheminements aeriens
    et souterrains sont charges ensemble ; la categorisation est effectuee a
    l'etape d'indexation par comparaison du nom de fichier a FICHIER_AERIEN.
    """
    cheminements: list[EntiteCheminement] = []
    fichiers_absents: list[str] = []
    crs: dict[str, Any] | None = None

    for nom_fichier in FICHIERS_CHEMINEMENT:
        chemin = os.path.join(repertoire, nom_fichier)
        if not os.path.isfile(chemin):
            fichiers_absents.append(nom_fichier)
            continue
        collection = lire_geojson(chemin)
        if collection is None:
            continue
        if crs is None:
            crs = collection.get("crs")
        for feature in collection.get("features", []):
            cheminements.append(_creer_entite_cheminement(feature, nom_fichier))

    return cheminements, fichiers_absents, crs


# ---------------------------------------------------------------------------
# Indexation des references
# ---------------------------------------------------------------------------


def indexer_references(
    cheminements: list[EntiteCheminement],
    ids_cables_electriques: set[str],
) -> tuple[
    dict[str, list[ReferenceCheminement]],
    dict[str, list[ReferenceCheminement]],
]:
    """Construit les index aerien et souterrain des references par cable electrique.

    Chaque cheminement est verse dans l'index aerien ou souterrain selon son
    fichier source. Seules les references vers des cables electriques connus
    sont indexees. Le test d'appartenance au set s'effectue en O(1).

    Retourne (refs_aerien, refs_souterrain).
    """
    refs_aerien: defaultdict[str, list[ReferenceCheminement]] = defaultdict(list)
    refs_souterrain: defaultdict[str, list[ReferenceCheminement]] = defaultdict(list)

    for cheminement in cheminements:
        index = refs_aerien if cheminement.fichier == FICHIER_AERIEN else refs_souterrain
        ref = ReferenceCheminement(
            id_cheminement=cheminement.id_entite,
            fichier=cheminement.fichier,
        )
        for id_cable in cheminement.ids_cables:
            if id_cable in ids_cables_electriques:
                index[id_cable].append(ref)

    return dict(refs_aerien), dict(refs_souterrain)


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies(
    cables_electriques: dict[str, EntiteCable],
    refs_aerien: dict[str, list[ReferenceCheminement]],
    refs_souterrain: dict[str, list[ReferenceCheminement]],
) -> list[dict[str, Any]]:
    """Detecte les cables electriques associes a des cheminements des deux categories.

    Un cable est signale si et seulement si son identifiant est present dans
    les deux index. Les cables references dans une seule categorie ne sont pas
    signales.
    """
    anomalies: list[dict[str, Any]] = []

    for id_cable, cable in cables_electriques.items():
        aeriens = refs_aerien.get(id_cable)
        souterrains = refs_souterrain.get(id_cable)
        if aeriens and souterrains:
            anomalies.append(
                {
                    "type_anomalie": TYPE_ANOMALIE,
                    "id_cable_electrique": id_cable,
                    "cheminements_aeriens": aeriens,
                    "cheminements_souterrains": souterrains,
                    "geometrie": cable.geometrie,
                }
            )

    return anomalies


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def _serialiser_refs(
    refs: list[ReferenceCheminement],
) -> tuple[str, str]:
    """Retourne (ids_csv, fichiers_csv) d'une liste de references en un seul parcours."""
    ids: list[str] = []
    fichiers: list[str] = []
    for ref in refs:
        ids.append(str(ref.id_cheminement) if ref.id_cheminement is not None else "")
        fichiers.append(ref.fichier)
    return ",".join(ids), ",".join(fichiers)


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des anomalies d'implantation incoherente.

    La geometrie de chaque feature est celle du cable electrique signale, ce
    qui permet la localisation directe dans QGIS. Les references aux cheminements
    impliques sont serialisees en CSV dans les proprietes pour une consultation
    rapide sans fichier annexe.
    """
    features: list[dict[str, Any]] = []
    for a in anomalies:
        ids_aeriens, fichiers_aeriens = _serialiser_refs(a["cheminements_aeriens"])
        ids_souterrains, fichiers_souterrains = _serialiser_refs(a["cheminements_souterrains"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "type_anomalie": a["type_anomalie"],
                    "priorite": PRIORITE_ANOMALIE,
                    "id_cable_electrique": a["id_cable_electrique"],
                    "nb_cheminements_aeriens": len(a["cheminements_aeriens"]),
                    "ids_cheminements_aeriens": ids_aeriens,
                    "fichiers_cheminements_aeriens": fichiers_aeriens,
                    "nb_cheminements_souterrains": len(a["cheminements_souterrains"]),
                    "ids_cheminements_souterrains": ids_souterrains,
                    "fichiers_cheminements_souterrains": fichiers_souterrains,
                },
                "geometry": a.get("geometrie"),
            }
        )
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


# ---------------------------------------------------------------------------
# Orchestration CLI
# ---------------------------------------------------------------------------


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle de coherence d'implantation des cables electriques.

    Charge les cables electriques et l'ensemble des cheminements, construit
    les index de references par categorie, detecte les anomalies et ecrit le
    fichier d'ecarts GeoJSON. Les fichiers absents sont listes dans le rapport
    sans bloquer l'execution.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    cables_electriques, cable_electrique_absent = charger_cables_electriques(repertoire_resolu)
    cheminements, fichiers_cheminement_absents, crs = charger_cheminements(repertoire_resolu)

    ids_cables_electriques = set(cables_electriques.keys())
    refs_aerien, refs_souterrain = indexer_references(cheminements, ids_cables_electriques)
    anomalies = detecter_anomalies(cables_electriques, refs_aerien, refs_souterrain)

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    ecrire_geojson(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_cables_electriques_analyses": len(cables_electriques),
        "nombre_cheminements_analyses": len(cheminements),
        "cable_electrique_absent": cable_electrique_absent,
        "fichiers_cheminement_absents": fichiers_cheminement_absents,
        "sortie": chemin_sortie,
    }


def main() -> None:
    """Point d'entree CLI du controle de coherence d'implantation des cables electriques."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E403 : verifie qu'aucun cable electrique "
            "(RPD_CableElectrique_Reco) n'est simultanement associe a un "
            "cheminement aerien (RPD_Aerien_Reco) et a un cheminement "
            "souterrain (RPD_Fourreau_Reco, RPD_PleineTerre_Reco, "
            "RPD_ProtectionMecanique_Reco) via le champ cables_href."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
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
