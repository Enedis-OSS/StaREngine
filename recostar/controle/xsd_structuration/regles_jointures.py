"""
Règles portant sur les tables de jointure d'un GML RecoStaR.

Deux contrôles y puisent, un par code du vérificateur :

    E0116 / E0016   E-0012   un couple déclaré plus d'une fois
    E0117 / E0017   E-0013   un bout de jointure non renseigné

RecoStaR décrit ses relations par des objets dédiés, un par lien, que le
vérificateur appelle des **tables de jointure** :

    Ouvrage_Materiel              ouvrage          -> materiel
    CableElectrique_NoeudReseau   cableelectrique  -> noeudreseau
    Cheminement_Cables            cheminement      -> cables

Deux objets décrivant le **même couple** font double emploi : le lien existe une
fois, il est déclaré deux. C'est le code `E-0012` du vérificateur, « Une table de
jointure a un doublon ».

Pourquoi ces contrôles lisent le GML
------------------------------------
La conversion écrase ou replie les relations dupliquées — `Ouvrage_Materiel` est
indexée par affectation, les autres alimentent des listes — si bien qu'un doublon
n'a aucune trace dans les GeoJSON, et elle ignore purement une relation dont un
bout manque. Ces contrôles appartiennent donc à la famille `xsd_structuration`,
qui lit le document source.

Doublon comme champ manquant sont des défauts du **document**, non d'un objet du
réseau : c'est à ce titre qu'ils rejoignent les contrôles de structuration
plutôt qu'une famille métier.

Ce qui identifie un lien
------------------------
Le couple de ses deux bouts, et lui seul. Les attributs accessoires portés par la
jointure — `EtatAvantRaccordement` sur la relation câble/nœud — n'entrent pas
dans la comparaison : deux liens entre les mêmes objets restent le même lien,
quelles que soient leurs annotations, et c'est bien un doublon qu'il faut lever.

Une jointure dont l'un des bouts manque ne décrit aucun lien : elle est écartée
du contrôle de doublon, et relève d'`E-0013`, « Champ manquant sur une table de
jointure », porté par E0117 depuis ce même module. Les deux règles sont donc
**exclusives par construction** : une jointure incomplète ne peut pas faire
doublon, et une jointure dupliquée a nécessairement ses deux bouts.

Les références sont comparées après résolution de la forme fragmentée
« #idXXXX », que le GML admet : `#id1` et `id1` désignent le même objet, et les
distinguer laisserait passer un doublon écrit sous deux formes.

Une anomalie par **couple** dupliqué, non par ligne en trop : trois déclarations
du même lien sont un seul doublon à corriger, et leur nombre est reporté.
"""

from collections import Counter
from dataclasses import dataclass

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

from recostar.controle.xsd_structuration.codes_controle import RANG_JOINTURES, RANG_JOINTURES_CHAMPS
from recostar.controle.xsd_structuration.priorites_structuration import priorite_par_regle

# Codes de règle, un par contrôle servi par ce module.
CODE_DOUBLON: str = "JOINTURE_DUPLIQUEE"
CODE_CHAMP_MANQUANT: str = "JOINTURE_CHAMP_MANQUANT"

# Attribut portant la référence d'un bout de jointure.
NS_XLINK: str = "http://www.w3.org/1999/xlink"
ATTR_XLINK_HREF: str = f"{{{NS_XLINK}}}href"

# Préfixe de la forme fragmentée d'une référence XLink.
PREFIXE_FRAGMENT: str = "#"

# Nombre d'occurrences à partir duquel un couple est un doublon.
SEUIL_DOUBLON: int = 2

# Identité de repli d'une jointure dont aucun bout n'est renseigné.
SANS_REFERENCE: str = "<sans référence>"


@dataclass(frozen=True, slots=True)
class TableJointure:
    """Description d'une table de jointure : son objet et ses deux bouts."""

    type_rpd: str
    bout_source: str
    bout_cible: str


# Les trois tables de jointure du modèle RecoStaR. Les noms des bouts sont ceux
# que lit `recostar_to_geojson`, source de vérité de la relation.
TABLES_JOINTURE: tuple[TableJointure, ...] = (
    TableJointure("Ouvrage_Materiel", "ouvrage", "materiel"),
    TableJointure("CableElectrique_NoeudReseau", "cableelectrique", "noeudreseau"),
    TableJointure("Cheminement_Cables", "cheminement", "cables"),
)

# Index par nom d'objet, pour reconnaître une jointure en O(1) au parcours.
TABLES_PAR_TYPE: dict[str, TableJointure] = {table.type_rpd: table for table in TABLES_JOINTURE}


class ErreurJointure:
    """Couple de jointure déclaré plus d'une fois dans le document."""

    __slots__ = ("type_rpd", "gml_id", "type_erreur", "source", "cible", "occurrences", "message")

    # Sévérité fixe, comme les autres contrôles de structuration : ce moteur ne
    # produit pas d'avertissement.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur (E-0012)."""
        return priorite_par_regle(RANG_JOINTURES, self.type_erreur)

    def __init__(
        self,
        type_rpd: str,
        source: str,
        cible: str,
        occurrences: int,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        # Une jointure ne porte pas de gml:id : le couple tient lieu d'identité.
        self.gml_id = f"{source} -> {cible}"
        self.type_erreur = CODE_DOUBLON
        self.source = source
        self.cible = cible
        self.occurrences = occurrences
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "type_erreur": self.type_erreur,
            "source": self.source,
            "cible": self.cible,
            "occurrences": self.occurrences,
            "message": self.message,
        }


