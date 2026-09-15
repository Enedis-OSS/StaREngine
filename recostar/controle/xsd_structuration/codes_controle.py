#!/usr/bin/env python3
"""
Identité des contrôles de structuration XSD selon la version RecoStaR.

Un même moteur de contrôle porte un code différent selon la version du format
qu'il applique : la **V1.1 est contrôlée par les codes E0110 à E0115**, la **V1.0
par les codes E0010 à E0015**. Ce module est la source de vérité de cette
correspondance ; les moteurs y lisent le code affichable, le `type_controle` du
rapport JSON et le suffixe du fichier de rapport à produire.

Le préfixe de code (« E11 » pour la V1.1, « E01 » pour la V1.0) est porté par le
`ProfilVersion` de chaque version : ajouter une version revient à déclarer son
préfixe dans son profil, sans modifier ce module ni aucun moteur.

Le rang identifie le contrôle indépendamment de la version : rang 0 = ordre de
structure, 1 = règles métier, 2 = validation XSD native, 3 = en-tête,
4 = valeurs des champs, 5 = validité des géométries, 6 et 7 = jointures,
8 = exploitabilité du document, 9 = srsDimension, 10 = présence d'ouvrages en
attente de mise en service.

**Ce module est une feuille du graphe d'imports** : il ne charge `versions`
qu'à l'appel, jamais au chargement. Le registre des versions instancie en effet
les profils, qui instancient les moteurs de règles (`regles_metier`,
`regles_valeurs`, `regles_entete`, `sequenceur_xsd`), lesquels lisent les rangs
déclarés ici pour dériver leur priorité. Un import de `versions` en tête de
module refermerait ce cycle et rendrait tout le dossier inimportable. Les rangs
étant des constantes pures, aucune raison de les faire dépendre des profils.
"""

from dataclasses import dataclass
from functools import cache

# Rang de chaque contrôle dans la famille, stable d'une version à l'autre.
RANG_ORDRE: int = 0
RANG_METIER: int = 1
RANG_XSD_NATIF: int = 2
RANG_ENTETE: int = 3
RANG_VALEURS: int = 4
RANG_GEOMETRIE: int = 5
RANG_JOINTURES: int = 6
RANG_JOINTURES_CHAMPS: int = 7
RANG_DOCUMENT: int = 8
RANG_SRS_DIMENSION: int = 9
RANG_STATUT_EN_SERVICE: int = 10

# Suffixe métier du `type_controle`, indexé par rang. Tuple : accès O(1) et
# table immuable, l'index valant directement le rang du contrôle.
SUFFIXES_TYPE: tuple[str, ...] = (
    "ORDRE",
    "METIER",
    "XSD_NATIF",
    "ENTETE",
    "VALEURS",
    "GEOMETRIE",
    "JOINTURES",
    "JOINTURES_CHAMPS",
    "DOCUMENT",
    "SRS_DIMENSION",
    "STATUT_EN_SERVICE",
)

# Nombre de contrôles de la famille, exposé pour les parcours et les tests.
NB_CONTROLES: int = len(SUFFIXES_TYPE)


def code_depuis_rang(prefixe: str, rang: int) -> str:
    """Compose le code d'un contrôle depuis le préfixe de version et son rang.

    Le dernier caractère du préfixe porte le chiffre des dizaines du code :
    « E011 » donne E0110 à E0119. Au-delà du rang 9, ce chiffre s'incrémente et
    le rang repart à zéro — « E011 » et le rang 10 donnent E0120. La
    nomenclature garde ainsi cinq caractères quel que soit le nombre de
    contrôles de la famille, là où une concaténation directe produirait E01110.
    """
    dizaine = int(prefixe[-1]) + rang // 10
    return f"{prefixe[:-1]}{dizaine}{rang % 10}"


@dataclass(frozen=True, slots=True)
class IdentiteControle:
    """Identité d'un contrôle pour une version donnée.

    Attributs :
        code            : Code affichable du contrôle ("E0110", "E0010").
        type_controle   : Valeur du champ `type_controle` du rapport JSON.
        suffixe_rapport : Suffixe du nom de fichier du rapport JSON.
    """

    code: str
    type_controle: str
    suffixe_rapport: str


# cache : le prefixe est demandé une fois par identité construite, soit à chaque
# génération de rapport, pour un registre de versions immuable.
@cache
def prefixe_version(version: str | None = None) -> str:
    """Retourne le préfixe de code d'une version (« E11 » en V1.1, « E01 » en V1.0).

    `None` désigne la version par défaut du registre. L'import de `versions` est
    différé au corps de la fonction : voir la note d'en-tête du module.
    """
    from recostar.controle.xsd_structuration.versions import VERSION_DEFAUT, resoudre_profil

    return resoudre_profil(VERSION_DEFAUT if version is None else version).prefixe_code


# cache : les identités sont demandées à chaque génération de rapport ;
# elles sont immuables et peu nombreuses (une par couple version/rang).
@cache
def identite_controle(version: str | None = None, rang: int = RANG_ORDRE) -> IdentiteControle:
    """Construit l'identité du contrôle de rang donné pour une version.

    `version` à None applique la version par défaut du registre.

    Lève `ValueError` si la version est inconnue (via `resoudre_profil`) ou si
    le rang ne correspond à aucun contrôle de la famille.
    """
    if not 0 <= rang < NB_CONTROLES:
        raise ValueError(f"Rang de contrôle XSD inconnu : {rang}. Rangs valides : 0 à {NB_CONTROLES - 1}.")

    code = code_depuis_rang(prefixe_version(version), rang)
    return IdentiteControle(
        code=code,
        type_controle=f"{code}_{SUFFIXES_TYPE[rang]}",
        suffixe_rapport=f"_controle_{code.lower()}.json",
    )


def codes_version(version: str | None = None) -> tuple[str, ...]:
    """Retourne les codes des contrôles d'une version, dans l'ordre d'exécution."""
    return tuple(identite_controle(version, rang).code for rang in range(NB_CONTROLES))
