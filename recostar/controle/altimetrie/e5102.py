"""
Controle E-5102 : Le sommet n'est pas associé à un PLOR / PTRL

Le moteur `detection_sommets_cables` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e5103.

Usage CLI :
    python -m recostar.controle.altimetrie.e5102 --repertoire <chemin> [--sortie <chemin>] [--version {auto,1.0,1.1}]

Sortie : ecarts_e5102_point_leve_absent.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.altimetrie.detection_sommets_cables import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.version_recostar import JETON_AUTO, VERSIONS_SUPPORTEES

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5102_point_leve_absent.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-5102"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "point_leve_absent",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "point_leve_absent": ("Le sommet de câble n'est superposé à aucun point levé."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    version: str = JETON_AUTO,
) -> dict[str, Any]:
    """Execute le controle E-5102 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
        version,
    )


def main() -> None:
    """Point d'entree CLI du controle E-5102."""
    parseur = argparse.ArgumentParser(description="Controle E-5102 : Le sommet n'est pas associé à un PLOR / PTRL")
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant les GeoJSON a analyser")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--version",
        choices=(JETON_AUTO, *VERSIONS_SUPPORTEES),
        default=JETON_AUTO,
        help="Version RecoStaR a controler. 'auto' (defaut) la deduit des proprietes GeoJSON.",
    )
    arguments = parseur.parse_args()
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, arguments.version)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
