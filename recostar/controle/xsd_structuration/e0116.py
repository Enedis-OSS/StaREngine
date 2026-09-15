#!/usr/bin/env python3
"""
Contrôle des doublons dans les tables de jointure d'un fichier GML RecoStaR.

Le moteur est version-agnostique : il applique le `ProfilVersion` qui lui est
fourni. Le code du contrôle suit la version contrôlée — **E0116** en V1.1,
**E0016** en V1.0 (point d'entrée dédié `e0016.py`).

Un seul code du vérificateur y est rendu : **E-0012**, « Une table de jointure a
un doublon ». Deux objets de jointure décrivant le même couple font double
emploi — le lien existe une fois, il est déclaré deux.

Pourquoi ce contrôle appartient à la structuration
--------------------------------------------------
Le doublon est un défaut du **document**, non d'un objet du réseau : deux lignes
décrivent le même fait. À ce titre il rejoint les contrôles de structuration
plutôt qu'une famille métier.

Il y était de toute façon contraint : la conversion écrase ou replie les
relations dupliquées — `Ouvrage_Materiel` est indexée par affectation, les autres
alimentent des listes — si bien qu'un doublon n'a aucune trace dans les GeoJSON.

Les trois tables et leurs bouts sont décrits dans `regles_jointures`, qui porte
aussi la règle. Ce module ne fait que parcourir le document et rendre le rapport.

Ne pas confondre E0116 et le code E-0012
----------------------------------------
Le contrôle **E0012** (sans tiret) est la déclinaison V1.0 d'E0112, la validation
XSD native, et n'a aucun rapport avec le code d'erreur **E-0012** (avec tiret)
que rend ce contrôle-ci. Les deux nomenclatures coexistent dans le projet, le
tiret les distinguant : `code_controle` nomme le contrôle, `code_erreur` nomme
l'anomalie.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les couples de jointure dupliqués

Usage :
    python -m recostar.controle.xsd_structuration.e0116 <fichier.gml> [--output-dir <repertoire>] \
                                                        [--version {auto,1.0,1.1}]
"""

import json
from datetime import datetime
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (  # nosec B405
    Element,
    ElementTree,
)

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.cli_controle import executer_controle
from recostar.controle.xsd_structuration.codes_controle import RANG_JOINTURES, identite_controle
from recostar.controle.xsd_structuration.priorites_structuration import statut_conformite, ventiler_par_priorite
from recostar.controle.xsd_structuration.regles_jointures import (
    TABLES_PAR_TYPE,
    ErreurJointure,
    detecter_doublons,
)
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT, resoudre_profil
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Namespaces GML
# ---------------------------------------------------------------------------

NS_GML = "http://www.opengis.net/gml/3.2"

TAG_FEATURE_MEMBER = f"{{{NS_GML}}}featureMember"


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurJointures:
    """Parcourt les tables de jointure d'un GML et détecte leurs doublons."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1, comme les autres moteurs de la famille. Les
        # trois tables de jointure existent dans les deux versions ; le profil ne
        # sert ici qu'à nommer le rapport.
        self.profil = profil if profil is not None else resoudre_profil()

    def _collecter(self) -> list[tuple[str, Element]]:
        """Relève les objets de jointure du document, avec leur type.

        Les `featureMember` portant autre chose sont écartés : le contrôle ne
        juge que les trois tables, tout le reste relevant des contrôles voisins.
        """
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
        jointures: list[tuple[str, Element]] = []
        for membre in arbre.getroot().iter(TAG_FEATURE_MEMBER):  # type: ignore
            for element in membre:
                type_rpd = _nom_local(element.tag)
                if type_rpd in TABLES_PAR_TYPE:
                    jointures.append((type_rpd, element))
        return jointures

    def analyser(self) -> list[ErreurJointure]:
        """Détecte les couples de jointure déclarés plus d'une fois."""
        return detecter_doublons(self._collecter())


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurJointure],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E0116 en V1.1, E0016 en V1.0.
        "type_controle": identite_controle(version, RANG_JOINTURES).type_controle,
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

    Le suffixe porte le code du contrôle appliqué : `_controle_e0116.json` en
    V1.1, `_controle_e0016.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_JOINTURES).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurJointure],
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
    "Contrôle des doublons dans les tables de jointure d'un fichier GML RecoStaR (E0116 en V1.1, E0016 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "jointure(s) dupliquee(s) detectee(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurJointure]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurJointures(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle des doublons de jointure."""
    executer_controle(
        rang=RANG_JOINTURES,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
