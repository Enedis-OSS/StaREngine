"""
Pipeline unifie de calcul et generation du rapport des longueurs de cables.

Enchaine automatiquement le calcul des longueurs geographiques et electriques
puis la generation du rapport PDF recapitulatif, via une seule commande CLI.

Usage : python pipeline.py --chemin-geojson <chemin> [--chemin-sortie <chemin>]
Sortie : fichier JSON et rapport PDF dans le repertoire de sortie.
"""

import argparse
import json
import os
import sys
from typing import Any

from calcul_longueur import _ecrire_fichier_sortie, executer_calcul
from rapport_longueur import generer_rapport_longueur


class ResultatPipeline:
    """Resultat de l'execution du pipeline complet."""

    __slots__ = ("succes", "erreur", "chemin_json", "chemin_pdf", "nb_cables")

    def __init__(self) -> None:
        self.succes: bool = False
        self.erreur: str = ""
        self.chemin_json: str = ""
        self.chemin_pdf: str = ""
        self.nb_cables: int = 0

    def vers_dict(self) -> dict[str, Any]:
        """Convertit le resultat en dictionnaire serialisable."""
        resultat: dict[str, Any] = {"succes": self.succes}
        if self.erreur:
            resultat["erreur"] = self.erreur
        if self.chemin_json:
            resultat["chemin_json"] = self.chemin_json
        if self.chemin_pdf:
            resultat["chemin_pdf"] = self.chemin_pdf
        resultat["nb_cables"] = self.nb_cables
        return resultat


def _valider_repertoire_entree(chemin_geojson: str) -> str | None:
    """Valide que le repertoire d'entree existe et retourne une erreur si invalide."""
    if not os.path.isdir(chemin_geojson):
        return f"Repertoire d'entree introuvable : {chemin_geojson}"
    return None


def executer_pipeline(
    chemin_geojson: str,
    chemin_sortie: str | None = None,
) -> ResultatPipeline:
    """Execute le pipeline complet : calcul des longueurs puis generation du rapport.

    Le repertoire chemin_geojson contient directement les fichiers GeoJSON.
    Le repertoire chemin_sortie recoit les resultats (JSON et PDF) dans un
    sous-dossier rapport/. S'il n'est pas specifie, chemin_geojson est utilise.
    """
    resultat = ResultatPipeline()

    erreur_entree = _valider_repertoire_entree(chemin_geojson)
    if erreur_entree is not None:
        resultat.erreur = erreur_entree
        return resultat

    # Repertoire de sortie par defaut : le repertoire d'entree
    sortie = chemin_sortie if chemin_sortie is not None else chemin_geojson

    # Etape 1 : calcul des longueurs
    donnees_calcul = executer_calcul(sortie, chemin_recolement=chemin_geojson)

    if not donnees_calcul.get("succes"):
        resultat.erreur = donnees_calcul.get("erreur", "Erreur lors du calcul")
        return resultat

    resultats_cables = donnees_calcul.get("resultats", [])
    resultat.nb_cables = len(resultats_cables)

    # Etape 2 : ecriture du fichier JSON
    resultat.chemin_json = _ecrire_fichier_sortie(sortie, donnees_calcul)

    # Etape 3 : generation du rapport PDF
    resultat.chemin_pdf = generer_rapport_longueur(sortie, resultats_cables)

    resultat.succes = True
    return resultat


def main() -> None:
    """Point d'entree du pipeline de calcul et rapport des longueurs."""
    parseur = argparse.ArgumentParser(
        description="Pipeline de calcul et rapport des longueurs de cables"
    )
    parseur.add_argument(
        "--chemin-geojson",
        required=True,
        help="Repertoire contenant les fichiers GeoJSON",
    )
    parseur.add_argument(
        "--chemin-sortie",
        required=False,
        default=None,
        help="Repertoire de sortie (defaut : repertoire d'entree)",
    )
    arguments = parseur.parse_args()

    resultat = executer_pipeline(arguments.chemin_geojson, arguments.chemin_sortie)

    if not resultat.succes:
        print(f"Erreur : {resultat.erreur}", file=sys.stderr)

    json.dump(resultat.vers_dict(), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
