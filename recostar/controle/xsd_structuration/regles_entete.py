#!/usr/bin/env python3
"""
Définition déclarative des règles d'en-tête RecoStaR RPD V1.1.

Ces règles encodent les exigences PDF §[1] (structure du fichier GML),
§[3] (Metadata) et §9 (ReseauUtilite) que ni le contrôle structurel E110
ni le contrôle métier E111 ne prennent en charge.

Architecture évolutive : namespaces attendus, motif d'URL du schéma,
énumération des SRS autorisés et séquences des objets d'en-tête sont
exposés en tant que constantes / dictionnaires immuables. Le moteur
d'analyse (controle_e113) consomme ces structures sans les recalculer.

Référence : "Structuration des informations attendue pour les fichiers
de récolement des ouvrages RécoStaR" V1.1.
"""

from priorites_structuration import PRIORITE_MAJEUR, PRIORITE_PAR_DEFAUT
from sequenceur_xsd import SlotSequence

# ---------------------------------------------------------------------------
# Namespaces et schéma attendus (PDF §[1])
# ---------------------------------------------------------------------------

# Préfixes XML attendus avec leur URI exacte. La casse est significative :
# le PDF §[1] insiste explicitement sur "xmlns:RecoStaR" avec la même casse.
# Lookup en O(1) sur le préfixe via dict.
NAMESPACES_ATTENDUS: dict[str, str] = {
    "RecoStaR": "http://StaR-Elec.com",
    "gml": "http://www.opengis.net/gml/3.2",
    "xlink": "http://www.w3.org/1999/xlink",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# URI de namespace cible attendue dans xsi:schemaLocation.
URI_RECOSTAR = "http://StaR-Elec.com"

# Fragment d'URL qui doit apparaître dans xsi:schemaLocation pour la version
# v1.1. Le PDF §[1] proscrit explicitement les pointeurs vers la branche main.
FRAGMENT_URL_XSD_V1_1 = "/raw/RecoStar-v1.1/"

# Fragment indicatif d'une URL "branche main" -> permet un message d'erreur
# ciblé recommandant la migration vers le tag de version.
FRAGMENT_URL_MAIN = "/raw/main/"

# Priorité de la seule anomalie « schemaLocation sur la branche main » : le
# fichier reste lisible et exploitable, mais il n'est plus ancré sur un tag de
# version figé — l'écart de structuration est important sans être bloquant.
# Les autres écarts de schemaLocation (attribut absent, version non référencée)
# conservent la priorité bloquante par défaut.
PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN: str = PRIORITE_MAJEUR


# ---------------------------------------------------------------------------
# Systèmes de référence spatial autorisés (PDF §10.6.1, énumération SRSValue)
# ---------------------------------------------------------------------------

# frozenset : test d'appartenance O(1) lors de la validation du SRS du Metadata.
SRS_AUTORISES: frozenset[str] = frozenset(
    {
        "EPSG:3942",
        "EPSG:3943",
        "EPSG:3944",
        "EPSG:3945",
        "EPSG:3946",
        "EPSG:3947",
        "EPSG:3948",
        "EPSG:3949",
        "EPSG:3950",
        "EPSG:9842",
        "EPSG:9843",
        "EPSG:9844",
        "EPSG:9845",
        "EPSG:9846",
        "EPSG:9847",
        "EPSG:9848",
        "EPSG:9849",
        "EPSG:9850",
        "EPSG:2154",
        "EPSG:9794",
        "EPSG:5490",
        "EPSG:2972",
        "EPSG:2975",
        "EPSG:4471",
        "EPSG:4467",
    }
)


# ---------------------------------------------------------------------------
# Séquences attendues pour les objets d'en-tête (PDF §[3] et §9)
# ---------------------------------------------------------------------------

# Réutilise SlotSequence + valider_sequence du module sequenceur_xsd : le moteur
# d'ordonnancement est ainsi mutualisé entre E110 (types RPD) et E113 (en-tête).
SEQUENCES_ENTETE: dict[str, list[SlotSequence]] = {
    # PDF §[3] Metadata : 5 attributs tous obligatoires.
    "Metadata": [
        SlotSequence("Datecreation", 1, 1),
        SlotSequence("Logiciel", 1, 1),
        SlotSequence("Producteur", 1, 1),
        SlotSequence("Responsable", 1, 1),
        SlotSequence("SRS", 1, 1),
    ],
    # PDF §9 ReseauUtilite : 4 attributs tous obligatoires.
    "ReseauUtilite": [
        SlotSequence("Mention", 1, 1),
        SlotSequence("Nom", 1, 1),
        SlotSequence("Responsable", 1, 1),
        SlotSequence("Theme", 1, 1),
    ],
}

# Ensemble des objets d'en-tête (lookup O(1)).
TYPES_ENTETE: frozenset[str] = frozenset(SEQUENCES_ENTETE.keys())


# ---------------------------------------------------------------------------
# Cardinalités attendues des objets d'en-tête dans le fichier
# ---------------------------------------------------------------------------

# (min, max) : max = -1 signifie non borné.
# Metadata : exactement 1 par fichier (cf. PDF §[3], "métadonnées générales").
# ReseauUtilite : au moins 1, plusieurs autorisés (tranches de travaux).
CARDINALITES_ENTETE: dict[str, tuple[int, int]] = {
    "Metadata": (1, 1),
    "ReseauUtilite": (1, -1),
}


# ---------------------------------------------------------------------------
# Codes d'erreur produits par le contrôle E113
# ---------------------------------------------------------------------------

# Codes regroupés par préoccupation pour faciliter le filtrage côté rapport.
CODE_NAMESPACE_MANQUANT = "NAMESPACE_MANQUANT"
CODE_NAMESPACE_URI_INCORRECTE = "NAMESPACE_URI_INCORRECTE"
CODE_SCHEMA_LOCATION_MANQUANT = "SCHEMA_LOCATION_MANQUANT"
CODE_SCHEMA_LOCATION_VERSION_INCORRECTE = "SCHEMA_LOCATION_VERSION_INCORRECTE"
CODE_OBJET_ENTETE_MANQUANT = "OBJET_ENTETE_MANQUANT"
CODE_OBJET_ENTETE_TROP_NOMBREUX = "OBJET_ENTETE_TROP_NOMBREUX"
CODE_CHAMP_OBLIGATOIRE_MANQUANT = "CHAMP_OBLIGATOIRE_MANQUANT"
CODE_CHAMP_HORS_ORDRE = "CHAMP_HORS_ORDRE"
CODE_CHAMP_INATTENDU = "CHAMP_INATTENDU"
CODE_SRS_INVALIDE = "SRS_INVALIDE"
CODE_GML_ID_DUPLIQUE = "GML_ID_DUPLIQUE"


# ---------------------------------------------------------------------------
# Type d'erreur d'en-tête
# ---------------------------------------------------------------------------


class ErreurEntete:
    """Erreur détectée dans l'en-tête ou les métadonnées d'un fichier GML."""

    # __slots__ : économie mémoire lorsque de nombreuses erreurs sont produites
    # (cas typique : gml:id dupliqués sur un gros fichier).
    __slots__ = (
        "code",
        "element",
        "valeur_trouvee",
        "valeur_attendue",
        "message",
        "priorite",
    )

    # Sévérité fixe : le contrôle d'en-tête ne produit que des erreurs.
    # Attribut de classe pour homogénéiser le rapport JSON avec E114.
    severite = "ERREUR"

    def __init__(
        self,
        code: str,
        element: str | None,
        valeur_trouvee: str | None,
        valeur_attendue: str | None,
        message: str,
        priorite: str = PRIORITE_PAR_DEFAUT,
    ) -> None:
        self.code = code
        self.element = element
        self.valeur_trouvee = valeur_trouvee
        self.valeur_attendue = valeur_attendue
        self.message = message
        # Slot plutôt qu'attribut de classe : l'en-tête est le seul contrôle
        # dont une règle déroge à la priorité par défaut (branche 'main' du XSD).
        self.priorite = priorite

    def vers_dict(self) -> dict:
        """Sérialise l'erreur en dictionnaire pour le rapport JSON."""
        return {
            "code": self.code,
            "severite": self.severite,
            "priorite": self.priorite,
            "element": self.element,
            "valeur_trouvee": self.valeur_trouvee,
            "valeur_attendue": self.valeur_attendue,
            "message": self.message,
        }
