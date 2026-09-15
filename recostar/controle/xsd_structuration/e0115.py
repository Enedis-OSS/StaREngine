#!/usr/bin/env python3
"""
Contrôle de la validité des géométries portées par les objets RPD d'un GML RecoStaR.

Le moteur est version-agnostique : il applique le `ProfilVersion` qui lui est
fourni. Le code du contrôle suit la version contrôlée — **E0115** en V1.1,
**E0015** en V1.0 (point d'entrée dédié `e0015.py`).

Deux codes du vérificateur y sont rendus, selon le type de l'objet porteur :

  - **E-1109** pour une `RPD_GeometrieSupplementaire_Reco` sans géométrie
    exploitable — l'objet n'a pas d'autre raison d'être que celle-là ;
  - **E-1108** pour tout autre objet dont la géométrie manque de sommets.

Ce contrôle comble un angle mort de la validation XSD (E0112) : `gml:posList`
étant typé comme une liste de doubles, une liste **vide** satisfait le schéma.
Un GML dont les tracés sont vides est donc déclaré conforme par tout validateur
XSD, le défaut étant sémantique et non structurel (cf. `regles_geometrie`).

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON listant les géométries invalides détectées

Usage :
    python -m recostar.controle.xsd_structuration.e0115 <fichier.gml> [--output-dir <repertoire>] \
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
from recostar.controle.xsd_structuration.codes_controle import RANG_GEOMETRIE, identite_controle
from recostar.controle.xsd_structuration.priorites_structuration import statut_conformite, ventiler_par_priorite
from recostar.controle.xsd_structuration.regles_geometrie import ErreurGeometrie, valider_objet
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT, resoudre_profil
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Namespaces GML et RecoStar
# ---------------------------------------------------------------------------

NS_GML = "http://www.opengis.net/gml/3.2"

TAG_FEATURE_MEMBER = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID = f"{{{NS_GML}}}id"

# Préfixe des types EP, hors périmètre comme dans le contrôle d'ordre.
PREFIXE_EP = "EP_"


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def _extraire_gml_id(element: Element) -> str:
    """Extrait la valeur de gml:id d'un élément, ou '<sans id>' si absent."""
    return element.get(ATTR_GML_ID, "<sans id>")


# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurGeometries:
    """Parcourt les objets RPD d'un GML et valide leurs géométries."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1, comme les autres moteurs de la famille.
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurGeometrie]:
        """Valide la géométrie de chaque objet RPD porteur d'un élément Geometrie."""
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
        racine = arbre.getroot()
        erreurs: list[ErreurGeometrie] = []

        for membre in racine.iter(TAG_FEATURE_MEMBER):  # type: ignore
            erreurs.extend(self._valider_membre(membre))

        return erreurs

    def _valider_membre(self, membre: Element) -> list[ErreurGeometrie]:
        """Valide les géométries d'un featureMember dont le contenu est un type RPD."""
        enfants = list(membre)
        if not enfants:
            return []

        element = enfants[0]
        type_rpd = _nom_local(element.tag)

        # Même périmètre que le contrôle d'ordre : les objets EP et les types
        # hors du profil de version ne sont pas contrôlés.
        if type_rpd.startswith(PREFIXE_EP) or type_rpd not in self.profil.noms_rpd:
            return []

        return valider_objet(type_rpd, _extraire_gml_id(element), element)


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurGeometrie],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E0115 en V1.1, E0015 en V1.0.
        "type_controle": identite_controle(version, RANG_GEOMETRIE).type_controle,
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

    Le suffixe porte le code du contrôle appliqué : `_controle_e0115.json` en
    V1.1, `_controle_e0015.json` en V1.0.
    """
    dossier = repertoire_sortie if repertoire_sortie else chemin_gml.parent
    nom_json = chemin_gml.stem + identite_controle(version, RANG_GEOMETRIE).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurGeometrie],
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
    "Contrôle de la validité des géométries des objets RPD d'un fichier GML RecoStaR (E0115 en V1.1, E0015 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "geometrie(s) invalide(s) detectee(s)"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurGeometrie]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurGeometries(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle de validité des géométries."""
    executer_controle(
        rang=RANG_GEOMETRIE,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
