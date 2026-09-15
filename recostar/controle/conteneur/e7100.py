"""
Controle E-7100 : Boite de jonction / dérivation sans matériel associé

Une boite du perimetre que ne vise aucune relation `Ouvrage_Materiel` n'abrite
aucun materiel declare : le recolement ne dit pas ce qu'elle contient.

Perimetre : les RPD_Jonction_Reco dont le TypeJonction designe une boite —
Derivation ou Jonction — et dont le Statut vaut UnderCommissionning. Meme
perimetre que le catalogue de materiel et E-7102.

Le moteur `detection_rattachement_materiel` compte
les relations visant chaque boite et releve les deux sens d'ecart, ce controle ne
retenant que le sien. Les deux sont exclusifs : une boite a zero materiel, un —
le cas conforme — ou plusieurs. L'autre controle issu du meme moteur : e7101.

Le moteur lit le **GML source** ; sans lui, le controle se declare sans objet
plutot que de rendre un faux conforme.

Usage CLI :
    python -m recostar.controle.conteneur.e7100 --repertoire <chemin> [--sortie <chemin>]
                                               [--gml <fichier.gml>]

Sortie : ecarts_e7100_boite_sans_materiel.geojson
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from recostar.controle.conteneur.detection_rattachement_materiel import executer_analyse
from recostar.controle.fonctions_communes.geojson import ProfilEcarts
from recostar.controle.fonctions_communes.modele_recostar import FICHIER_JONCTION

# Nom du fichier GeoJSON de sortie
FICHIER_SORTIE: str = "ecarts_e7100_boite_sans_materiel.geojson"

# Identite du controle : le code du verificateur lui-meme.
CODE_CONTROLE: str = "E-7100"

# Types d'anomalie relevant de ce code. Le moteur en detecte un autre, qui
# appartient au controle voisin.
TYPES_RETENUS: frozenset[str] = frozenset(
    {
        "boite_sans_materiel",
    }
)

DESCRIPTIONS_ANOMALIES: dict[str, str] = {
    "boite_sans_materiel": ("La boîte de jonction / dérivation n'est associée à aucun matériel."),
}

PROFIL_ECARTS: ProfilEcarts = ProfilEcarts(
    code_controle=CODE_CONTROLE,
    descriptions=DESCRIPTIONS_ANOMALIES,
    champs_id=("id_jonction",),
    couche_source=FICHIER_JONCTION,
)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    chemin_gml: Path | None = None,
) -> dict[str, Any]:
    """Execute le controle E-7100 et ecrit ses ecarts.

    Delegue la detection au moteur partage, qui n'emet ici que les anomalies
    de ce code.
    """
    return executer_analyse(
        repertoire,
        TYPES_RETENUS,
        PROFIL_ECARTS,
        FICHIER_SORTIE,
        sortie,
        chemin_gml,
    )


def main() -> None:
    """Point d'entree CLI du controle E-7100."""
    parseur = argparse.ArgumentParser(
        description="Controle E-7100 : Boite de jonction / dérivation sans matériel associé"
    )
    parseur.add_argument("--repertoire", required=True, help="Repertoire contenant le GML a analyser")
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--gml",
        default=None,
        help="Fichier GML source (defaut : le GML present dans le repertoire, s'il est unique)",
    )
    arguments = parseur.parse_args()
    chemin_gml = Path(arguments.gml) if arguments.gml is not None else None
    resultat = executer_controle_cli(arguments.repertoire, arguments.sortie, chemin_gml)
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
