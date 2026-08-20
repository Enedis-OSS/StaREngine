#!/usr/bin/env python3
"""
Priorités des anomalies de structuration XSD (E110-E114 / E010-E014).

Les cinq contrôles de structuration produisent toutes leurs anomalies avec la
même sévérité (`ERREUR`) : la sévérité dit *ce qui a été violé*, elle ne dit pas
*ce que la violation coûte*. Ce module ajoute cette seconde dimension — la
**priorité** — afin que quelques règles clairement identifiées soient signalées
sans invalider la livraison, pendant que toutes les autres restent bloquantes.

La priorité est portée par chaque objet d'erreur (attribut `priorite`) et vaut
`PRIORITE_PAR_DEFAUT` sauf déclaration explicite. Les deux seules dérogations en
service sont déclarées **au plus près de la règle concernée**, jamais ici :

  - `regles_valeurs.REGLES_VALEURS` → règle `E_THEME_RPD`
    (ReseauUtilite/Theme hors énumération) : priorité mineure ;
  - `regles_entete.PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN` → schemaLocation
    pointant la branche `main` du XSD : priorité majeure.

Ajouter une dérogation revient donc à poser une priorité sur la règle, sans
toucher ni au moteur de détection, ni au message d'erreur, ni à ce module.

Les libellés de priorité sont des littéraux alignés sur
`controle/synthese_controles.py` (`ORDRE_PRIORITES`, `PRIORITES_DECLASSANTES`)
mais volontairement **non importés** : les modules de ce dossier s'importent à
plat et restent exécutables seuls en ligne de commande, sans accès au paquet
parent. C'est la convention déjà retenue par les contrôles GeoJSON
(cf. `altimetrie/controle_e201.PRIORITE_ANOMALIE`).
"""

from collections.abc import Iterable
from typing import Protocol

# ---------------------------------------------------------------------------
# Échelle de priorité
# ---------------------------------------------------------------------------

# Niveaux utilisés par la structuration, du plus grave au moins grave.
PRIORITE_BLOQUANT: str = "bloquant"
PRIORITE_MAJEUR: str = "majeur"
PRIORITE_MINEUR: str = "mineur"

# Priorité appliquée à toute anomalie qui n'en déclare pas : une erreur de
# structuration invalide la conformité au schéma, elle est bloquante par nature.
PRIORITE_PAR_DEFAUT: str = PRIORITE_BLOQUANT

# Seules ces priorités déclassent un contrôle en NON_CONFORME. frozenset : test
# d'appartenance en O(1) et valeur immuable. Doit rester aligné sur
# `synthese_controles.PRIORITES_DECLASSANTES`, qui applique la même règle au
# statut de famille et au rapport PDF.
PRIORITES_DECLASSANTES: frozenset[str] = frozenset({PRIORITE_BLOQUANT})


# ---------------------------------------------------------------------------
# Statuts de conformité
# ---------------------------------------------------------------------------

CONFORME: str = "CONFORME"
NON_CONFORME: str = "NON_CONFORME"


class AnomalieStructuration(Protocol):
    """Contrat minimal attendu d'une anomalie de structuration.

    Les cinq classes d'erreur du dossier (ErreurOrdre, ErreurMetier, ErreurXsd,
    ErreurEntete, ErreurValeur) le satisfont structurellement : aucune n'a à
    hériter d'une base commune pour être ventilée par ce module.
    """

    priorite: str


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
