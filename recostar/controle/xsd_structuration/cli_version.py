#!/usr/bin/env python3
"""
Outils CLI partagés pour la sélection de version RecoStaR.

Mutualise, pour l'ensemble des contrôles E110 à E114 et le pipeline, l'ajout de
l'option `--version` et la résolution du profil de version à appliquer. Évite de
dupliquer cette logique (argument, détection automatique, repli) dans chaque
script.

Comportement de l'option `--version {auto,1.0,1.1}` :
- `auto` (défaut) : la version est déduite du fichier GML via `detection_version`.
  Si la détection échoue (en-tête absent ou non reconnu), on se replie sur la
  version par défaut en signalant le repli, afin que les contrôles s'exécutent
  malgré tout (en particulier E113 qui doit pouvoir diagnostiquer l'en-tête).
- `1.0` / `1.1` : la version est imposée, sans détection.
"""

import argparse
import sys
from pathlib import Path

from detection_version import JETON_AUTO, detecter_version
from versions import VERSION_DEFAUT, VERSIONS_SUPPORTEES, resoudre_profil
from versions.profil import ProfilVersion

# Valeurs acceptées par l'option --version : détection auto + versions connues.
_CHOIX_VERSION: tuple[str, ...] = (JETON_AUTO,) + VERSIONS_SUPPORTEES


def ajouter_argument_version(parseur: argparse.ArgumentParser) -> None:
    """Déclare l'option --version commune à tous les contrôles."""
    parseur.add_argument(
        "--version",
        choices=_CHOIX_VERSION,
        default=JETON_AUTO,
        help=(
            "Version RecoStaR à contrôler. 'auto' (défaut) la déduit du "
            "schemaLocation du fichier ; sinon imposer '1.0' ou '1.1'."
        ),
    )


def resoudre_profil_cli(chemin_gml: Path, version_demandee: str) -> ProfilVersion:
    """Résout le profil de version à appliquer pour un fichier GML.

    En mode `auto`, déduit la version du fichier puis se replie sur la version
    par défaut si la détection échoue (message sur stderr). En mode explicite,
    applique directement la version demandée.
    """
    if version_demandee != JETON_AUTO:
        return resoudre_profil(version_demandee)

    code = detecter_version(chemin_gml)
    if code is None:
        print(
            f"Version non détectée dans '{chemin_gml}' : repli sur la version "
            f"{VERSION_DEFAUT}. Précisez --version en cas de doute.",
            file=sys.stderr,
        )
        code = VERSION_DEFAUT
    return resoudre_profil(code)
