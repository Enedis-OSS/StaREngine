#!/usr/bin/env python3
"""
Point d'entrée du contrôle E014 : valeurs des champs (énumérations, CodeLists, formats) d'un fichier GML RecoStaR **V1.0**.

E014 est l'équivalent V1.0 du contrôle E114 (V1.1) : même moteur, même
format de rapport, mais appliqué au profil de version 1.0 (séquences dérivées du
XSD V1.0, énumération SRS plus courte et champ de type de
levé nommé `TypeLeve`). Le rapport produit
porte le `type_controle` « E014_VALEURS » et est écrit sous
`<nom_gml>_controle_e014.json`.

Aucune logique de contrôle n'est dupliquée ici : ce module se contente de figer
la version appliquée par le moteur de `controle_e114.py`. L'option
`--version` n'est donc pas offerte, le code du contrôle désignant déjà la
version.

Entrée  : Fichier GML RecoStaR V1.0 à contrôler
Sortie  : Fichier JSON `<nom_gml>_controle_e014.json`

Usage :
    python controle_e014.py <fichier.gml> [--output-dir <repertoire>]
"""

from controle_e114 import main as _main
from versions.v1_0 import PROFIL_V1_0

# Version figée appliquée par ce point d'entrée.
VERSION: str = PROFIL_V1_0.code


def main() -> None:
    """Exécute le contrôle E014 en imposant la version RecoStaR 1.0."""
    _main(version_imposee=VERSION)


if __name__ == "__main__":
    main()
