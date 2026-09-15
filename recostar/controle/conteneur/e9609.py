#!/usr/bin/env python3
"""
Controle E-9609 : les raccordements declares et les coincidences geometriques divergent.

La jonction declare dans `cables_href` des cables que la geometrie ne confirme
pas, ou touche des cables qu'elle ne declare pas. Les deux sources de
raccordement se contredisent.

Un code local a star-engine
---------------------------
Le verificateur code le **compte** de cables raccordes — E-6201, E-6202, E-6203 —
mais ne nomme pas cette divergence. Elle reste pourtant un defaut a corriger : une
jonction peut etre au bon nombre de raccordements tout en declarant une reference
sans realite geometrique, que le compte seul laisse passer.

Ce constat n'est exclusif d'aucun autre. **E-9502** le complete en nommant
*lequel* des cables declares s'ecarte, quand il est electrique et en cours de mise
en service ; ce controle-ci porte le constat au niveau de la jonction, avec le
decompte des deux sources cote a cote.

Le moteur `detection_cables_jonction` releve en un
parcours toutes les anomalies de raccordement d'une jonction, ce controle ne retient
que celles de son code. Autres controles servis par ce moteur :
e6201, e6202, e6203, e6116 et `cable/e9502.py`.

Entree  : repertoire de GeoJSON RecoStaR
Sortie  : ecarts_e9609_raccordement_incoherent.geojson

Usage CLI :
    python -m recostar.controle.conteneur.e9609 --repertoire <chemin> [--sortie <chemin>]
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_cables_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9609_raccordement_incoherent.geojson"

# Identite du controle : le code d'erreur lui-meme.
CODE_CONTROLE: str = "E-9609"

# Types ecrits en clair, et non importes du moteur : le releve d'exhaustivite des
# codes lit ces cles par analyse syntaxique, et ne resout qu'une constante
# declaree dans le module meme.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "raccordement_incoherent",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "raccordement_incoherent": (
        "Les raccordements déclarés par cables_href et les raccordements géographiques divergent."
    ),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
)


def executer_controle_cli(repertoire: str, sortie: str | None = None) -> dict[str, Any]:
    """Execute le controle E-9609 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(repertoire, TYPES_RETENUS, PROFIL_ECARTS, FICHIER_SORTIE, sortie)


def main() -> None:
    """Point d'entree CLI du controle E-9609."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9609 : une jonction dont les raccordements declares et geometriques divergent."
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
