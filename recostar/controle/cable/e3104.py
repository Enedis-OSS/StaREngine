"""
Controle E-3104 : Les attributs du câble ne permettent pas de l'identifier

Le moteur `detection_coherence_cable` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e3302.

Usage CLI :
    python -m recostar.controle.cable.e3104 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e3104_typage_cable_incoherent.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cable.detection_coherence_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e3104_typage_cable_incoherent.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-3104"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "domaine_tension_fonction_incoherent",
        "fonction_cable_invalide",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "domaine_tension_fonction_incoherent": ("Le DomaineTension du câble est incohérent avec sa FonctionCable."),
    "fonction_cable_invalide": ("La FonctionCable du câble n'est pas une valeur autorisée."),
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
    """Execute le controle E-3104 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-3104."""
    parseur = argparse.ArgumentParser(
        description="Controle E-3104 : Les attributs du câble ne permettent pas de l'identifier"
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
