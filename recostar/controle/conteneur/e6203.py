#!/usr/bin/env python3
"""
Controle E-6203 : extremite reseau non liee a un cable et un seul.

Une RPD_Jonction_Reco au Statut UnderCommissionning dont le TypeJonction vaut
**ExtremiteReseau** raccorde exactement un cable. C'est le seul type borne des
deux cotes, et la fiche du verificateur enonce la regle dans les deux sens : ce
controle porte donc **deux types d'anomalie** sous un seul code — aucun cable, ou
plusieurs.

Un cable n'est compte comme raccorde que si la declaration (`cables_href`) et la
geometrie (coincidence avec une extremite du cable, a 1 mm pres) se confirment
mutuellement : compter les seules references reviendrait a croire une declaration
sans la verifier.

Le moteur `detection_cables_jonction` releve en un
parcours toutes les anomalies de raccordement d'une jonction, ce controle ne retient
que celles de son code. Autres controles servis par ce moteur :
e6201, e6202, e6116, e9609 et `cable/e9502.py`.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e6203_extremite_reseau_cardinalite.geojson

Usage CLI :
    python -m recostar.controle.conteneur.e6203 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_cables_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6203_extremite_reseau_cardinalite.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-6203"

# Types ecrits en clair, et non importes du moteur : le releve d'exhaustivite des
# codes lit ces cles par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "extremite_reseau_sans_cable",
        "extremite_reseau_cables_multiples",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "extremite_reseau_sans_cable": ("L'extrémité réseau ne raccorde aucun câble."),
    "extremite_reseau_cables_multiples": (
        "L'extrémité réseau raccorde plusieurs câbles alors qu'elle n'en admet qu'un."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-6203 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-6203."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6203 : une extremite reseau qui ne raccorde pas exactement un cable."
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
