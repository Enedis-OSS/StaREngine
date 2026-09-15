"""
Controle E-7103 : Matériel associé à un objet de type boite de jonction / dérivation qui n'est pas au statut UnderCommissionning

La jonction portant le materiel est bien une boite — Derivation ou Jonction —
mais son Statut ne vaut pas UnderCommissionning. Le materiel est rattache a un
ouvrage qui n'est pas en cours de pose.

C'est le complement exact d'E-7102, qui ne juge que le **type** de la jonction :
sa docstring relevait elle-meme qu'un materiel porte par une jonction
Decommissioned y restait conforme. Les deux regles sont evaluees en cascade, un
type inadapte court-circuitant celle du statut.

Perimetre : **toutes** les entites RPD_Materiel_Reco, sans condition.
RPD_Materiel_Reco ne porte pas de champ Statut ; celui de la jonction n'est pas
un filtre mais une regle, portee par E-7103.

Le moteur `detection_rattachement_jonction` parcourt
la relation materiel -> jonction en sens inverse du catalogue de materiel, et
releve les trois
ecarts, ce controle ne retenant que ceux de son code. L'autre controle issu du
meme moteur : e7102.

Une anomalie est emise par lien fautif : un materiel indument reference par deux
jonctions porte deux anomalies, chacune etant a corriger pour elle-meme.

Usage CLI :
    python -m recostar.controle.conteneur.e7103 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e7103_materiel_jonction_hors_statut.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_rattachement_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_MATERIEL

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e7103_materiel_jonction_hors_statut.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-7103"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent au controle voisin.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "statut_jonction_invalide",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "statut_jonction_invalide": ("La jonction portant ce matériel n'est pas au statut UnderCommissionning."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    # Repli sur la jonction : un materiel sans identifiant laisse l'ecart
    # identifiable par l'ouvrage qui le porte.
    champs_id=("id_materiel", "id_jonction"),
    couche_source=FICHIER_MATERIEL,
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
) -> dict[str, Any]:
    """Execute le controle E-7103 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-7103."""
    parseur = argparse.ArgumentParser(
        description="Controle E-7103 : Matériel associé à un objet de type boite de jonction / dérivation qui n'est pas au statut UnderCommissionning"
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
