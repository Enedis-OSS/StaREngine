#!/usr/bin/env python3
"""
Controle E-3110 : l'objet n'a aucune geometrie supplementaire.

Un conteneur du perimetre doit porter une geometrie supplementaire exploitable :
une reference `geometriesupplementaire_href` qui aboutit, et dont la geometrie
est valide. La geometrie supplementaire est l'emprise reelle de l'ouvrage — le
contour du batiment, la cloture de l'enceinte, l'encombrement du coffret — la ou
la geometrie propre du conteneur n'est qu'un point de position.

Perimetre, et ce que la version y change
----------------------------------------
Trois conteneurs sont controles dans les deux versions du format :

    RPD_Coffret_Reco
    RPD_BatimentTechnique_Reco
    RPD_EnceinteCloturee_Reco

La **V1.1 y ajoute RPD_Support_Reco** : l'emprise du support y devient exigible,
ce que la V1.0 n'imposait pas. Le perimetre suit donc la version du jeu, detectee
par `version_recostar.determiner_version_depuis_repertoire` — la meme mecanique
qu'E-5201 et E-9200, qui ne lisent pas non plus les points leves comme source.
La version effectivement appliquee est reportee au rapport : un perimetre qui
depend d'une detection doit dire sur quoi il s'est arrete.

Trois ruptures, un seul code
----------------------------
La chaine `conteneur -> geometrie supplementaire -> geometrie` peut rompre en
trois endroits, et `classifier_chaine_conteneur` les distingue deja :

    geometrie_supplementaire_absente       `geometriesupplementaire_href` n'est pas renseigne
    geometrie_supplementaire_introuvable   la reference ne resout aucune entite
    geometrie_supplementaire_invalide      l'entite existe mais ne porte pas de geometrie exploitable

Les trois portent le meme code E-3110 : dans les trois cas l'objet n'a, de fait,
aucune geometrie supplementaire. Les distinguer par le type d'anomalie garde
toutefois la correction lisible — renseigner la reference, la corriger, ou
reparer la geometrie visee sont trois gestes differents. Elles sont exclusives
par construction, la classification s'arretant a la premiere rupture.

Ne pas confondre avec E-6106
----------------------------
E-6106 evalue la meme chaine, mais **depuis un noeud** qui en depend pour se
localiser : il ne dit rien d'un conteneur qu'aucun noeud n'habite. E-3110 porte
l'exigence sur le conteneur lui-meme, qu'il heberge ou non. Les deux peuvent donc
se prononcer sur une meme rupture, a deux mailles differentes — le noeud prive de
position d'un cote, le conteneur prive d'emprise de l'autre.

Le moteur de la chaine est partage : `fonctions_communes.localisation_conteneur`,
que parcourent aussi E-6105, E-6106, E-6204 et E-6109.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e3110_geometrie_supplementaire_absente.geojson

Usage CLI :
    python -m recostar.controle.conteneur.e3110 --repertoire <chemin> [--sortie <chemin>] \
                                                [--version {auto,1.0,1.1}]
"""

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import (
    ProfilEcarts,
    compter_ecarts_par_type,
    ecrire_geojson_si_anomalies,
    normaliser_geojson_ecarts,
)
from recostar.controle.fonctions_communes.localisation_conteneur import (
    Conteneur,
    classifier_chaine_conteneur,
    indexer_conteneurs_autorises,
    indexer_geometries_supplementaires,
)
from recostar.controle.fonctions_communes.modele_recostar import (
    COUCHE_BATIMENT,
    COUCHE_COFFRET,
    COUCHE_ENCEINTE_CLOTUREE,
    COUCHE_GEOM_SUPP,
    COUCHE_SUPPORT,
    EXTENSION_COUCHE,
)
from recostar.controle.fonctions_communes.version_recostar import (
    JETON_AUTO,
    VERSIONS_SUPPORTEES,
    determiner_version_depuis_repertoire,
)

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e3110_geometrie_supplementaire_absente.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-3110"

# Conteneurs controles dans les deux versions du format.
COUCHES_COMMUNES: tuple[str, ...] = (
    COUCHE_COFFRET,
    COUCHE_BATIMENT,
    COUCHE_ENCEINTE_CLOTUREE,
)

# Conteneur que la V1.1 ajoute au perimetre : l'emprise du support y devient
# exigible, ce que la V1.0 n'imposait pas.
COUCHES_V1_1: tuple[str, ...] = (COUCHE_SUPPORT,)

# Version a partir de laquelle le support entre dans le perimetre.
VERSION_AVEC_SUPPORT: str = "1.1"

# Types ecrits en clair, et non importes du moteur de chaine : le releve
# d'exhaustivite des codes lit ces cles par analyse syntaxique, et ne resout
# qu'une constante declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "geometrie_supplementaire_absente",
        "geometrie_supplementaire_introuvable",
        "geometrie_supplementaire_invalide",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "geometrie_supplementaire_absente": ("Le conteneur ne référence aucune géométrie supplémentaire."),
    "geometrie_supplementaire_introuvable": (
        "La géométrie supplémentaire référencée par le conteneur n'existe pas dans le jeu de données."
    ),
    "geometrie_supplementaire_invalide": (
        "La géométrie supplémentaire référencée par le conteneur ne porte pas de géométrie exploitable."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_conteneur",),
)


