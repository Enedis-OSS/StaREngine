#!/usr/bin/env python3
"""
Contrôle de l'attribut `srsDimension` des géométries d'un GML RecoStaR.

Le moteur est version-agnostique : il applique le `ProfilVersion` qui lui est
fourni. Le code du contrôle suit la version contrôlée — **E0119** en V1.1,
**E0019** en V1.0 (point d'entrée dédié `e0019.py`).

Trois codes du vérificateur y sont rendus, en cascade sur un même nœud :

    E-1201   le nœud de positions ne déclare aucun `srsDimension`
    E-1300   la valeur déclarée n'est pas celle du modèle (3)
    E-0009   le nombre de valeurs ne se divise pas par la dimension déclarée

La règle et son raisonnement vivent dans `regles_srs_dimension`. Ce module ne
fait que parcourir les objets RPD et rendre le rapport.

Périmètre : les mêmes objets que le contrôle de géométrie (E0115 / E0015) — les
types RPD du profil de version, les objets EP exclus. Seuls sont visités les
objets porteurs d'un élément `Geometrie` : `srsDimension` n'a de sens que là.

Entrée  : Fichier GML RecoStaR à contrôler
Sortie  : Fichier JSON décrivant l'exploitabilité du document

Usage :
    python -m recostar.controle.xsd_structuration.e0119 <fichier.gml> [--output-dir <repertoire>] \
                                                        [--version {auto,1.0,1.1}]
"""

import json
from datetime import datetime
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element, ElementTree  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.cli_controle import executer_controle
from recostar.controle.xsd_structuration.codes_controle import RANG_SRS_DIMENSION, identite_controle
from recostar.controle.xsd_structuration.priorites_structuration import statut_conformite, ventiler_par_priorite
from recostar.controle.xsd_structuration.regles_geometrie import BALISE_GEOMETRIE
from recostar.controle.xsd_structuration.regles_srs_dimension import ErreurSrsDimension, detecter
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT, resoudre_profil
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

# ---------------------------------------------------------------------------
# Analyse du fichier GML
# ---------------------------------------------------------------------------


class AnalyseurSrsDimension:
    """Parcourt les géométries d'un GML et valide leur `srsDimension`."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Profil par défaut : V1.1, comme les autres moteurs de la famille. Il
        # délimite ici le périmètre, les types RPD variant d'une version à l'autre.
        self.profil = profil if profil is not None else resoudre_profil()

    def analyser(self) -> list[ErreurSrsDimension]:
        """Valide le `srsDimension` de chaque objet RPD porteur d'une géométrie."""
        arbre: ElementTree[Element] = DefusedET.parse(str(self.chemin_gml))
        erreurs: list[ErreurSrsDimension] = []
        for membre in arbre.getroot().iter(TAG_FEATURE_MEMBER):  # type: ignore
            erreurs.extend(self._valider_membre(membre))
        return erreurs

    def _valider_membre(self, membre: Element) -> list[ErreurSrsDimension]:
        """Valide les géométries d'un featureMember dont le contenu est un type RPD."""
        enfants = list(membre)
        if not enfants:
            return []

        element = enfants[0]
        type_rpd = _nom_local(element.tag)
        # Même périmètre que le contrôle de géométrie : les objets EP et les
        # types hors du profil de version ne sont pas contrôlés.
        if type_rpd.startswith(PREFIXE_EP) or type_rpd not in self.profil.noms_rpd:
            return []

        gml_id = element.get(ATTR_GML_ID, SANS_ID)
        erreurs: list[ErreurSrsDimension] = []
        for geometrie in element.iter():
            if _nom_local(geometrie.tag) == BALISE_GEOMETRIE:
                erreurs.extend(detecter(type_rpd, gml_id, geometrie))
        return erreurs


# ---------------------------------------------------------------------------
# Génération du rapport JSON
# ---------------------------------------------------------------------------


def _construire_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurSrsDimension],
    version: str = VERSION_DEFAUT,
) -> dict:
    """Construit le dictionnaire de rapport à sérialiser en JSON."""
    nb_erreurs = len(erreurs)
    par_priorite = ventiler_par_priorite(erreurs)
    return {
        "fichier": str(chemin_gml.resolve()),
        "date_controle": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "niveau": "Forte",
        # Le code du contrôle dépend de la version : E0119 en V1.1, E0019 en V1.0.
        "type_controle": identite_controle(version, RANG_SRS_DIMENSION).type_controle,
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
    nom_json = chemin_gml.stem + identite_controle(version, RANG_SRS_DIMENSION).suffixe_rapport
    return (dossier / nom_json).resolve()


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurSrsDimension],
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
    "Controle de l'attribut srsDimension des geometries d'un GML RecoStaR : "
    "declare, egal a 3, et coherent avec le nombre de coordonnees "
    "(E0119 en V1.1, E0019 en V1.0)."
)

# Libellé du décompte affiché en fin d'exécution.
LIBELLE_ANOMALIES: str = "anomalie(s) de srsDimension"


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurSrsDimension]:
    """Analyse un GML avec le profil donné : adaptateur pour l'enveloppe CLI."""
    return AnalyseurSrsDimension(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entrée principal du contrôle de srsDimension."""
    executer_controle(
        rang=RANG_SRS_DIMENSION,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()


# Constantes de parcours, reprises du controle de geometrie : les deux visitent
# les memes objets.
NS_GML: str = "http://www.opengis.net/gml/3.2"
TAG_FEATURE_MEMBER: str = f"{{{NS_GML}}}featureMember"
ATTR_GML_ID: str = f"{{{NS_GML}}}id"
PREFIXE_EP: str = "EP_"
SANS_ID: str = "<sans id>"


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]
