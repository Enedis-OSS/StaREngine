#!/usr/bin/env python3
"""
Registre des profils de version RecoStaR pris en charge par les contrôles XSD.

Point d'entrée unique pour obtenir un `ProfilVersion` à partir de son code de
version. Les moteurs et les CLI passent par `resoudre_profil()` afin de rester
indépendants du nombre de versions supportées.

Ajouter une version : créer `versions/vX_Y.py` exposant un `ProfilVersion`,
puis l'enregistrer dans `_PROFILS` ci-dessous. Rien d'autre n'est à modifier.
"""

from versions.profil import ProfilVersion
from versions.v1_0 import PROFIL_V1_0
from versions.v1_1 import PROFIL_V1_1

# Version appliquée par défaut quand aucune n'est précisée : préserve le
# comportement historique (les contrôles ne ciblaient que la V1.1).
VERSION_DEFAUT: str = "1.1"

# Registre code de version → profil. dict : lookup O(1) sur le code.
_PROFILS: dict[str, ProfilVersion] = {
    PROFIL_V1_0.code: PROFIL_V1_0,
    PROFIL_V1_1.code: PROFIL_V1_1,
}

# Ensemble des versions supportées, exposé pour la validation des arguments CLI.
VERSIONS_SUPPORTEES: tuple[str, ...] = tuple(_PROFILS)


def resoudre_profil(code: str = VERSION_DEFAUT) -> ProfilVersion:
    """Retourne le profil correspondant au code de version demandé.

    Lève `ValueError` avec un message explicite si le code est inconnu, afin
    que les CLI puissent signaler clairement les versions disponibles.
    """
    profil = _PROFILS.get(code)
    if profil is None:
        versions = ", ".join(sorted(_PROFILS))
        raise ValueError(f"Version RecoStaR inconnue : '{code}'. Versions supportées : {versions}.")
    return profil
