"""
Règle portant sur le jeu entier, et non sur un objet en particulier.

Un contrôle y puise, au rang 10 de la famille :

    E0120 / E0020   E-9700   aucun ouvrage en attente de mise en service

Pourquoi des règles de jeu, et non d'objet
------------------------------------------
Les autres rangs signalent un objet fautif parmi d'autres : il se corrige seul,
et le reste de la livraison tient. Ce constat-ci ne vise aucun objet — il dit
que la livraison **dans son ensemble** n'est pas celle attendue. Un récolement
sans le moindre ouvrage au statut `UnderCommissionning` ne décrit aucun travail
à mettre en service.

Le défaut ne se déduit d'aucun objet : chacun, pris isolément, est conforme.
Seul le décompte sur le jeu entier le révèle, d'où sa place ici plutôt que dans
les règles d'objet.

L'altimétrie du jeu, elle, relève de la famille altimétrie
----------------------------------------------------------
Le constat voisin — un jeu dont les points de levé rattachés aux câbles sont
tous à l'altitude zéro — porte le code E-9701 et vit dans
`altimetrie.detection_sommets_cables` : il exige d'apparier les points de levé
aux sommets de câbles et d'en écarter les extrémités, ce que ce moteur-là sait
faire et que la structuration, qui ne lit que le GML, devrait réécrire.
"""

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import Element  # nosec B405

from recostar.controle.xsd_structuration.codes_controle import RANG_STATUT_EN_SERVICE
from recostar.controle.xsd_structuration.priorites_structuration import priorite_par_regle

# Codes de regle, un par code d'erreur rendu.
CODE_AUCUN_EN_SERVICE: str = "AUCUN_OUVRAGE_EN_SERVICE"

# Namespaces et balises lues.
NS_RECOSTAR: str = "http://StaR-Elec.com"
TAG_STATUT: str = f"{{{NS_RECOSTAR}}}Statut"

# Statut des ouvrages que la livraison met en service : ce que le recolement
# vient precisement decrire.
STATUT_EN_SERVICE: str = "UnderCommissionning"

# Identite de repli : le constat porte sur le jeu, non sur un objet.
IDENTITE_JEU: str = "<jeu>"


class ErreurJeu:
    """Constat portant sur la livraison entière."""

    __slots__ = ("type_rpd", "gml_id", "rang", "type_erreur", "nombre", "message")

    # Severite fixe, comme les autres controles de structuration.
    severite = "ERREUR"

    @property
    def priorite(self) -> str:
        """Priorité déduite du code d'erreur du vérificateur, au rang du constat."""
        return priorite_par_regle(self.rang, self.type_erreur)

    def __init__(self, rang: int, type_erreur: str, nombre: int, message: str) -> None:
        # Aucun objet n'est en cause : le repli nomme le jeu lui-meme.
        self.type_rpd = IDENTITE_JEU
        self.gml_id = IDENTITE_JEU
        self.rang = rang
        self.type_erreur = type_erreur
        self.nombre = nombre
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "type_erreur": self.type_erreur,
            "nombre": self.nombre,
            "message": self.message,
        }


def compter_ouvrages_en_service(racine: Element) -> int:
    """Compte les objets portant le statut de mise en service."""
    return sum(1 for statut in racine.iter(TAG_STATUT) if (statut.text or "").strip() == STATUT_EN_SERVICE)


def detecter_statut_en_service(racine: Element) -> list[ErreurJeu]:
    """Signale une livraison sans aucun ouvrage en attente de mise en service."""
    nombre = compter_ouvrages_en_service(racine)
    if nombre:
        return []
    return [
        ErreurJeu(
            RANG_STATUT_EN_SERVICE,
            CODE_AUCUN_EN_SERVICE,
            0,
            f"Aucun objet du jeu ne porte le statut « {STATUT_EN_SERVICE} » : "
            "la livraison ne décrit aucun ouvrage à mettre en service",
        )
    ]
