"""
Controle E-6107 : Nœud réseau manquant. Coffret n'a pas de nœud réseau conforme identifié

Le moteur `detection_composition_coffret` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6208.

Usage CLI :
    python -m recostar.controle.conteneur.e6107 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6107_coffret_sans_noeud_autorise.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_composition_coffret import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6107_coffret_sans_noeud_autorise.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6107"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "coffret_sans_noeud_autorise",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "coffret_sans_noeud_autorise": ("Le coffret n'est rattaché à aucun nœud réseau autorisé dans un coffret."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_coffret",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6107 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6107."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6107 : Nœud réseau manquant. Coffret n'a pas de nœud réseau conforme identifié"
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
