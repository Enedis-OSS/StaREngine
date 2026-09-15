#!/usr/bin/env python3
"""
Contrôle de l'exploitabilité du document GML RecoStaR.

Le moteur est version-agnostique : il applique le `ProfilVersion` qui lui est
fourni. Le code du contrôle suit la version contrôlée — **E0118** en V1.1,
**E0018** en V1.0 (point d'entrée dédié `e0018.py`).

Deux codes du vérificateur y sont rendus :

    E-0001   le fichier GML n'a pas pu être analysé
    E-0004   il s'analyse, mais ne contient aucune donnée

La règle et son raisonnement vivent dans `regles_document`. Ce module ne fait
que lire le fichier et rendre le rapport.

Le seul contrôle qui ne défaille pas sur un GML cassé
-----------------------------------------------------
Les neuf autres rangs laissent l'erreur d'analyse remonter : le pipeline isole
alors leur échec, et le rapport global liste neuf contrôles en échec sans dire
pourquoi. Celui-ci rattrape l'erreur et la nomme. Les échecs voisins deviennent
la conséquence lisible d'une cause énoncée.

C'est aussi pourquoi il n'est pas exécuté en premier : son rang ne change rien,
puisqu'il ne dépend d'aucun autre et qu'aucun autre ne dépend de lui.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON décrivant l'exploitabilité du document

Usage :
    python -m recostar.controle.xsd_structuration.e0118 <fichier.gml> [--output-dir <repertoire>] \
                                                        [--version {auto,1.0,1.1}]
"""

import json
from datetime import datetime
from pathlib import Path

from recostar.controle.xsd_structuration.cli_controle import executer_controle
from recostar.controle.xsd_structuration.codes_controle import RANG_DOCUMENT, identite_controle
from recostar.controle.xsd_structuration.priorites_structuration import statut_conformite, ventiler_par_priorite
from recostar.controle.xsd_structuration.regles_document import ErreurDocument, detecter, lire_document
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurDocument:
    """Établit si un GML est exploitable, et s'il porte des données."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Le profil ne sert ici qu'à nommer le rapport : les deux règles
        # portent sur le document, identique d'une version à l'autre.
        self.profil = profil

    def analyser(self) -> list[ErreurDocument]:
        """Retourne l'anomalie du document, s'il en porte une."""
        return detecter(lire_document(self.chemin_gml))


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurDocument],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E0118 en V1.1, E0018 en V1.0.
        "type_controle": identite_controle(version, RANG_DOCUMENT).type_controle,
        "version_controlee": version,
        "conformite": statut_conformite(par_priorite),
        "nb_erreurs": nb_erreurs,
        "nb_par_severite": {"ERREUR": nb_erreurs} if nb_erreurs else {},
        "nb_par_priorite": par_priorite,
        "erreurs": [e.vers_dict() for e in erreurs],
    }


def _resoudre_chemin_sortie(
    chemin_gml: Path,
    repertoire_sortie: Path | None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Détermine le chemin du fichier JSON de sortie."""
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_DOCUMENT).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurDocument],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Écrit le rapport d'erreurs au format JSON et retourne le chemin du fichier créé."""
    chemin_sortie = _resoudre_chemin_sortie(chemin_gml, repertoire_sortie, version)
    rapport = _construire_rapport(chemin_gml, erreurs, version)

    with open(chemin_sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    return chemin_sortie


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

DESCRIPTION_CLI: str = (
    "Controle de l'exploitabilite du document GML RecoStaR : fichier analysable "
    "et porteur d'au moins un objet (E0118 en V1.1, E0018 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "anomalie(s) de document"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurDocument]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurDocument(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle d'exploitabilité du document."""
    executer_controle(
        rang=RANG_DOCUMENT,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
