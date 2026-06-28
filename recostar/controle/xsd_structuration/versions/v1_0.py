#!/usr/bin/env python3
"""
Profil de version RecoStaR V1.0.

Les parties **structurelles** (séquences des types RPD, énumération des SRS)
sont dérivées automatiquement du XSD V1.0 via `generateur_sequences` : tout
delta structurel V1.0↔V1.1 encodé dans le schéma (éléments renommés comme
`Ligne2.5D`/`Leve`, champ `NombrePlages`, absence du type télécom, champs câble
requis au lieu d'optionnels) est ainsi capté sans recopie.

Les parties **métier** (règles conditionnelles E111, valeurs E114) et l'en-tête
(E113) sont, elles, des deltas curés à la main par rapport au catalogue V1.1 :

- R001 (câble élec « en attente » → champs requis) est retiré : en V1.0 ces
  champs sont déjà requis par le XSD (`minOccurs=1`), donc traités par E110.
  Les règles R002/R003 sont conservées (R003 devient inerte faute de `Statut`
  sur le support en V1.0).
- L'énumération SRS plus courte de la V1.0 remplace celle de la V1.1 dans la
  règle de valeur E_SRS, sans dupliquer le reste du catalogue.
- Les séquences d'en-tête (Metadata, ReseauUtilite) sont identiques entre
  versions : elles sont réutilisées telles quelles.
"""

from pathlib import Path

from generateur_sequences import generer_enumeration, generer_sequences
from regles_entete import (
    CARDINALITES_ENTETE,
    NAMESPACES_ATTENDUS,
    SEQUENCES_ENTETE,
    TYPES_ENTETE,
)
from regles_metier import REGLES_METIER, indexer_regles_par_type
from regles_valeurs import (
    CODE_VALEUR_HORS_ENUMERATION,
    REGLES_VALEURS,
    SEVERITE_ERREUR,
    RegleValeur,
    construire_index,
)
from sequenceur_xsd import SlotSequence

from versions.profil import ProfilVersion

# Chemin du XSD officiel V1.0 (source des parties structurelles + énum SRS).
_RACINE_RECOSTAR: Path = Path(__file__).resolve().parents[3]
CHEMIN_XSD_V1_0: Path = _RACINE_RECOSTAR / "conversion" / "conversion_V1" / "xsd" / "SchemaStarElecRecoStar.xsd"

# Fragment d'URL identifiant la V1.0 dans xsi:schemaLocation (cf. conversion_V1).
FRAGMENT_URL_XSD_V1_0: str = "/raw/RecoStar-v1.0/"

# Identifiant de la règle métier propre à la V1.1 (champs câble requis sous
# condition), sans objet en V1.0 où ces champs sont structurellement requis.
_ID_REGLE_CABLE_EN_ATTENTE: str = "R001_CABLE_ELEC_EN_ATTENTE"


# ---------------------------------------------------------------------------
# Parties dérivées du XSD V1.0
# ---------------------------------------------------------------------------

SEQUENCES_RPD_V1_0: dict[str, list[SlotSequence]] = generer_sequences(CHEMIN_XSD_V1_0)
NOMS_RPD_V1_0: frozenset[str] = frozenset(SEQUENCES_RPD_V1_0)
SRS_AUTORISES_V1_0: frozenset[str] = generer_enumeration(CHEMIN_XSD_V1_0, "SRSValueType")


# ---------------------------------------------------------------------------
# Deltas métier curés (E111 et E114)
# ---------------------------------------------------------------------------


def _regles_metier_v1_0() -> tuple:
    """Catalogue métier V1.0 = catalogue V1.1 privé de la règle R001."""
    return tuple(regle for regle in REGLES_METIER if regle.identifiant != _ID_REGLE_CABLE_EN_ATTENTE)


def _regle_srs_v1_0() -> RegleValeur:
    """Règle de valeur SRS adaptée à l'énumération (plus courte) de la V1.0."""
    valeurs = SRS_AUTORISES_V1_0
    return RegleValeur(
        identifiant="E_SRS",
        types_rpd=frozenset({"Metadata"}),
        champ="SRS",
        # Closure sur l'énumération V1.0 : lookup O(1) sur frozenset.
        evaluateur=lambda v: v in valeurs,
        code_erreur=CODE_VALEUR_HORS_ENUMERATION,
        severite=SEVERITE_ERREUR,
        source="PDF §10.6.1 (V1.0)",
        description="Valeurs autorisées : " + ", ".join(sorted(valeurs)),
    )


def _catalogue_valeurs_v1_0() -> tuple[RegleValeur, ...]:
    """Catalogue de valeurs V1.0 = catalogue V1.1, règle E_SRS remplacée.

    Les règles ciblant des types absents de la V1.0 (télécom) restent
    inoffensives : elles ne sont jamais déclenchées faute d'objet correspondant.
    """
    srs = _regle_srs_v1_0()
    return tuple(srs if regle.identifiant == "E_SRS" else regle for regle in REGLES_VALEURS)


_REGLES_PAR_TYPE_V1_0 = indexer_regles_par_type(_regles_metier_v1_0())
_INDEX_VALEURS_V1_0 = construire_index(_catalogue_valeurs_v1_0())


# ---------------------------------------------------------------------------
# Assemblage du profil
# ---------------------------------------------------------------------------

PROFIL_V1_0: ProfilVersion = ProfilVersion(
    code="1.0",
    sequences_rpd=SEQUENCES_RPD_V1_0,
    noms_rpd=NOMS_RPD_V1_0,
    regles_par_type=_REGLES_PAR_TYPE_V1_0,
    types_rpd_avec_regles=frozenset(_REGLES_PAR_TYPE_V1_0),
    index_regles_valeurs=_INDEX_VALEURS_V1_0,
    types_avec_regles=frozenset(type_rpd for type_rpd, _ in _INDEX_VALEURS_V1_0),
    # En-tête identique à la V1.1 (Metadata / ReseauUtilite inchangés).
    sequences_entete=SEQUENCES_ENTETE,
    types_entete=TYPES_ENTETE,
    cardinalites_entete=CARDINALITES_ENTETE,
    srs_autorises=SRS_AUTORISES_V1_0,
    namespaces_attendus=NAMESPACES_ATTENDUS,
    fragment_url_xsd=FRAGMENT_URL_XSD_V1_0,
    chemin_xsd=CHEMIN_XSD_V1_0,
)
