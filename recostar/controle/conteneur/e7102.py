"""
Controle E-7102 : Matériel non associé à un objet de type boite de jonction / dérivation

Un materiel doit etre porte par une RPD_Jonction_Reco, et celle-ci doit etre
d'un type susceptible d'en recevoir : Derivation ou Jonction. Un materiel
orphelin, ou porte par une ExtremiteReseau, releve de ce code.

Perimetre : **toutes** les entites RPD_Materiel_Reco, sans condition.
RPD_Materiel_Reco ne porte pas de champ Statut ; celui de la jonction n'est pas
un filtre mais une regle, portee par E-7103.

Le moteur `detection_rattachement_jonction` parcourt
la relation materiel -> jonction en sens inverse du catalogue de materiel, et
releve les trois
ecarts, ce controle ne retenant que ceux de son code. L'autre controle issu du
meme moteur : e7103.

Une anomalie est emise par lien fautif : un materiel indument reference par deux
jonctions porte deux anomalies, chacune etant a corriger pour elle-meme.

Usage CLI :
    python -m recostar.controle.conteneur.e7102 --repertoire <chemin> [--sortie <chemin>]

Sortie : ecarts_e7102_materiel_jonction_non_rattache.geojson
"""

import argparse
import json
import sys
from typing import Any

from recostar.controle.conteneur.detection_rattachement_jonction import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_MATERIEL

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e7102_materiel_jonction_non_rattache.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-7102"

# Types d'anomalie relevant de ce code. Le moteur en detecte d'autres, qui
# appartiennent au controle voisin.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "jonction_absente",
        "type_jonction_invalide",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "jonction_absente": ("Aucune jonction ne référence ce matériel."),
    "type_jonction_invalide": ("La jonction référençant ce matériel n'est pas une boîte de jonction / dérivation."),
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
    """Execute le controle E-7102 et ecrit ses ecarts.

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
    """Point d'entree CLI du controle E-7102."""
    parseur = argparse.ArgumentParser(
        description="Controle E-7102 : Matériel non associé à un objet de type boite de jonction / dérivation"
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
