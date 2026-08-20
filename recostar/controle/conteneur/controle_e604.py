"""
Controle E604 : types de noeuds autorises a se rattacher a un coffret.

Verifie que les entites RPD_Coffret_Reco ne sont referencees que par des noeuds
dont le type figure parmi les sept couches autorisees :

    RPD_CoupeCircuitAFusibles_Reco       RPD_PointDeComptage_Reco
    RPD_JeuBarres_Reco                   RPD_SupportModules_Reco
    RPD_ModuleRaccordement_Reco          RPD_Terre_Reco
    RPD_OuvrageCollectifBranchement_Reco

Sens de la relation : c'est le **noeud** qui porte la reference, via son champ
`conteneur_href`, et le coffret qui la subit. Le controle parcourt donc les
noeuds pour qualifier les coffrets, comme E601 parcourt les jonctions pour
qualifier les materiels.

Pourquoi toutes les couches du repertoire sont parcourues
--------------------------------------------------------
Un type de noeud non autorise est, par definition, un type qui ne figure pas
dans la liste. Restreindre l'analyse aux sept couches autorisees rendrait donc
le controle structurellement incapable de detecter quoi que ce soit. Toutes les
couches GeoJSON du repertoire sont parcourues (les fichiers d'ecarts en sont
exclus par `lister_fichiers_geojson`), et le nom du fichier fait foi pour le
type du noeud — c'est la convention de nommage RecoStaR, `RPD_<Type>_Reco`.
Meme parti que le controle E209, qui confronte les points de leve a toutes les
autres couches.

Seules les references **visant un coffret controle** sont examinees : les autres
`conteneur_href` designent un support ou un batiment technique et ne relevent
pas de cette regle. C'est ce qui permet a RPD_Jonction_Reco ou
RPD_PosteElectrique_Reco, porteurs du meme champ, de n'etre signales que s'ils
visent effectivement un coffret.

Perimetre : entites RPD_Coffret_Reco au Statut UnderCommissionning ou
Functional. Les coffrets d'un autre statut sont ignores, et les references qui
les visent avec eux.

Portee de la regle : la contrainte porte sur le **type** du noeud rattache, non
sur l'existence du rattachement. Un coffret que ne reference aucun noeud n'est
donc pas signale — a la difference d'E601, dont la regle exigeait explicitement
la presence du lien.

Regle de gestion : une anomalie est emise **par lien fautif** (coffret, noeud),
convention des controles de relation du projet (E500, E503, E507). Un coffret
rattache a deux noeuds interdits porte deux anomalies : chaque rattachement est
a corriger pour lui-meme.

Geometrie des ecarts : le Point du noeud fautif, qui porte la reference et donc
le defaut. Certains noeuds n'ont pas de geometrie propre — leur position est
deduite de leur conteneur (cf. RPD_ModuleRaccordement_Reco) : la geometrie du
coffret prend alors le relais, afin que l'ecart reste localisable.

Versions : coffret et noeuds ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Priorite : mineur.

Usage CLI :
    python controle_e604.py --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e604_coffret_noeud_non_autorise.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from controle_e600 import _charger_features
from utils_geojson import (
    EXTENSION_GEOJSON,
    ProfilEcarts,
    ecrire_geojson_si_anomalies,
    lire_geojson,
    lister_fichiers_geojson,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)

# Fichier source des entites controlees
FICHIER_COFFRET: str = "RPD_Coffret_Reco.geojson"

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e604_coffret_noeud_non_autorise.geojson"

# Identite du controle, utilisee pour normaliser les proprietes des ecarts.
CODE_CONTROLE: str = "E604"

# Type d'anomalie unique produit par ce controle
TYPE_NOEUD_NON_AUTORISE: str = "noeud_non_autorise"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_NOEUD_NON_AUTORISE: ("Le type de nœud rattaché au coffret ne fait pas partie des types autorisés."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_coffret", "id_noeud"),
)

# Niveau de priorite affecte a toutes les anomalies. Mineur : l'ecart est
# signale et compte dans le rapport, mais ne declasse pas la famille
# (cf. PRIORITES_DECLASSANTES dans synthese_controles).
PRIORITE_ANOMALIE: str = "mineur"

# Noms des champs dans les proprietes des features
CHAMP_STATUT: str = "Statut"
CHAMP_CONTENEUR_HREF: str = "conteneur_href"

# Statuts des coffrets a controler (frozenset -> appartenance en O(1))
STATUTS_CONTROLES: frozenset[str] = frozenset({"UnderCommissionning", "Functional"})

# Couches de noeuds autorisees a referencer un coffret. Le nom de la couche est
# celui du fichier GeoJSON, convention de nommage RecoStaR `RPD_<Type>_Reco`.
COUCHES_NOEUDS_AUTORISEES: frozenset[str] = frozenset(
    {
        "RPD_CoupeCircuitAFusibles_Reco",
        "RPD_JeuBarres_Reco",
        "RPD_ModuleRaccordement_Reco",
        "RPD_OuvrageCollectifBranchement_Reco",
        "RPD_PointDeComptage_Reco",
        "RPD_SupportModules_Reco",
        "RPD_Terre_Reco",
    }
)


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_coffrets_a_controler(
    repertoire: str,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, Any] | None, bool]:
    """Charge l'index {id_coffret: geometrie} des coffrets du perimetre.

    Retourne (index, crs, fichier_absent). Seuls les coffrets au Statut
    UnderCommissionning ou Functional sont indexes : le dictionnaire sert donc a
    la fois de filtre de perimetre (appartenance en O(1)) et d'acces a la
    geometrie de repli. Meme parti que l'index d'E507.
    """
    features, crs, absent = _charger_features(repertoire, FICHIER_COFFRET)
    index: dict[str, dict[str, Any] | None] = {}
    for feature in features:
        proprietes = feature.get("properties") or {}
        if proprietes.get(CHAMP_STATUT) not in STATUTS_CONTROLES:
            continue
        id_coffret = obtenir_id_feature(feature)
        if id_coffret is None:
            continue
        index[id_coffret] = feature.get("geometry")
    return index, crs, absent


def nom_couche(nom_fichier: str) -> str:
    """Derive le nom de la couche du nom de son fichier GeoJSON.

    « RPD_Terre_Reco.geojson » -> « RPD_Terre_Reco ». Le nom du fichier fait foi
    pour le type du noeud : c'est la convention de nommage RecoStaR, et la seule
    information de type disponible, les features ne portant pas leur classe.
    """
    return nom_fichier[: -len(EXTENSION_GEOJSON)] if nom_fichier.lower().endswith(EXTENSION_GEOJSON) else nom_fichier


def parcourir_couches(repertoire: str) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Parcourt les couches GeoJSON du repertoire, une seule chargee a la fois.

    Les fichiers d'ecarts sont exclus par `lister_fichiers_geojson`. Le
    generateur evite de detenir simultanement toutes les couches du jeu, dont le
    volume est sans rapport avec le nombre d'anomalies recherchees.
    """
    for nom_fichier in lister_fichiers_geojson(repertoire):
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        yield nom_couche(nom_fichier), collection.get("features", [])


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def couche_autorisee(couche: str) -> bool:
    """Indique si une couche est autorisee a referencer un coffret."""
    return couche in COUCHES_NOEUDS_AUTORISEES


