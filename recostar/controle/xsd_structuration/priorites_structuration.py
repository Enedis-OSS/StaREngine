#!/usr/bin/env python3
"""
Priorités des anomalies de structuration XSD (E0110-E0114 / E0010-E0014).

Les cinq contrôles de structuration produisent toutes leurs anomalies avec la
même sévérité (`ERREUR`) : la sévérité dit *ce qui a été violé*, elle ne dit pas
*ce que la violation coûte*. Ce module ajoute cette seconde dimension — la
**priorité** — afin que quelques règles clairement identifiées soient signalées
sans invalider la livraison, pendant que toutes les autres restent bloquantes.

Depuis le lot 2, cette priorité n'est plus choisie : elle est **déduite du
niveau du code d'erreur du vérificateur** que la règle enfreinte déclenche
(`codes_verificateur_xsd`). Chaque classe d'erreur déclare la sienne par
`priorite_par_rang`, et les règles à code propre par `priorite_par_regle`.

Deux dérogations restent déclarées **au plus près de la règle concernée**,
jamais ici. Ce sont des assouplissements locaux, assumés comme tels : la
priorité explicite d'une règle prime sur la dérivation.

  - `regles_valeurs.REGLES_VALEURS` → règle `E_THEME_RPD`
    (ReseauUtilite/Theme hors énumération) : priorité basse ;
  - `regles_entete.PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN` → schemaLocation
    pointant la branche `main` du XSD : priorité moyenne.

Les libellés de priorité sont des littéraux alignés sur
`controle/synthese_controles.py` (`ORDRE_PRIORITES`, `PRIORITES_DECLASSANTES`)
mais volontairement **non importés** : les modules de ce dossier s'importent à
plat et restent exécutables seuls en ligne de commande, sans accès au paquet
parent. C'est la convention déjà retenue par `codes_verificateur_xsd`.
"""

from collections.abc import Iterable
from typing import Protocol

from recostar.controle.xsd_structuration.codes_verificateur_xsd import resoudre_code_erreur_xsd

# ---------------------------------------------------------------------------
# Échelle de priorité
# ---------------------------------------------------------------------------

# Niveaux du vérificateur RecoStaR, du plus grave au moins grave. `bloquante`
# n'est pas repris : chez le vérificateur il signifie que le traitement
# s'interrompt, ce que star-engine exprime par le statut « Non exécuté ».
PRIORITE_FORTE: str = "forte"
PRIORITE_MOYENNE: str = "moyenne"
PRIORITE_BASSE: str = "basse"

# Priorité appliquée à une anomalie dont la règle n'a pas de code d'erreur : une
# erreur de structuration invalide la conformité au schéma, elle est forte par
# défaut. Les règles qui ont un code tiennent leur priorité de `priorite_par_regle`.
PRIORITE_PAR_DEFAUT: str = PRIORITE_FORTE

# Niveau de chaque code d'erreur visé par `codes_verificateur_xsd`, recopié des
# fiches du vérificateur en version 2.14.0. La table est locale au dossier, pour
# la même raison que `CORRESPONDANCES_XSD` ; un test la confronte au référentiel
# du paquet parent, ce qui rend tout désalignement visible.
NIVEAU_PAR_CODE: dict[str, str] = {
    "E-0003": PRIORITE_FORTE,
    "E-0012": PRIORITE_FORTE,
    "E-0013": PRIORITE_FORTE,
    "E-0008": PRIORITE_FORTE,
    "E-0010": PRIORITE_FORTE,
    "E-1101": PRIORITE_FORTE,
    "E-1103": PRIORITE_FORTE,
    "E-1104": PRIORITE_MOYENNE,
    "E-1106": PRIORITE_FORTE,
    "E-1107": PRIORITE_FORTE,
    "E-2100": PRIORITE_FORTE,
    "E-2102": PRIORITE_FORTE,
    "E-1108": PRIORITE_FORTE,
    "E-1109": PRIORITE_FORTE,
    "E-0001": PRIORITE_FORTE,
    "E-0004": PRIORITE_FORTE,
    "E-0009": PRIORITE_FORTE,
    "E-1201": PRIORITE_MOYENNE,
    "E-1300": PRIORITE_BASSE,
    # Code local du constat de jeu : la livraison entiere est en cause.
    "E-9700": PRIORITE_MOYENNE,
}

