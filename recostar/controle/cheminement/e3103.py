"""
Controle E-3103 : Le cheminement n'a pas le nombre de câble attendu

Le moteur `detection_relations_cheminement` releve toutes les anomalies de son
domaine ; ce controle ne retient que celles de son code. Autres controles servis
par ce moteur : e3102, e9400.

Deux regles particulieres visent le seul fourreau depourvu de cable, la pose d'un
fourreau en attente de cablage etant une pratique courante :

- coupe-type **Provisoire** : le cheminement est conforme, aucun ecart n'est emis ;
- sinon : l'ecart est emis sous le type `fourreau_sans_cable`, de niveau **basse**
  (cf. codes_verificateur.DEROGATIONS_NIVEAU), et ne declasse donc pas la livraison.

Aucune des deux ne s'applique aux autres couches de cheminement, ni au fourreau
porteur de plusieurs cables : ces cas conservent le niveau du code E-3103.

Usage CLI :
    python -m recostar.controle.cheminement.e3103 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e3103_cardinalite_cheminement_cable.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.cheminement.detection_relations_cheminement import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e3103_cardinalite_cheminement_cable.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-3103"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cheminement_multi_cables",
        "cheminement_sans_cable",
        # Le fourreau sans cable releve du meme code mais porte son propre type :
        # c'est ce qui lui vaut un niveau basse la ou les autres restent forts
        # (cf. codes_verificateur.DEROGATIONS_NIVEAU).
        "fourreau_sans_cable",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cheminement_multi_cables": ("Le cheminement référence plusieurs câbles."),
    "cheminement_sans_cable": ("Le cheminement ne référence aucun câble."),
    "fourreau_sans_cable": ("Le fourreau ne référence aucun câble."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_cable", "id_cheminement"),
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-3103 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-3103."""
    parseur = argparse.ArgumentParser(description="Controle E-3103 : Le cheminement n'a pas le nombre de câble attendu")
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