def _reference_coffret(proprietes: Mapping[str, Any]) -> str | None:
    """Retourne l'identifiant de conteneur reference, ou None si absent."""
    valeur = proprietes.get(CHAMP_CONTENEUR_HREF)
    if valeur is None:
        return None
    reference = str(valeur).strip()
    return reference or None


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    coffrets: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les rattachements fautifs portes par une couche donnee.

    Une couche autorisee ne peut produire aucune anomalie : elle est ecartee
    sans etre parcourue. Sur les autres, seules les references visant un coffret
    du perimetre sont retenues — les `conteneur_href` designant un support ou un
    batiment technique ne relevent pas de cette regle.
    """
    if couche_autorisee(couche):
        return []
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        proprietes = feature.get("properties") or {}
        reference = _reference_coffret(proprietes)
        if reference is None or reference not in coffrets:
            continue
        anomalies.append(
            {
                "type_anomalie": TYPE_NOEUD_NON_AUTORISE,
                "id_coffret": reference,
                "id_noeud": obtenir_id_feature(feature),
                "couche_noeud": couche,
                # Le noeud porte la reference, donc le defaut ; sa geometrie
                # localise l'ecart. Certains noeuds n'en ont pas — leur position
                # est deduite du conteneur — le coffret prend alors le relais.
                "geometrie": feature.get("geometry") or coffrets[reference],
            }
        )
    return anomalies


def detecter_anomalies(
    couches: Iterable[tuple[str, list[dict[str, Any]]]],
    coffrets: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les coffrets rattaches a un noeud d'un type non autorise.

    Une anomalie est emise par lien fautif (coffret, noeud) : un coffret
    rattache a deux noeuds interdits porte deux anomalies, chaque rattachement
    etant a corriger pour lui-meme.
    """
    anomalies: list[dict[str, Any]] = []
    detecter = detecter_anomalies_couche  # alias local
    for couche, features in couches:
        anomalies.extend(detecter(couche, features, coffrets))
    return anomalies


