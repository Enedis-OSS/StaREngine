#!/usr/bin/env python3
"""
Controle E-6201 : jonction de type derivation avec moins de 3 cables raccordes.

Une RPD_Jonction_Reco au Statut UnderCommissionning dont le TypeJonction vaut
**Derivation** doit raccorder au moins trois cables : c'est ce qui fait d'elle une
derivation plutot qu'une jonction simple.

Un cable n'est compte comme raccorde que si la declaration (`cables_href`) et la
geometrie (coincidence avec une extremite du cable, a 1 mm pres) se confirment
mutuellement : compter les seules references reviendrait a croire une declaration
sans la verifier.

Le seuil et le code sont portes ensemble par `REGLES_PAR_TYPE` du moteur : le
TypeJonction est le discriminant de l'un comme de l'autre.

Le moteur `detection_cables_jonction` releve en un
parcours toutes les anomalies de raccordement d'une jonction, ce controle ne retient
que celles de son code. Autres controles servis par ce moteur :
e6202, e6203, e6116, e9609 et `cable/e9502.py`.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e6201_derivation_cables_insuffisants.geojson

Usage CLI :
    python -m recostar.controle.conteneur.e6201 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_cables_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6201_derivation_cables_insuffisants.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-6201"

# Types ecrits en clair, et non importes du moteur : le releve d'exhaustivite des
# codes lit ces cles par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "derivation_cables_insuffisants",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "derivation_cables_insuffisants": ("La jonction de type Derivation raccorde moins de 3 câbles."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-6201 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-6201."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6201 : une jonction de type Derivation raccordant moins de 3 cables."
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
