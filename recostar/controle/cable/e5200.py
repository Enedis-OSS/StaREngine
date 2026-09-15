"""
Controle E-5200 : Nombre de points levés insuffisant dans les courbes

Le moteur `detection_discretisation` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e5101.

Usage CLI :
    python -m recostar.controle.cable.e5200 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e5200_courbe_mal_discretisee.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_discretisation import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e5200_courbe_mal_discretisee.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-5200"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "courbe_mal_discretisee",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "courbe_mal_discretisee": ("La portion courbe du câble n'est pas suffisamment discrétisée."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-5200 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-5200."""
    parseur = argparse.ArgumentParser(
        description="Controle E-5200 : Nombre de points levés insuffisant dans les courbes"
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
