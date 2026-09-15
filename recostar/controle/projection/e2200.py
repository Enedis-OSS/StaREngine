#!/usr/bin/env python3
"""
Controle E-2200 : le systeme de projection de l'objet n'est pas defini.

Le fichier GeoJSON portant l'entite ne declare aucun champ `crs`, ou en
declare un que le controle ne sait pas normaliser. La projection de l'objet
est alors inconnue : rien ne permet de la situer.

C'est une **declaration manquante**, non une projection fautive : le cas d'un
`crs` present mais different du SRS declare porte le code E-5105 et appelle
une reprojection, correction d'une tout autre nature. Les deux sont exclusifs
par construction, un `crs` etant soit absent, soit present.

Le moteur `detection_projection` confronte en un seul
parcours la projection de chaque fichier au SRS declare par `_metadata.json`, et
les fichiers entre eux. Ce controle ne retient que les anomalies de son code ;
les deux autres controles qu'il sert sont **E-5105 et E-9302**.

Entree  : repertoire de GeoJSON RecoStaR et son `_metadata.json`
Sortie  : ecarts_e2200_projection_non_definie.geojson

Usage CLI :
    python -m recostar.controle.projection.e2200 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.projection.detection_projection import executer_analyse

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e2200_projection_non_definie.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-2200"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"projection_non_definie"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "projection_non_definie": ("Le fichier portant l'entité ne déclare aucun système de projection exploitable."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_entite",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-2200 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-2200."""
    parseur = argparse.ArgumentParser(
        description="Controle E-2200 : une entite dont le fichier ne declare aucun systeme de projection."
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
