"""
Controle E-7104 : Le couple Fabriquant / modèle ne fait pas parti du catalogue

Le moteur `detection_catalogue_materiel` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e9600.

Usage CLI :
    python -m recostar.controle.conteneur.e7104 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e7104_materiel_hors_catalogue.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_catalogue_materiel import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e7104_materiel_hors_catalogue.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-7104"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "couple_fabricant_modele_non_reference",
        "domaine_tension_hors_catalogue",
        "fabricant_non_reference",
        "modele_non_reference",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "couple_fabricant_modele_non_reference": ("L'association Fabricant / Modèle n'est pas référencée au catalogue."),
    "domaine_tension_hors_catalogue": (
        "Le DomaineTension de la jonction n'est couvert par aucune entrée du catalogue."
    ),
    "fabricant_non_reference": ("Le Fabricant du matériel n'est pas référencé au catalogue."),
    "modele_non_reference": ("Le Modèle du matériel n'est pas référencé au catalogue pour ce domaine."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction", "id_materiel"),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-7104 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-7104."""
    parseur = argparse.ArgumentParser(
        description="Controle E-7104 : Le couple Fabriquant / modèle ne fait pas parti du catalogue"
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
