#!/usr/bin/env python3
"""
Controle E0120 / E0020 : la livraison ne contient aucun ouvrage en attente de
mise en service.

Un recolement decrit des ouvrages a mettre en service : au moins un objet doit
porter le statut `UnderCommissionning`. Une livraison qui n'en porte aucun n'est
pas fautive objet par objet — chacun est conforme — mais ne repond pas a l'objet
du depot, ce que ce controle nomme sous le code local E-9700.

Le moteur `regles_jeu` porte les deux constats de jeu, ce controle ne retenant
que le sien. L'autre controle issu du meme moteur : e0121.

Usage CLI :
    python -m recostar.controle.xsd_structuration.e0120 --gml <fichier.gml>
                                                        [--sortie <chemin>] [--version {auto,1.0,1.1}]

Sortie : <fichier>_controle_e0120.json
"""

from pathlib import Path

from recostar.controle.xsd_structuration.cli_controle import executer_controle
from recostar.controle.xsd_structuration.codes_controle import RANG_STATUT_EN_SERVICE, identite_controle
from recostar.controle.xsd_structuration.rapport_commun import generer_rapport as _generer_rapport
from recostar.controle.xsd_structuration.regles_document import lire_document
from recostar.controle.xsd_structuration.regles_jeu import ErreurJeu, detecter_statut_en_service
from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT
from recostar.controle.xsd_structuration.versions.profil import ProfilVersion

DESCRIPTION_CLI: str = (
    "Controle de la presence d'ouvrages en attente de mise en service dans la livraison (E0120 en V1.1, E0020 en V1.0)."
)

# Libelle du decompte affiche en fin d'execution.
LIBELLE_ANOMALIES: str = "anomalie(s) de statut de livraison"


class AnalyseurStatutEnService:
    """Etablit si la livraison porte au moins un ouvrage a mettre en service."""

    __slots__ = ("chemin_gml", "profil")

    def __init__(self, chemin_gml: Path, profil: ProfilVersion | None = None) -> None:
        self.chemin_gml = chemin_gml
        # Le profil ne sert qu'a nommer le rapport : le statut controle est le
        # meme d'une version a l'autre.
        self.profil = profil

    def analyser(self) -> list[ErreurJeu]:
        """Retourne l'anomalie de la livraison, si elle en porte une.

        Un document illisible ne rend aucun constat : son defaut est celui
        qu'E0118 nomme, et le signaler ici le dirait deux fois.
        """
        constat = lire_document(self.chemin_gml)
        if constat.racine is None:
            return []
        return detecter_statut_en_service(constat.racine)


def generer_rapport(
    chemin_gml: Path,
    erreurs: list[ErreurJeu],
    repertoire_sortie: Path | None = None,
    version: str = VERSION_DEFAUT,
) -> Path:
    """Ecrit le rapport JSON du controle et retourne le chemin du fichier cree."""
    identite = identite_controle(version, RANG_STATUT_EN_SERVICE)
    return _generer_rapport(
        chemin_gml,
        identite.type_controle,
        identite.suffixe_rapport,
        erreurs,
        repertoire_sortie,
        version,
    )


def analyser_fichier(chemin_gml: Path, profil: ProfilVersion) -> list[ErreurJeu]:
    """Analyse un GML avec le profil donne : adaptateur pour l'enveloppe CLI."""
    return AnalyseurStatutEnService(chemin_gml, profil).analyser()


def main(version_imposee: str | None = None) -> None:
    """Point d'entree principal du controle de statut de livraison."""
    executer_controle(
        rang=RANG_STATUT_EN_SERVICE,
        description=DESCRIPTION_CLI,
        analyser=analyser_fichier,
        generer_rapport=generer_rapport,
        libelle_anomalies=LIBELLE_ANOMALIES,
        version_imposee=version_imposee,
    )


if __name__ == "__main__":
    main()