# Seules ces priorités déclassent un contrôle en NON_CONFORME. frozenset : test
# d'appartenance en O(1) et valeur immuable. Doit rester aligné sur
# `synthese_controles.PRIORITES_DECLASSANTES`, qui applique la même règle au
# statut de famille et au rapport PDF.
PRIORITES_DECLASSANTES: frozenset[str] = frozenset({PRIORITE_FORTE})


def priorite_par_regle(rang: int, code_regle: str | None = None) -> str:
    """Priorité déduite du code d'erreur qu'une règle de structuration déclenche.

    Repli sur `PRIORITE_PAR_DEFAUT` lorsque la règle n'a pas d'équivalent chez
    le vérificateur : une anomalie sans code doit rester signalée, pas muette.
    """
    code_erreur = resoudre_code_erreur_xsd(rang, code_regle)
    if code_erreur is None:
        return PRIORITE_PAR_DEFAUT
    return NIVEAU_PAR_CODE.get(code_erreur, PRIORITE_PAR_DEFAUT)


def priorite_par_rang(rang: int) -> str:
    """Priorité par défaut d'un contrôle de structuration, déduite de son code.

    Sert de valeur de classe aux erreurs des contrôles qui n'émettent qu'un seul
    code (E0111, E0112, E0114).
    """
    return priorite_par_regle(rang, None)


# ---------------------------------------------------------------------------
# Statuts de conformité
# ---------------------------------------------------------------------------

CONFORME: str = "CONFORME"
NON_CONFORME: str = "NON_CONFORME"


class AnomalieStructuration(Protocol):
    """Contrat minimal attendu d'une anomalie de structuration.

    Les classes d'erreur du dossier le satisfont structurellement : aucune n'a à
    hériter d'une base commune pour être ventilée par ce module.

    `priorite` est déclarée en lecture seule (@property) et non en attribut : la
    ventilation ne fait que la lire, et un attribut serait invariant, donc
    incompatible avec les erreurs qui la calculent au lieu de la stocker.
    """

    @property
    def priorite(self) -> str:
        """Niveau de priorité de l'anomalie."""
        ...


# ---------------------------------------------------------------------------
# Ventilation et conformité
# ---------------------------------------------------------------------------


def ventiler_par_priorite(erreurs: Iterable[AnomalieStructuration]) -> dict[str, int]:
    """Compte les anomalies par niveau de priorité.

    Un seul passage sur la collection ; la ventilation est vide lorsqu'aucune
    anomalie n'est détectée, ce qui évite d'écrire des compteurs à zéro dans les
    rapports JSON.
    """
    ventilation: dict[str, int] = {}
    for erreur in erreurs:
        priorite = erreur.priorite
        ventilation[priorite] = ventilation.get(priorite, 0) + 1
    return ventilation


def compter_bloquantes(ventilation: dict[str, int]) -> int:
    """Nombre d'anomalies dont la priorité invalide la conformité."""
    return sum(ventilation.get(priorite, 0) for priorite in PRIORITES_DECLASSANTES)


def statut_conformite(ventilation: dict[str, int]) -> str:
    """Statut de conformité déduit d'une ventilation par priorité.

    Seules les anomalies déclassantes invalident la conformité : une anomalie
    majeure ou mineure est comptée et listée dans le rapport, mais le fichier
    reste livrable au regard du contrôle qui l'a produite.
    """
    return CONFORME if compter_bloquantes(ventilation) == 0 else NON_CONFORME
