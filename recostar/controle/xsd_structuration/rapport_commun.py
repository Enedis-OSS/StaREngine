#!/usr/bin/env python3
"""
Construction et écriture des rapports JSON communs aux contrôles E110 à E114.

Les cinq contrôles produisent un rapport de structure identique (fichier, date,
conformité, ventilation par sévérité, liste d'erreurs). Ce module centralise
cette structure : le format reste homogène entre contrôles et l'ajout d'un
champ ne se fait qu'à un seul endroit.

Chaque contrôle conserve la responsabilité de ce qui lui est propre : son
suffixe de fichier, son code de type de contrôle et ses éventuels champs
additionnels (E112 documente le XSD utilisé).
"""

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

# Niveau de criticité commun aux contrôles de structuration XSD.
NIVEAU_CONTROLE: str = "Forte"


class ErreurRapportable(Protocol):
    """Contrat minimal attendu d'une erreur pour figurer dans un rapport."""

    severite: str

    def vers_dict(self) -> dict[str, Any]:
        """Sérialise l'erreur en dictionnaire JSON."""
        ...


def compter_par_severite(erreurs: Sequence[ErreurRapportable]) -> dict[str, int]:
    """Compte les erreurs par sévérité.

    Les contrôles E110 à E114 sont mono-sévérité (ERREUR) : le compteur est donc
    soit vide, soit réduit à cette seule clé. Le comptage reste néanmoins
    générique pour rester valable si une sévérité complémentaire est introduite.
    """
    compteur: dict[str, int] = {}
    for erreur in erreurs:
        compteur[erreur.severite] = compteur.get(erreur.severite, 0) + 1
    return compteur


def resoudre_chemin_rapport(
    chemin_gml: Path,
    repertoire_sortie: Path | None,
    suffixe: str,
) -> Path:
    """Détermine le chemin du rapport JSON à partir du nom du fichier contrôlé.

    Le rapport est écrit à côté du fichier GML lorsque aucun répertoire de
    sortie n'est précisé.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    return (dossier / (chemin_gml.stem + suffixe)).resolve()


def construire_rapport(
    chemin_gml: Path,
    type_controle: str,
    erreurs: Sequence[ErreurRapportable],
    version: str,
    champs_specifiques: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit le dictionnaire de rapport à sérialiser en JSON.

    La conformité et le nombre d'erreurs sont dérivés de la ventilation par
    sévérité : un fichier est conforme si aucune erreur n'a été détectée.

    `champs_specifiques` est inséré juste après `fichier` pour les contrôles
    qui documentent une entrée supplémentaire (E112 et son XSD).
    """
    par_severite = compter_par_severite(erreurs)
    nb_erreurs = len(erreurs)

    rapport: dict[str, Any] = {"fichier": str(chemin_gml.resolve())}
    if champs_specifiques:
        rapport.update(champs_specifiques)
    rapport.update(
        {
            "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "niveau": NIVEAU_CONTROLE,
            "type_controle": type_controle,
            "version_controlee": version,
            "conformite": "CONFORME" if nb_erreurs == 0 else "NON_CONFORME",
            "nb_erreurs": nb_erreurs,
            "nb_par_severite": par_severite,
            "erreurs": [e.vers_dict() for e in erreurs],
        }
    )
    return rapport


def ecrire_rapport(chemin_sortie: Path, rapport: dict[str, Any]) -> Path:
    """Écrit le rapport au format JSON et retourne le chemin du fichier créé."""
    with open(chemin_sortie, "w", encoding="utf-8") as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)
    return chemin_sortie


def generer_rapport(
    chemin_gml: Path,
    type_controle: str,
    suffixe: str,
    erreurs: Sequence[ErreurRapportable],
    repertoire_sortie: Path | None,
    version: str,
    champs_specifiques: dict[str, Any] | None = None,
) -> Path:
    """Construit puis écrit le rapport d'un contrôle, et retourne son chemin."""
    chemin_sortie = resoudre_chemin_rapport(chemin_gml, repertoire_sortie, suffixe)
    rapport = construire_rapport(chemin_gml, type_controle, erreurs, version, champs_specifiques)
    return ecrire_rapport(chemin_sortie, rapport)
