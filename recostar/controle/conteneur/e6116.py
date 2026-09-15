#!/usr/bin/env python3
"""
Controle E-6116 : jonction de telecommunication sans cable de telecommunication.

Une RPD_Jonction_Reco au Statut UnderCommissionning dont le TypeJonction vaut
**Telecom** doit declarer, dans son `cables_href`, au moins une reference
resolvant un RPD_CableTelecommunication_Reco.

Contrainte de **nature**, non de compte : aucun nombre minimal de cables n'est
impose a ce type par ailleurs. L'exigence porte sur les seules references
declarees, leur confirmation geometrique relevant du constat de coherence
(E-9609).

La regle symetrique — un cable de telecommunication ne se raccorde qu'a une
jonction Telecom — porte le code E-6113 et vit dans `e6113.py`.

Le moteur `detection_cables_jonction` releve en un
parcours toutes les anomalies de raccordement d'une jonction, ce controle ne retient
que celles de son code. Autres controles servis par ce moteur :
e6201, e6202, e6203, e9609 et `cable/e9502.py`.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e6116_jonction_telecom_sans_cable.geojson

Usage CLI :
    python -m recostar.controle.conteneur.e6116 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_cables_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6116_jonction_telecom_sans_cable.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-6116"

# Types ecrits en clair, et non importes du moteur : le releve d'exhaustivite des
# codes lit ces cles par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_telecommunication_absent",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_telecommunication_absent": (
        "La jonction Telecom ne référence aucun câble de télécommunication dans cables_href."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-6116 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-6116."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6116 : une jonction Telecom ne referencant aucun cable de telecommunication."
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
