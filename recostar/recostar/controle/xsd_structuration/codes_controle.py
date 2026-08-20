#!/usr/bin/env python3
"""
Identité des contrôles de structuration XSD selon la version RecoStaR.

Un même moteur de contrôle porte un code différent selon la version du format
qu'il applique : la **V1.1 est contrôlée par les codes E110 à E114**, la **V1.0
par les codes E010 à E014**. Ce module est la source de vérité de cette
correspondance ; les moteurs y lisent le code affichable, le `type_controle` du
rapport JSON et le suffixe du fichier de rapport à produire.

Le préfixe de code (« E11 » pour la V1.1, « E01 » pour la V1.0) est porté par le
`ProfilVersion` de chaque version : ajouter une version revient à déclarer son
préfixe dans son profil, sans modifier ce module ni aucun moteur.

Le rang identifie le contrôle indépendamment de la version : rang 0 = ordre de
structure, 1 = règles métier, 2 = validation XSD native, 3 = en-tête,
4 = valeurs des champs.
"""

from dataclasses import dataclass
from functools import cache

from versions import VERSION_DEFAUT, resoudre_profil

# Rang de chaque contrôle dans la famille, stable d'une version à l'autre.
RANG_ORDRE: int = 0
RANG_METIER: int = 1
RANG_XSD_NATIF: int = 2
RANG_ENTETE: int = 3
RANG_VALEURS: int = 4

# Suffixe métier du `type_controle`, indexé par rang. Tuple : accès O(1) et
# table immuable, l'index valant directement le rang du contrôle.
SUFFIXES_TYPE: tuple[str, ...] = (
    "ORDRE",
    "METIER",
    "XSD_NATIF",
    "ENTETE",
    "VALEURS",
)

# Nombre de contrôles de la famille, exposé pour les parcours et les tests.
NB_CONTROLES: int = len(SUFFIXES_TYPE)


@dataclass(frozen=True, slots=True)
class IdentiteControle:
    """Identité d'un contrôle pour une version donnée.

    Attributs :
        code            : Code affichable du contrôle ("E110", "E010").
        type_controle   : Valeur du champ `type_controle` du rapport JSON.
        suffixe_rapport : Suffixe du nom de fichier du rapport JSON.
    """

    code: str
    type_controle: str
    suffixe_rapport: str


# cache : les identités sont demandées à chaque génération de rapport ;
# elles sont immuables et peu nombreuses (une par couple version/rang).
@cache
def identite_controle(version: str = VERSION_DEFAUT, rang: int = RANG_ORDRE) -> IdentiteControle:
    """Construit l'identité du contrôle de rang donné pour une version.

    Lève `ValueError` si la version est inconnue (via `resoudre_profil`) ou si
    le rang ne correspond à aucun contrôle de la famille.
    """
    if not 0 <= rang < NB_CONTROLES:
        raise ValueError(f"Rang de contrôle XSD inconnu : {rang}. Rangs valides : 0 à {NB_CONTROLES - 1}.")

    code = f"{resoudre_profil(version).prefixe_code}{rang}"
    return IdentiteControle(
        code=code,
        type_controle=f"{code}_{SUFFIXES_TYPE[rang]}",
        suffixe_rapport=f"_controle_{code.lower()}.json",
    )


def codes_version(version: str = VERSION_DEFAUT) -> tuple[str, ...]:
    """Retourne les codes des cinq contrôles d'une version, dans l'ordre d'exécution."""
    return tuple(identite_controle(version, rang).code for rang in range(NB_CONTROLES))
