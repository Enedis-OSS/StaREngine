"""
Controle E-9604 : La référence déclarée par cables_href ne correspond à aucune entité du jeu de données

Le moteur `detection_references_noeud_cable` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e9605, e9606, e9607, e9608.

Usage CLI :
    python -m recostar.controle.conteneur.e9604 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e9604_cable_reference_introuvable.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_references_noeud_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e9604_cable_reference_introuvable.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-9604"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_introuvable",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_introuvable": ("La référence déclarée par cables_href ne correspond à aucune entité du jeu de données."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_noeud",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-9604 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
    )


def main() -> None:
    """Point d'entree CLI du controle E-9604."""
    parseur = argparse.ArgumentParser(
        description="Controle E-9604 : La référence déclarée par cables_href ne correspond à aucune entité du jeu de données"
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