def _nom_local(tag: str) -> str:
    """Extrait le nom local depuis un tag qualifié '{namespace}localname'."""
    return tag.rsplit("}", 1)[-1]


def reference_bout(element: Element, nom: str) -> str | None:
    """Retourne la référence portée par un bout de jointure, ou None.

    La forme fragmentée « #idXXXX » est résolue : le GML l'admet, et distinguer
    `#id1` de `id1` laisserait passer un doublon écrit sous deux formes.
    """
    for enfant in element:
        if _nom_local(enfant.tag) != nom:
            continue
        reference = enfant.get(ATTR_XLINK_HREF)
        if reference is None:
            return None
        return reference.lstrip(PREFIXE_FRAGMENT).strip() or None
    return None


def couple_jointure(element: Element, table: TableJointure) -> tuple[str, str] | None:
    """Retourne le couple (source, cible) d'une jointure, ou None si incomplet.

    Une jointure dont l'un des bouts manque ne décrit aucun lien : elle est
    ignorée ici, son incomplétude relevant d'E0117.
    """
    source = reference_bout(element, table.bout_source)
    cible = reference_bout(element, table.bout_cible)
    if source is None or cible is None:
        return None
    return source, cible


def compter_couples(elements: list[tuple[str, Element]]) -> Counter[tuple[str, str, str]]:
    """Compte les occurrences de chaque couple, par table de jointure.

    La clé porte le type de la table : deux tables différentes peuvent
    légitimement relier les mêmes identifiants, et les confondre inventerait un
    doublon.
    """
    decompte: Counter[tuple[str, str, str]] = Counter()
    for type_rpd, element in elements:
        table = TABLES_PAR_TYPE.get(type_rpd)
        if table is None:
            continue
        couple = couple_jointure(element, table)
        if couple is not None:
            decompte[(type_rpd, couple[0], couple[1])] += 1
    return decompte


def _formuler_message(type_rpd: str, source: str, cible: str, occurrences: int) -> str:
    """Rédige le message d'un couple dupliqué."""
    return f"La jointure {type_rpd} « {source} -> {cible} » est déclarée {occurrences} fois"


def detecter_doublons(elements: list[tuple[str, Element]]) -> list[ErreurJointure]:
    """Détecte les couples de jointure déclarés plus d'une fois.

    Une anomalie par couple dupliqué, non par ligne en trop : trois déclarations
    du même lien sont un seul doublon à corriger. Le tri rend l'ordre des
    erreurs déterministe.
    """
    decompte = compter_couples(elements)
    return [
        ErreurJointure(type_rpd, source, cible, occurrences, _formuler_message(type_rpd, source, cible, occurrences))
        for (type_rpd, source, cible), occurrences in sorted(decompte.items())
        if occurrences >= SEUIL_DOUBLON
    ]


class ErreurChampJointure:
    """Bout de jointure non renseigné : la relation ne désigne pas sa cible."""

    __slots__ = ("type_rpd", "gml_id", "type_erreur", "champ", "reference_presente", "message")

    # Sévérité fixe, comme les autres contrôles de structuration.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur (E-0013)."""
        return priorite_par_regle(RANG_JOINTURES_CHAMPS, self.type_erreur)

    def __init__(self, type_rpd: str, champ: str, reference_presente: str | None, message: str) -> None:
        self.type_rpd = type_rpd
        # Une jointure ne porte pas de gml:id. Le bout qui **est** renseigné
        # situe l'anomalie ; sans lui, la jointure ne désigne plus rien du tout.
        self.gml_id = reference_presente or SANS_REFERENCE
        self.type_erreur = CODE_CHAMP_MANQUANT
        self.champ = champ
        self.reference_presente = reference_presente
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "type_erreur": self.type_erreur,
            "champ": self.champ,
            "reference_presente": self.reference_presente,
            "message": self.message,
        }


def champs_manquants(element: Element, table: TableJointure) -> list[str]:
    """Retourne les bouts non renseignés d'une jointure, dans l'ordre du modèle.

    Un bout manque s'il est absent de l'objet, ou présent sans `xlink:href`
    exploitable : dans les deux cas la relation ne désigne pas sa cible.
    """
    return [nom for nom in (table.bout_source, table.bout_cible) if reference_bout(element, nom) is None]


def detecter_champs_manquants(elements: list[tuple[str, Element]]) -> list[ErreurChampJointure]:
    """Détecte les bouts de jointure non renseignés.

    Une anomalie **par champ manquant**, non par jointure : c'est le champ que le
    code nomme, et l'opérateur doit savoir lequel des deux bouts renseigner. Une
    jointure privée de ses deux bouts en porte donc deux — elle ne décrit
    effectivement plus rien.
    """
    erreurs: list[ErreurChampJointure] = []
    for type_rpd, element in elements:
        table = TABLES_PAR_TYPE.get(type_rpd)
        if table is None:
            continue
        manquants = champs_manquants(element, table)
        if not manquants:
            continue
        presente = next(
            (reference_bout(element, nom) for nom in (table.bout_source, table.bout_cible) if nom not in manquants),
            None,
        )
        erreurs.extend(
            ErreurChampJointure(type_rpd, champ, presente, _formuler_message_champ(type_rpd, champ, presente))
            for champ in manquants
        )
    return erreurs


def _formuler_message_champ(type_rpd: str, champ: str, presente: str | None) -> str:
    """Rédige le message d'un bout de jointure non renseigné."""
    contexte = f" (autre bout : « {presente} »)" if presente is not None else ""
    return f"La jointure {type_rpd} ne renseigne pas son champ « {champ} »{contexte}"
