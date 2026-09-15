"""
Règles portant sur le document GML lui-même, avant tout objet qu'il contient.

Un seul contrôle y puise, au rang 8 de la famille :

    E0118 / E0018   E-0001   le GML n'est pas exploitable
                    E-0004   le GML ne contient aucune donnée

Pourquoi ce contrôle passe avant les autres, logiquement sinon dans l'ordre
--------------------------------------------------------------------------
Les neuf autres contrôles de la famille commencent par analyser le document ; si
celui-ci est mal formé, ils échouent tous, chacun signalant son propre échec. Le
rapport global affiche alors une liste de contrôles en échec sans dire *pourquoi*
— et le pipeline, qui isole les défaillances contrôle par contrôle, rend une
famille « en partie en échec » plutôt qu'un diagnostic.

Ce contrôle-ci est le seul à **rattraper** l'erreur d'analyse et à la rendre
comme une anomalie nommée. Les échecs des autres rangs cessent alors d'être
énigmatiques : ils sont la conséquence, E-0001 en est la cause.

Ce que le contrôle ne voit pas
------------------------------
La fiche E-0001 couvre trois cas : GML **manquant**, **illisible**, ou présent en
**plusieurs exemplaires**. Seul le deuxième est à portée d'un contrôle, qui reçoit
par construction le chemin d'un fichier. Les deux autres sont résolus en amont
par `fonctions_communes.source_gml.resoudre_chemin_gml`, qui rend un motif
explicite ; la famille est alors déclarée non exécutée, ce que le vérificateur
exprime par le niveau `bloquante` du même code.

Un document vide n'est pas un document illisible
------------------------------------------------
Les deux règles sont **exclusives par construction** : un document qui ne
s'analyse pas ne livre aucun objet à compter, et un document vide s'est
nécessairement analysé. Elles n'appellent d'ailleurs pas la même correction —
réparer un fichier corrompu, ou comprendre pourquoi une livraison ne contient
rien.

Ce qui compte comme « donnée »
------------------------------
Les `gml:featureMember` du document, quels que soient les objets qu'ils portent.
Un GML réduit à son en-tête — métadonnées, `ReseauUtilite` — s'analyse mais ne
décrit aucun ouvrage : c'est précisément le cas que nomme E-0004.
"""

from dataclasses import dataclass
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element, ParseError  # nosec B405

import defusedxml.ElementTree as DefusedET  # type: ignore

from recostar.controle.xsd_structuration.codes_controle import RANG_DOCUMENT
from recostar.controle.xsd_structuration.priorites_structuration import priorite_par_regle

# Codes de regle, un par code d'erreur rendu.
CODE_ILLISIBLE: str = "DOCUMENT_ILLISIBLE"
CODE_VIDE: str = "DOCUMENT_VIDE"

# Balise portant les objets du document.
NS_GML: str = "http://www.opengis.net/gml/3.2"
TAG_FEATURE_MEMBER: str = f"{{{NS_GML}}}featureMember"

# Identite de repli : le document n'a pas d'objet a designer.
IDENTITE_DOCUMENT: str = "<document>"


@dataclass(frozen=True, slots=True)
class ConstatDocument:
    """Ce que la lecture du document a pu établir.

    - `racine` : la racine analysée, ou None si l'analyse a échoué ;
    - `motif` : le message de l'analyseur, renseigné dans ce seul cas.

    Les deux champs sont exclusifs : c'est ce qui rend les deux règles exclusives
    à leur tour.
    """

    racine: Element | None
    motif: str | None


def lire_document(chemin_gml: Path) -> ConstatDocument:
    """Analyse le GML sans lever, afin que l'échec devienne une anomalie.

    C'est l'inverse du parti des autres rangs, qui laissent l'erreur remonter :
    ici, elle *est* le résultat du contrôle.
    """
    try:
        arbre = DefusedET.parse(str(chemin_gml))
    except (ParseError, OSError) as erreur:
        return ConstatDocument(None, str(erreur))
    return ConstatDocument(arbre.getroot(), None)


def compter_objets(racine: Element) -> int:
    """Compte les `featureMember` du document, quels que soient leurs objets."""
    return sum(1 for _ in racine.iter(TAG_FEATURE_MEMBER))


class ErreurDocument:
    """Document GML inexploitable, ou vide de tout objet."""

    __slots__ = ("type_rpd", "gml_id", "type_erreur", "nombre_objets", "message")

    # Severite fixe, comme les autres controles de structuration.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur (E-0001 ou E-0004)."""
        return priorite_par_regle(RANG_DOCUMENT, self.type_erreur)

    def __init__(self, type_erreur: str, nombre_objets: int, message: str) -> None:
        # Le défaut est celui du document : aucun type ni identifiant d'objet
        # n'a de sens ici, le repli nomme donc le document lui-même.
        self.type_rpd = IDENTITE_DOCUMENT
        self.gml_id = IDENTITE_DOCUMENT
        self.type_erreur = type_erreur
        self.nombre_objets = nombre_objets
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "type_erreur": self.type_erreur,
            "nombre_objets": self.nombre_objets,
            "message": self.message,
        }


def detecter(constat: ConstatDocument) -> list[ErreurDocument]:
    """Rend l'anomalie du document, s'il en porte une.

    Au plus une : les deux règles sont exclusives, et un document conforme n'en
    porte aucune.
    """
    if constat.racine is None:
        return [ErreurDocument(CODE_ILLISIBLE, 0, f"Le fichier GML n'a pas pu être analysé : {constat.motif}")]
    nombre = compter_objets(constat.racine)
    if nombre == 0:
        return [ErreurDocument(CODE_VIDE, 0, "Le fichier GML ne contient aucun objet (gml:featureMember)")]
    return []
