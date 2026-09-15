#!/usr/bin/env python3
"""
Controle E-4201 : la longueur du cable HTA est superieure a 500 m.

Un cable electrique en cours de mise en service dont le DomaineTension vaut
**HTA** ne doit pas depasser 500 metres. Les cables d'un autre domaine relevent
d'un autre code, ou d'aucun : le verificateur ne plafonne que le HTA et le HTA.

Perimetre : RPD_CableElectrique_Reco au Statut UnderCommissionning, hors cables
references par un cheminement aerien. Longueur mesuree en 3D.

Le moteur `detection_longueur_cable` mesure les deux
domaines en un parcours, ce controle ne retenant que le sien. L'autre controle
issu du meme moteur est **E-4200** pour le BT, dans `e4200.py`.

Le domaine de tension est le discriminant du code autant que du seuil : les deux
sont portes ensemble par `REGLES_PAR_DOMAINE`, et ne peuvent donc pas diverger.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e4201_longueur_hta.geojson

Usage CLI :
    python -m recostar.controle.cable.e4201 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_longueur_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_CABLE_ELECTRIQUE

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e4201_longueur_hta.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-4201"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"longueur_hta_excessive"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "longueur_hta_excessive": ("La longueur du câble HTA dépasse le maximum de 500 m admis pour son DomaineTension."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
    couche_source=FICHIER_CABLE_ELECTRIQUE,
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-4201 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle de longueur HTA."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-4201 : un RPD_CableElectrique_Reco au statut "
            "UnderCommissionning, non aerien et de DomaineTension HTA, ne doit pas "
            "depasser 500 metres (longueur 3D)."
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