def compter_liens_couche(
    features: list[dict[str, Any]],
    coffrets: Mapping[str, dict[str, Any] | None],
) -> int:
    """Compte les references d'une couche vers un coffret du perimetre.

    La couche n'entre pas dans le compte : `nombre_liens_controles` denombre
    **toutes** les references visant un coffret controle, qu'elles proviennent
    d'une couche autorisee ou non. Un lien conforme reste un lien controle.
    """
    return sum(
        1
        for feature in features
        if (reference := _reference_coffret(feature.get("properties") or {})) is not None and reference in coffrets
    )


def compter_coffrets_non_conformes(anomalies: list[dict[str, Any]]) -> int:
    """Compte les coffrets distincts portant au moins une anomalie."""
    return len({anomalie["id_coffret"] for anomalie in anomalies})


# ---------------------------------------------------------------------------
# Construction du GeoJSON de sortie
# ---------------------------------------------------------------------------


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des rattachements de noeud non autorises.

    Le crs est propage depuis le fichier des coffrets, entites controlees.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": FICHIER_COFFRET,
                "id_coffret": a["id_coffret"],
                "id_noeud": a["id_noeud"],
                "couche_noeud": a["couche_noeud"],
                "priorite": PRIORITE_ANOMALIE,
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
    """Execute le controle des noeuds rattaches aux coffrets en mode CLI.

    Indexe les coffrets du perimetre, parcourt toutes les couches du repertoire
    et ecrit le fichier d'ecarts GeoJSON. L'absence du fichier coffret est
    signalee sans bloquer : sans coffret controle, aucune reference ne peut etre
    fautive et le controle est sans objet.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    coffrets, crs, coffret_absent = charger_coffrets_a_controler(repertoire_resolu)

    anomalies: list[dict[str, Any]] = []
    couches_analysees = 0
    liens_controles = 0
    for couche, features in parcourir_couches(repertoire_resolu):
        couches_analysees += 1
        liens_controles += compter_liens_couche(features, coffrets)
        anomalies.extend(detecter_anomalies_couche(couche, features, coffrets))

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "priorite": PRIORITE_ANOMALIE,
        "nombre_anomalies": len(anomalies),
        "nombre_coffrets_controles": len(coffrets),
        "nombre_coffrets_non_conformes": compter_coffrets_non_conformes(anomalies),
        "nombre_couches_analysees": couches_analysees,
        "nombre_liens_controles": liens_controles,
        "fichier_coffret_absent": coffret_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle des noeuds rattaches aux coffrets."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E604 : les RPD_Coffret_Reco au statut UnderCommissionning "
            "ou Functional ne doivent etre references que par les sept types de "
            "noeuds autorises."
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
