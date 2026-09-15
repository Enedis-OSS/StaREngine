#!/usr/bin/env python3
"""
Controle E-4200 : la longueur du cable BT est superieure a 250 m.

Un cable electrique en cours de mise en service dont le DomaineTension vaut
**BT** ne doit pas depasser 250 metres. Les cables d'un autre domaine relevent
d'un autre code, ou d'aucun : le verificateur ne plafonne que le BT et le HTA.

Perimetre : RPD_CableElectrique_Reco au Statut UnderCommissionning, hors cables
references par un cheminement aerien. Longueur mesuree en 3D.

Le moteur `detection_longueur_cable` mesure les deux
domaines en un parcours, ce controle ne retenant que le sien. L'autre controle
issu du meme moteur est **E-4201** pour le HTA, dans `e4201.py`.

Le domaine de tension est le discriminant du code autant que du seuil : les deux
sont portes ensemble par `REGLES_PAR_DOMAINE`, et ne peuvent donc pas diverger.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e4200_longueur_bt.geojson

Usage CLI :
    python -m recostar.controle.cable.e4200 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_longueur_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_CABLE_ELECTRIQUE

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e4200_longueur_bt.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-4200"

# Type ecrit en clair, et non importe du moteur : le releve d'exhaustivite des
# codes lit cette cle par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset({"longueur_bt_excessive"})

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "longueur_bt_excessive": ("La longueur du câble BT dépasse le maximum de 250 m admis pour son DomaineTension."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
    couche_source=FICHIER_CABLE_ELECTRIQUE,
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-4200 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle de longueur BT."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle E-4200 : un RPD_CableElectrique_Reco au statut "
            "UnderCommissionning, non aerien et de DomaineTension BT, ne doit pas "
            "depasser 250 metres (longueur 3D)."
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
