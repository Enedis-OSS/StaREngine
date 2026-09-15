"""
Controle E-6115 : Un câble électrique ne doit pas être lié à un nœud de télécommunication

Une RPD_Jonction_Reco dont le TypeJonction vaut Telecom ne doit pas declarer de
RPD_CableElectrique_Reco dans son cables_href. Elle melangerait le reseau
electrique et le reseau de telecommunication.

C'est le cas symetrique d'E-6113, qui interdit le cable de telecommunication sur
tout autre noeud. Les deux regles partagent le meme discriminant — la nature du
noeud — et sont portees ensemble par `classifier_separation_reseaux`.

Perimetre : la seule couche RPD_Jonction_Reco, au Statut UnderCommissionning ou
Functional, et de TypeJonction Telecom. Aucun autre noeud n'est un noeud de
telecommunication.

Le cable de terre sur une jonction de telecommunication releve d'E-6213, code
reaffecte a ce cas par arbitrage metier (cf. e6213.py). Avec E-6113, les trois
regles ferment la separation : une jonction de telecommunication n'admet que du
cable de telecommunication, et aucun autre noeud n'en admet.

La regle n'est evaluee que sur une reference qui **aboutit** et designe bien un
cable : une reference introuvable (E-9604) ou visant une entite d'une autre
nature (E-9607) releve des controles voisins.

Le moteur `detection_references_noeud_cable` releve
toutes les anomalies de son domaine, ce controle ne retenant que celles de son
code. Les autres controles servis par ce moteur : e6113, e6213, e9604, e9605,
e9606, e9607, e9608.

Usage CLI :
    python -m recostar.controle.conteneur.e6115 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e6115_cable_electrique_sur_noeud_telecom.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_references_noeud_cable import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e6115_cable_electrique_sur_noeud_telecom.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-6115"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent aux controles voisins.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "cable_electrique_sur_noeud_telecom",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "cable_electrique_sur_noeud_telecom": ("La jonction de télécommunication est liée à un câble électrique."),
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
    """Execute le controle E-6115 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-6115."""
    parseur = argparse.ArgumentParser(
        description="Controle E-6115 : un câble électrique ne doit pas être lié à un nœud de télécommunication"
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
