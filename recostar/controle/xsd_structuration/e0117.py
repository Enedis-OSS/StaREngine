#!/usr/bin/env python3
"""
Contrôle des champs manquants dans les tables de jointure d'un fichier GML RecoStaR.

Le moteur est version-agnostique : il applique le `ProfilVersion` qui lui est
fourni. Le code du contrôle suit la version contrôlée — **E0117** en V1.1,
**E0017** en V1.0 (point d'entrée dédié `e0017.py`).

Un seul code du vérificateur y est rendu : **E-0013**, « Champ manquant sur une
table de jointure ». Une jointure dont l'un des deux bouts n'est pas renseigné
ne désigne pas sa cible : elle affirme une relation sans dire avec quoi.

Complément d'E0116, sur les mêmes objets
----------------------------------------
Les deux contrôles lisent les trois mêmes tables, décrites dans
`regles_jointures`, et sont **exclusifs par construction** :

    E0116 / E-0012   un couple déclaré plus d'une fois
    E0117 / E-0013   un bout non renseigné

Une jointure incomplète ne peut pas faire doublon — elle ne forme aucun couple —
et une jointure dupliquée a nécessairement ses deux bouts. Aucune ne relève donc
des deux codes.

Un bout manque s'il est absent de l'objet, ou présent sans `xlink:href`
exploitable : dans les deux cas la relation ne désigne rien.

Une anomalie **par champ manquant**, non par jointure : c'est le champ que le
code nomme, et l'opérateur doit savoir lequel des deux bouts renseigner. Une
jointure privée de ses deux bouts en porte donc deux — elle ne décrit
effectivement plus rien. Le bout qui *est* renseigné, quand il y en a un, situe
l'anomalie dans le document.

Pourquoi ce contrôle appartient à la structuration
--------------------------------------------------
La conversion ignore purement une relation dont un bout manque : elle n'a aucune
trace dans les GeoJSON. Et le défaut est celui du **document**, non d'un objet du
réseau. À ce double titre il rejoint la famille `xsd_structuration`, qui lit le
document source.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les bouts de jointure non renseignés

Usage :
    python -m recostar.controle.xsd_structuration.e0117 <fichier.gml> [--output-dir <repertoire>] \
                                                        [--version {auto,1.0,1.1}]
"""

import json
from datetime import datetime
from pathlib import Path

from recostar.controle.xsd_structuration.cli_controle import executer_controle
from recostar.controle.xsd_structuration.codes_controle import RANG_JOINTURES_CHAMPS, identite_controle
from recostar.controle.xsd_structuration.e0116 import AnalyseurJointures
from recostar.controle.xsd_structuration.priorites_structuration import statut_conformite, ventiler_par_priorite
from recostar.controle.xsd_structuration.regles_jointures import ErreurChampJointure, detecter_champs_manquants
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurChampsJointure(AnalyseurJointures):
    """Parcourt les tables de jointure d'un GML et relève leurs bouts manquants.

    Le parcours du document est celui d'E0116 : les deux contrôles lisent les
    mêmes objets, seule la règle appliquée diffère. Hériter du collecteur évite
    d'en tenir deux versions, et garantit que les deux contrôles voient
    exactement le même périmètre.
    """

    __slots__ = ()

    def analyser(self) -> list[ErreurChampJointure]:  # type: ignore[override]
        """Détecte les bouts de jointure non renseignés."""
        return detecter_champs_manquants(self._collecter())


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurChampJointure],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E0117 en V1.1, E0017 en V1.0.
        "type_controle": identite_controle(version, RANG_JOINTURES_CHAMPS).type_controle,
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
    """Détermine le chemin du fichier JSON de sortie.

    Le suffixe porte le code du contrôle appliqué : `_controle_e0117.json` en
    V1.1, `_controle_e0017.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_JOINTURES_CHAMPS).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurChampJointure],
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
    "Contrôle des champs manquants dans les tables de jointure d'un fichier GML "
    "RecoStaR (E0117 en V1.1, E0017 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "champ(s) de jointure non renseigne(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurChampJointure]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurChampsJointure(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle des champs de jointure."""
    executer_controle(
        rang=RANG_JOINTURES_CHAMPS,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