def couches_controlees(version: str) -> tuple[str, ...]:
    """Retourne les couches de conteneur soumises a l'exigence, selon la version."""
    if version == VERSION_AVEC_SUPPORT:
        return COUCHES_COMMUNES + COUCHES_V1_1
    return COUCHES_COMMUNES


def detecter_anomalies(
    conteneurs: Mapping[str, Conteneur],
    perimetre: frozenset[str],
    geometries_supplementaires: Mapping[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Detecte les conteneurs du perimetre prives de geometrie supplementaire.

    Une anomalie par conteneur, la classification s'arretant a la premiere
    rupture de la chaine : les trois motifs sont exclusifs.

    Le tri rend l'ordre des ecarts deterministe, un dictionnaire d'index ne
    garantissant pas celui du repertoire.
    """
    anomalies: list[dict[str, Any]] = []
    for identifiant in sorted(perimetre):
        conteneur = conteneurs[identifiant]
        motif = classifier_chaine_conteneur(conteneur, geometries_supplementaires)
        if motif is None:
            continue
        anomalies.append(
            {
                "type_anomalie": motif,
                "id_conteneur": identifiant,
                "couche_conteneur": conteneur.couche,
                "geometriesupplementaire_href": conteneur.href_geomsupp,
                "geometrie": conteneur.geometrie,
            }
        )
    return anomalies


def construire_geojson_ecarts(
    anomalies: list[dict[str, Any]],
    crs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit un FeatureCollection des conteneurs sans geometrie supplementaire.

    La geometrie de chaque feature est celle du conteneur en cause — son point
    de position, faute de l'emprise qui manque precisement. Un conteneur qui n'en
    porte pas non plus rend une feature sans geometrie : l'ecart reste lisible,
    et c'est le cumul de deux defauts.
    """
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "type_anomalie": a["type_anomalie"],
                "fichier_source": f"{a['couche_conteneur']}{EXTENSION_COUCHE}",
                "couche": a["couche_conteneur"],
                "id_conteneur": a["id_conteneur"],
                "geometriesupplementaire_href": a["geometriesupplementaire_href"],
            },
            "geometry": a["geometrie"],
        }
        for a in anomalies
    ]
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return normaliser_geojson_ecarts(resultat, PROFIL_ECARTS)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E-3110 et ecrit ses ecarts.

    Le perimetre depend de la version du jeu : la detection precede donc
    l'indexation, et la version retenue est reportee au rapport.
    """
    repertoire_resolu = str(Path(repertoire).resolve())
    if not os.path.isdir(repertoire_resolu):
        return {
            "succes": False,
            "erreur": f"Repertoire introuvable : {repertoire_resolu}",
        }

    dossier_sortie = str(Path(sortie).resolve()) if sortie is not None else repertoire_resolu
    version_appliquee = determiner_version_depuis_repertoire(repertoire_resolu, version)
    couches = couches_controlees(version_appliquee)

    conteneurs, perimetre, couches_absentes = indexer_conteneurs_autorises(repertoire_resolu, frozenset(couches))
    geometries_supplementaires = indexer_geometries_supplementaires(repertoire_resolu)
    # L'absence complete de la couche ferait sortir tous les conteneurs en
    # « introuvable » : le rapport le dit, pour que la cause reste lisible.
    chemin_geomsupp = os.path.join(repertoire_resolu, f"{COUCHE_GEOM_SUPP}{EXTENSION_COUCHE}")
    geomsupp_absente = not os.path.isfile(chemin_geomsupp)

    anomalies = detecter_anomalies(conteneurs, perimetre, geometries_supplementaires)
    geojson_ecarts = construire_geojson_ecarts(anomalies)

    os.makedirs(dossier_sortie, exist_ok=True)
    chemin_ecrit = ecrire_geojson_si_anomalies(geojson_ecarts, os.path.join(dossier_sortie, FICHIER_SORTIE))

    return {
        "succes": True,
        "nombre_anomalies": len(anomalies),
        "anomalies_par_type": compter_ecarts_par_type(geojson_ecarts),
        "version_controlee": version_appliquee,
        "couches_controlees": list(couches),
        "nombre_conteneurs_controles": len(perimetre),
        "nombre_geometries_supplementaires": len(geometries_supplementaires),
        "couches_absentes": couches_absentes,
        "fichier_geometrie_supplementaire_absent": geomsupp_absente,
        "sortie": chemin_ecrit,
    }


def main() -> None:
    """Point d'entree CLI du controle E-3110."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-3110 : un coffret, un batiment technique ou une enceinte "
            "cloturee doit porter une geometrie supplementaire exploitable. En "
            "RecoStaR V1.1, le support entre aussi dans le perimetre."
        )
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les fichiers GeoJSON")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=(JETON_AUTO, *VERSIONS_SUPPORTEES),
        default=JETON_AUTO,
        help="Version RecoStaR appliquee (defaut : detection automatique)",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
