#!/usr/bin/env python3
"""
Controle E-9302 : les fichiers du jeu ne portent pas tous le meme systeme de projection.

Les GeoJSON du jeu declarent au moins deux `crs` distincts. Sont signalees les
entites des fichiers portant un crs **minoritaire** : ce sont eux qu'il faut
reprendre, non le jeu entier.

Ce constat compare les fichiers **entre eux**, la ou E-2200 et E-5105 comparent
chaque fichier au SRS declare. Il n'est donc exclusif ni de l'un ni de l'autre :
un jeu peut etre unanime tout en divergeant du declare (E-5105 seul), ou
panache tout en ayant des fichiers conformes.

Un code local plutot qu'E-0007
------------------------------
Le verificateur nomme ce defaut `E-0007`. L'arbitrage metier ecarte ce code au
profit d'un code de la serie locale : la regle s'evalue ici sur les GeoJSON
issus de la conversion, ou « le fichier » du verificateur est devenu un **jeu
de fichiers**, chacun portant son propre `crs`.

Le moteur `detection_projection` confronte en un seul
parcours la projection de chaque fichier au SRS declare par `_metadata.json`, et
les fichiers entre eux. Ce controle ne retient que les anomalies de son code ;
les deux autres controles qu'il sert sont **E-2200 et E-5105**.

Entree  : repertoire de GeoJSON RecoStaR et son `_metadata.json`
Sortie  : ecarts_e9302_projection_non_unique.geojson

Usage CLI :
    python -m recostar.controle.projection.e9302 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.projection.detection_projection import executer_analyse

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9302_projection_non_unique.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-9302"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"projection_non_unique"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "projection_non_unique": ("Le fichier portant l'entité déclare un système de projection minoritaire dans le jeu."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-9302 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-9302."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9302 : une entite dont le fichier porte un systeme de projection minoritaire dans le jeu."
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON et le _metadata.json",
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
