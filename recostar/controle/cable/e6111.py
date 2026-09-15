"""
Controle E-6111 : Les extrémités de câble ne sont pas jointes géométriquement aux nœuds liés

Le moteur `detection_raccordement_cable` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e6110, e9501.

Usage CLI :
    python -m recostar.controle.cable.e6111 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6111_extremite_non_raccordee.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_raccordement_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6111_extremite_non_raccordee.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6111"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "extremite_non_raccordee",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "extremite_non_raccordee": ("Une extrémité du câble n'est raccordée à aucun nœud du réseau."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable",),
    # Couche de l'entite en anomalie, que les ecarts ne nomment pas.
    couche_source="RPD_CableElectrique_Reco",
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-6111 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6111."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6111 : Les extrémités de câble ne sont pas jointes géométriquement aux nœuds liés"
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
