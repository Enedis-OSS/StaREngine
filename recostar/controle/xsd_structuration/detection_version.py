#!/usr/bin/env python3
"""
Détection automatique de la version RecoStaR d'un fichier GML.

La version est déduite du jeton `RecoStar-vX.Y` présent dans l'attribut
`xsi:schemaLocation` de l'élément racine. Ce module est volontairement
**découplé** du contrôle d'en-tête E113 : E113 valide le schemaLocation selon
sa propre convention et doit pouvoir s'exécuter même sur un en-tête non
conforme, tandis que la détection se contente d'identifier la version.

Seuls les tags **canoniques** `RecoStar-v1.0` et `RecoStar-v1.1` sont reconnus.
L'ancien tag `RecoStar-v1.10` (émis par les versions antérieures du
convertisseur, désormais corrigé pour produire `v1.1`) n'est volontairement plus
détecté : un tel fichier retombe sur le repli de version par défaut côté CLI.

À défaut de tag de version, une URL pointant la **branche `main`** du dépôt
amont (`/raw/main/`) est rattachée à la **V1.0** : c'est la forme émise par les
producteurs historiques (dont AtelierStaR-Elec), dont les données suivent le
schéma V1.0. Cette reconnaissance ne vaut que pour le choix du profil de
contrôle : l'absence de tag de version reste une non-conformité d'en-tête,
signalée par le contrôle E013 (`SCHEMA_LOCATION_VERSION_INCORRECTE`).

En cas d'absence, de jeton inconnu ou de XML illisible, la détection retourne
`None` sans lever d'exception : l'appelant (CLI) décide alors du repli (version
par défaut) et laisse les contrôles signaler eux-mêmes les anomalies d'en-tête.
"""

import re
from pathlib import Path

# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
from xml.etree.ElementTree import (  # nosec B405
    ParseError,
)

import defusedxml.ElementTree as DefusedET  # type: ignore

# Attribut qualifié portant les couples (namespace, URL du schéma).
_NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_ATTR_SCHEMA_LOCATION = f"{{{_NS_XSI}}}schemaLocation"

# Valeur conventionnelle demandée en CLI pour activer la détection automatique.
JETON_AUTO = "auto"

# Extraction du numéro de version brut figurant après « RecoStar-v ».
_MOTIF_VERSION = re.compile(r"RecoStar-v(\d+(?:\.\d+)*)")

# Correspondance jeton brut (tel qu'écrit dans les fichiers) → code de version
# du registre. Seuls les tags canoniques sont reconnus ; ajouter une version
# revient à ajouter une entrée ici.
_VERSIONS_PAR_JETON: dict[str, str] = {
    "1.0": "1.0",
    "1.1": "1.1",
}

# Repli sur la branche du dépôt : les fichiers historiques ne portent pas de tag
# de version mais pointent la branche `main`, dont le contenu correspond au
# schéma V1.0. Insensible à la casse, le nom de branche n'étant pas normalisé
# selon les producteurs.
_MOTIF_BRANCHE = re.compile(r"/raw/([^/]+)/", re.IGNORECASE)

# Correspondance nom de branche → code de version du registre.
_VERSIONS_PAR_BRANCHE: dict[str, str] = {
    "main": "1.0",
}


def _lire_schema_location(chemin_gml: Path) -> str | None:
    """Lit l'attribut xsi:schemaLocation de la racine, ou None si illisible.

    Parsing durci (defusedxml) pour neutraliser les attaques XXE, cohérent avec
    les autres contrôles. Toute erreur de lecture est convertie en None : la
    détection ne doit jamais interrompre la chaîne de contrôle.
    """
    try:
        racine = DefusedET.parse(str(chemin_gml)).getroot()
    except (ParseError, OSError):
        return None
    if racine is None:
        return None
    return racine.get(_ATTR_SCHEMA_LOCATION)


def detecter_version(chemin_gml: Path) -> str | None:
    """Déduit le code de version RecoStaR d'un fichier GML.

    Retourne le code de version (« 1.0 », « 1.1 ») reconnu dans le
    schemaLocation, ou None si l'attribut est absent, illisible ou ne porte ni
    jeton de version connu ni nom de branche répertorié.

    Le tag de version est prioritaire ; à défaut, le nom de branche de l'URL
    sert de repli (`main` → V1.0).
    """
    valeur = _lire_schema_location(chemin_gml)
    if not valeur:
        return None

    correspondance = _MOTIF_VERSION.search(valeur)
    if correspondance is not None:
        version = _VERSIONS_PAR_JETON.get(correspondance.group(1))
        if version is not None:
            return version

    branche = _MOTIF_BRANCHE.search(valeur)
    if branche is None:
        return None
    return _VERSIONS_PAR_BRANCHE.get(branche.group(1).lower())
