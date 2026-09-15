"""
Controle E-6114 : Un coffret de télécommunication ne doit pas être lié à un nœud électrique

Un RPD_Coffret_Reco dont le TypeCoffret vaut Telecom ne doit heberger aucun
noeud du reseau electrique. Sont vises les sept types de noeuds que le modele
admet dans un coffret :

    RPD_CoupeCircuitAFusibles_Reco       RPD_PointDeComptage_Reco
    RPD_JeuBarres_Reco                   RPD_SupportModules_Reco
    RPD_ModuleRaccordement_Reco          RPD_Terre_Reco
    RPD_OuvrageCollectifBranchement_Reco

Chacun appartient au reseau electrique : dans un coffret de telecommunication,
il melange les deux reseaux.

Sens de la relation : c'est le **noeud** qui porte la reference, via son champ
`conteneur_href`, et le coffret qui la subit. Le controle parcourt donc les
noeuds pour qualifier les coffrets, comme E-6108 et E-6107.

Perimetre de couches, et sa frontiere avec E-6108
------------------------------------------------
Les sept couches sont celles que le modele autorise dans un coffret
(`COUCHES_NOEUDS_COFFRET`), la liste meme que lit E-6108. Les deux controles s'y
partagent le travail sans se recouvrir :

  - E-6108 signale les couches **absentes** de la liste, quel que soit le type du
    coffret — une RPD_Jonction_Reco dans un coffret, par exemple ;
  - E-6114 signale les couches **presentes** dans la liste lorsqu'elles visent un
    coffret de telecommunication.

Aucun lien ne peut donc relever des deux, et ce controle n'a rien a dire des
couches qu'E-6108 rejette deja : les lire ici produirait une seconde anomalie
pour une meme cause.

Seules les references **visant un coffret de telecommunication controle** sont
examinees : les autres `conteneur_href` designent un coffret d'un autre type, un
support ou un batiment technique, et ne relevent pas de cette regle.

Perimetre d'entites : RPD_Coffret_Reco au Statut UnderCommissionning ou
Functional dont le TypeCoffret vaut Telecom. Les coffrets d'un autre statut ou
d'un autre type sont ignores, et les references qui les visent avec eux.

Portee de la regle : la contrainte porte sur le **type** du noeud rattache, non
sur l'existence du rattachement. Un coffret de telecommunication que ne
reference aucun noeud n'est donc pas signale. Meme parti qu'E-6108.

Le predicat du coffret de telecommunication est partage avec les trois autres
codes du bloc de separation (`fonctions_communes.separation_reseaux`).

Regle de gestion : une anomalie est emise **par lien fautif** (coffret, noeud),
convention des controles de relation du projet (E-9500, E-6103, E-9502, E-6108).
Un
coffret rattache a deux noeuds electriques porte deux anomalies : chaque
rattachement est a corriger pour lui-meme.

Geometrie des ecarts : le Point du noeud fautif, qui porte la reference et donc
le defaut. Les noeuds sans geometrie propre tiennent leur position de leur
conteneur : la geometrie du coffret prend alors le relais, afin que l'ecart
reste localisable.

Versions : coffret et noeuds ont une structure identique en RecoStaR V1.0 et
V1.1 ; le controle est agnostique de version.

Usage CLI :
    python -m recostar.controle.conteneur.e6114 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6114_coffret_telecom_noeud_electrique.geojson
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.chargement import charger_features
from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
    obtenir_id_feature,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    CHAMP_CONTENEUR_HREF,
    CHAMP_STATUT,
    COUCHES_NOEUDS_COFFRET,
    EXTENSION_COUCHE,
    FICHIER_COFFRET,
    STATUTS_EN_SERVICE,
)
from recostar.controle.fonctions_communes.proprietes import reference_href
from recostar.controle.fonctions_communes.separation_reseaux import est_coffret_telecom

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6114_coffret_telecom_noeud_electrique.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6114"

# Type d'anomalie unique produit par ce controle
TYPE_NOEUD_ELECTRIQUE: str = "noeud_electrique_sur_coffret_telecom"

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    TYPE_NOEUD_ELECTRIQUE: ("Le coffret de télécommunication est lié à un nœud du réseau électrique."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_coffret", "id_noeud"),
)

# Statuts des coffrets a controler (frozenset -> appartenance en O(1))
STATUTS_CONTROLES: frozenset[str] = STATUTS_EN_SERVICE

# Couches de noeuds electriques controlees : celles que le modele admet dans un
# coffret. Tuple : l'ordre fixe le parcours des fichiers.
COUCHES_CIBLES: tuple[str, ...] = tuple(sorted(COUCHES_NOEUDS_COFFRET))


# ---------------------------------------------------------------------------
# Chargement des entites
# ---------------------------------------------------------------------------


def charger_coffrets_telecom(
    repertoire: str,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, Any] | None, bool]:
    """Charge l'index {id_coffret: geometrie} des coffrets de telecommunication.

    Retourne (index, crs, fichier_absent). Deux conditions cumulatives : un
    Statut UnderCommissionning ou Functional, et un TypeCoffret valant Telecom.
    Le dictionnaire sert donc a la fois de filtre de perimetre (appartenance en
    O(1)) et d'acces a la geometrie de repli. Meme parti que l'index d'E-6108.
    """
    features, crs, absent = charger_features(repertoire, FICHIER_COFFRET)
    index: dict[str, dict[str, Any] | None] = {}
    for feature in features:
        proprietes = feature.get("properties") or {}
        if proprietes.get(CHAMP_STATUT) not in STATUTS_CONTROLES:
            continue
        if not est_coffret_telecom(proprietes):
            continue
        id_coffret = obtenir_id_feature(feature)
        if id_coffret is None:
            continue
        index[id_coffret] = feature.get("geometry")
    return index, crs, absent


# ---------------------------------------------------------------------------
# Detection des anomalies
# ---------------------------------------------------------------------------


def detecter_anomalies_couche(
    couche: str,
    features: list[dict[str, Any]],
    coffrets: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les rattachements fautifs portes par une couche donnee.

    La nature du noeud se lit sur sa seule couche : les sept couches controlees
    appartiennent toutes au reseau electrique, sans exception d'entite. Il n'y a
    donc aucun attribut a lire — seule la cible de la reference decide.

    Une couche hors perimetre ne peut produire aucune anomalie : elle est
    ecartee sans etre parcourue.
    """
    if couche not in COUCHES_NOEUDS_COFFRET:
        return []
    anomalies: list[dict[str, Any]] = []
    for feature in features:
        proprietes = feature.get("properties") or {}
        reference = reference_href(proprietes, CHAMP_CONTENEUR_HREF)
        if reference is None or reference not in coffrets:
            continue
        anomalies.append(
            {
                "type_anomalie": TYPE_NOEUD_ELECTRIQUE,
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


def compter_liens_couche(
    features: list[dict[str, Any]],
    coffrets: Mapping[str, dict[str, Any] | None],
) -> int:
    """Compte les references d'une couche vers un coffret du perimetre.

    Le compte porte sur **toutes** les references visant un coffret controle,
    conformes comprises : un lien conforme reste un lien controle.
    """
    return sum(
        1
        for feature in features
        if (reference := reference_href(feature.get("properties") or {}, CHAMP_CONTENEUR_HREF)) is not None
        and reference in coffrets
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
    """Construit un FeatureCollection des rattachements fautifs.

    `couche_noeud` nomme le type du noeud en cause : c'est l'information que
    l'operateur doit corriger, et elle serait sinon perdue, tous les types
    partageant le meme fichier d'ecarts.
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
    """Execute le controle E-6114 et ecrit ses ecarts.

    Indexe les coffrets de telecommunication du perimetre, parcourt les sept
    couches de noeuds electriques et ecrit le fichier d'ecarts GeoJSON. Les
    couches absentes sont remontees au rapport sans bloquer : un jeu ne contient
    pas necessairement tous les types de noeuds. L'absence du fichier coffret
    l'est aussi : sans coffret controle, aucune reference ne peut etre fautive
    et le controle est sans objet.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu

    coffrets, crs, coffret_absent = charger_coffrets_telecom(repertoire_resolu)

    anomalies: list[dict[str, Any]] = []
    couches_absentes: list[str] = []
    liens_controles = 0
    for couche in COUCHES_CIBLES:
        features, _, absente = charger_features(repertoire_resolu, f"{couche}{EXTENSION_COUCHE}")
        if absente:
            couches_absentes.append(couche)
            continue
        liens_controles += compter_liens_couche(features, coffrets)
        anomalies.extend(detecter_anomalies_couche(couche, features, coffrets))

    geojson_ecarts = construire_geojson_ecarts(anomalies, crs)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_sortie = os.path.join(dossier_sortie, FICHIER_SORTIE)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, chemin_sortie)

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "nombre_coffrets_controles": len(coffrets),
        "nombre_coffrets_non_conformes": compter_coffrets_non_conformes(anomalies),
        "couches_absentes": couches_absentes,
        "nombre_liens_controles": liens_controles,
        "fichier_coffret_absent": coffret_absent,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-6114."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-6114 : un coffret de télécommunication ne doit héberger que des jonctions de télécommunication."
        )
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
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
