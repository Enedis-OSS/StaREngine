#!/usr/bin/env python3
"""
Correspondance des regles de structuration XSD vers les codes du verificateur.

Les controles E0110-E0115 / E0010-E0015 n'emettent pas de features GeoJSON mais des
erreurs typees par un code de regle (`NAMESPACE_MANQUANT`, `GML_ID_DUPLIQUE`,
`ELEMENT_INATTENDU`...). La correspondance y est plus fine et souvent directe,
d'ou une table locale a ce dossier plutot qu'un partage avec
`controle/codes_verificateur.py` : les modules de `xsd_structuration/`
s'importent a plat et restent executables seuls, sans acces au paquet parent.
C'est la convention deja retenue par `priorites_structuration.py`.

La table est indexee par **rang de controle** et non par code affichable : le
rang identifie le controle independamment de la version (cf. `codes_controle`),
ce qui evite de dupliquer chaque entree pour la serie E011x et la serie E001x.
"""

from functools import lru_cache

from recostar.controle.xsd_structuration.codes_controle import (
    NB_CONTROLES,
    RANG_DOCUMENT,
    RANG_ENTETE,
    RANG_GEOMETRIE,
    RANG_METIER,
    RANG_ORDRE,
    RANG_SRS_DIMENSION,
    RANG_VALEURS,
    RANG_XSD_NATIF,
    code_depuis_rang,
)

# Version du referentiel du verificateur reproduite ici, alignee sur
# `controle/codes_verificateur.VERSION_REFERENTIEL`.
VERSION_REFERENTIEL: str = "2.14.0"


# ---------------------------------------------------------------------------
# Code par defaut d'un controle
# ---------------------------------------------------------------------------

# Cinq controles emettent un code unique quelle que soit la regle violee :
#   - E0111 evalue les obligations conditionnelles de la version (E-2102) ;
#   - E0112 encapsule les erreurs natives du validateur XSD, toutes des
#     non-conformites au schema (E-1104) ;
#   - E0114 verifie les valeurs de champ, toutes hors domaine autorise (E-2100) ;
#   - E0116 signale un couple de jointure declare plusieurs fois (E-0012) ;
#   - E0117 signale un bout de jointure non renseigne (E-0013).
# E0118 et E0119 portent chacun plusieurs codes, declares regle par regle.
# Les declarer par rang evite d'enumerer leurs dizaines de codes de regle.
# Tuple indexe par rang : acces O(1) et table immuable.
CODE_PAR_DEFAUT_RANG: tuple[str | None, ...] = (
    None,  # RANG_ORDRE : depend de la regle, cf. CORRESPONDANCES_XSD
    "E-2102",  # RANG_METIER
    "E-1104",  # RANG_XSD_NATIF
    None,  # RANG_ENTETE : depend de la regle
    "E-2100",  # RANG_VALEURS
    None,  # RANG_GEOMETRIE : depend de la regle, cf. CORRESPONDANCES_XSD
    "E-0012",  # RANG_JOINTURES : un seul code, le doublon de table de jointure
    "E-0013",  # RANG_JOINTURES_CHAMPS : un bout de jointure non renseigne
    None,  # RANG_DOCUMENT : depend de la regle, cf. CORRESPONDANCES_XSD
    None,  # RANG_SRS_DIMENSION : depend de la regle, cf. CORRESPONDANCES_XSD
    "E-9700",  # RANG_STATUT_EN_SERVICE : aucun ouvrage en attente de mise en service
)


# ---------------------------------------------------------------------------
# Table (rang, code de regle) -> code d'erreur
# ---------------------------------------------------------------------------

CORRESPONDANCES_XSD: dict[tuple[int, str], str] = {
    # E0110 / E0010 — ordre et completude de la sequence des elements.
    (RANG_ORDRE, "ELEMENT_REQUIS_MANQUANT"): "E-1101",
    (RANG_ORDRE, "ELEMENT_INATTENDU"): "E-1106",
    # E0113 / E0013 — en-tete, namespaces, metadonnees, unicite du gml:id.
    (RANG_ENTETE, "SRS_INVALIDE"): "E-0003",
    (RANG_ENTETE, "GML_ID_DUPLIQUE"): "E-0008",
    (RANG_ENTETE, "SCHEMA_LOCATION_MANQUANT"): "E-0010",
    (RANG_ENTETE, "SCHEMA_LOCATION_VERSION_INCORRECTE"): "E-0010",
    (RANG_ENTETE, "NAMESPACE_MANQUANT"): "E-1103",
    (RANG_ENTETE, "NAMESPACE_URI_INCORRECTE"): "E-1103",
    (RANG_ENTETE, "CHAMP_OBLIGATOIRE_MANQUANT"): "E-1101",
    (RANG_ENTETE, "OBJET_ENTETE_MANQUANT"): "E-1107",
    # `CHAMP_INATTENDU` recouvre deux codes du verificateur : l'objet absent du
    # standard (E-1100) et le champ en trop sur un objet connu (E-1106). Le
    # moteur ne les distingue pas encore ; le second est retenu, les separer en
    # deux regles reste a faire.
    (RANG_ENTETE, "CHAMP_INATTENDU"): "E-1106",
    # E0115 / E0015 — geometries privees des positions qui les definiraient.
    # Le verificateur reserve un code a la geometrie supplementaire, dont c'est
    # la seule raison d'etre ; les autres objets relevent du code general.
    (RANG_GEOMETRIE, "GEOMETRIE_INVALIDE"): "E-1108",
    (RANG_GEOMETRIE, "GEOMSUPP_SANS_GEOMETRIE"): "E-1109",
    # E0118 / E0018 — le document lui-meme, avant tout objet. Les deux regles
    # sont exclusives : un document qui ne s'analyse pas ne livre rien a compter.
    (RANG_DOCUMENT, "DOCUMENT_ILLISIBLE"): "E-0001",
    (RANG_DOCUMENT, "DOCUMENT_VIDE"): "E-0004",
    # E0119 / E0019 — l'attribut srsDimension, en cascade sur un meme noeud :
    # declare, de la bonne valeur, puis coherent avec le nombre de coordonnees.
    (RANG_SRS_DIMENSION, "SRS_DIMENSION_ABSENTE"): "E-1201",
    (RANG_SRS_DIMENSION, "SRS_DIMENSION_INCORRECTE"): "E-1300",
    (RANG_SRS_DIMENSION, "SRS_DIMENSION_INCOHERENTE"): "E-0009",
}


# Regles emises sans equivalent dans la nomenclature du verificateur. Les
# declarer explicitement plutot que de les omettre permet au test
# d'exhaustivite d'echouer sur toute nouvelle regle qui ne serait ni
# correspondue ni ecartee. frozenset : appartenance en O(1), valeur immuable.
REGLES_SANS_CODE: frozenset[tuple[int, str]] = frozenset(
    {
        # Le verificateur ne controle pas l'ordre des elements : aucun de ses
        # codes ne vise une sequence hors ordre.
        (RANG_ORDRE, "ORDRE_INCORRECT"),
        (RANG_ENTETE, "CHAMP_HORS_ORDRE"),
        # Aucun code ne vise la duplication d'un objet d'en-tete ; E-1107 ne
        # couvre que son absence.
        (RANG_ENTETE, "OBJET_ENTETE_TROP_NOMBREUX"),
    }
)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


# Appelee une fois par erreur de structuration : le cache absorbe les jeux
# comportant plusieurs milliers d'erreurs partageant le meme code de regle.
@lru_cache(maxsize=256)
def resoudre_code_erreur_xsd(rang: int, code_regle: str | None) -> str | None:
    """Retourne le code du verificateur associe a une regle de structuration.

    La table explicite prime sur le code par defaut du controle. Retourne None
    lorsque le rang est inconnu, que la regle est declaree sans equivalent ou
    qu'aucune correspondance n'est etablie : un code absent ne doit jamais
    empecher l'emission de l'erreur.
    """
    if not 0 <= rang < NB_CONTROLES:
        return None
    if code_regle is None:
        return CODE_PAR_DEFAUT_RANG[rang]
    cle = (rang, code_regle)
    if cle in REGLES_SANS_CODE:
        return None
    return CORRESPONDANCES_XSD.get(cle, CODE_PAR_DEFAUT_RANG[rang])


def codes_possibles_rang(rang: int) -> tuple[str, ...]:
    """Retourne les codes du verificateur qu'un controle peut emettre.

    Sert a renseigner la colonne du rapport quand le controle n'a releve
    aucune anomalie : a defaut des codes reellement emis, ceux qu'il couvre.
    Les regles declarees sans equivalent n'y figurent pas, n'ayant pas de code.
    """
    if not 0 <= rang < NB_CONTROLES:
        return ()
    codes = {code for (rg, _), code in CORRESPONDANCES_XSD.items() if rg == rang}
    defaut = CODE_PAR_DEFAUT_RANG[rang]
    if defaut is not None:
        codes.add(defaut)
    return tuple(sorted(codes))


# Codes de controle valides, indexes par rang : E0110 a E0121 en V1.1, E0010 a
# E0021 en V1.0. La composition passe par `code_depuis_rang`, seul endroit qui
# sache franchir la dizaine ; la table sert de garde-fou autant que de resolution.
_RANG_PAR_CODE: dict[str, int] = {
    code_depuis_rang(prefixe, rang): rang for rang in range(NB_CONTROLES) for prefixe in ("E011", "E001")
}


def rang_depuis_code_controle(code_controle: str) -> int | None:
    """Derive le rang d'un controle depuis son code affichable.

    « E0113 » et « E0013 » designent le meme controle d'en-tete : le dernier
    caractere porte le rang, le prefixe la version du standard.

    Le code entier est confronte a la table, et non son seul dernier chiffre :
    depuis que la famille occupe les dix rangs, aucune valeur ne sort plus de
    l'echelle, et lire le dernier chiffre seul ferait d'« E0130 » un rang 0.
    """
    return _RANG_PAR_CODE.get(code_controle.upper()) if code_controle else None


# Rangs reexportes : les appelants n'ont alors pas a importer `codes_controle`
# en plus de ce module.
__all__ = [
    "CODE_PAR_DEFAUT_RANG",
    "CORRESPONDANCES_XSD",
    "RANG_ENTETE",
    "RANG_GEOMETRIE",
    "RANG_METIER",
    "RANG_ORDRE",
    "RANG_VALEURS",
    "RANG_XSD_NATIF",
    "REGLES_SANS_CODE",
    "VERSION_REFERENTIEL",
    "rang_depuis_code_controle",
    "resoudre_code_erreur_xsd",
]
