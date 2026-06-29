#!/usr/bin/env python3
"""
Définition déclarative des règles de valeurs RecoStaR RPD V1.1.

Encode trois familles de contraintes sur les valeurs portées par les
éléments enfants des objets RPD :

1. Énumérations strictes (PDF §10, listes fermées) ⟶ SEVERITE_ERREUR.
   Toute valeur hors liste viole la spécification.
2. CodeLists ouvertes (PDF §10, extensibles) ⟶ SEVERITE_AVERTISSEMENT.
   Les valeurs documentées sont les seules attendues en pratique, mais
   le standard autorise des extensions locales.
3. Contraintes de format métier (PDF §9 et §6.6) ⟶ SEVERITE_ERREUR ciblée.
   Cas où la spécification impose une valeur littérale unique (Theme=ELECTRD)
   ou un motif strict (NumeroPRM = 14 chiffres).

Architecture : chaque règle est un n-uplet immuable RegleValeur, indexé
par couple (type_rpd, champ) pour un lookup O(1) lors de l'évaluation.
Cette indexation permet le polymorphisme : le même champ « Materiau »
admet des valeurs différentes selon qu'il est porté par un câble (Alu…)
ou un cheminement (CastIron…).

Référence : "Structuration des informations attendue pour les fichiers
de récolement des ouvrages RécoStaR" V1.1.
"""

import re
from collections.abc import Callable
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Sévérités et codes d'erreur
# ---------------------------------------------------------------------------

SEVERITE_ERREUR = "ERREUR"
SEVERITE_AVERTISSEMENT = "AVERTISSEMENT"

CODE_VALEUR_HORS_ENUMERATION = "VALEUR_HORS_ENUMERATION"
CODE_VALEUR_HORS_CODELIST = "VALEUR_HORS_CODELIST"
CODE_FORMAT_INVALIDE = "FORMAT_INVALIDE"


# ---------------------------------------------------------------------------
# Énumérations strictes (PDF §10, listes fermées)
# ---------------------------------------------------------------------------

# frozenset : test d'appartenance O(1), immuable, donc thread-safe.
_ENUM_DOMAINE_TENSION: frozenset[str] = frozenset(
    {
        "BT",
        "HTA",
        "HTB",
        "Inconnu",
        "TBT",
    }
)
_ENUM_ISOLANT: frozenset[str] = frozenset(
    {
        "Thermodurcissable",
        "Reticulee",
        "Nu",
    }
)
_ENUM_MATERIAU_CABLE: frozenset[str] = frozenset(
    {
        "Alu",
        "Cuivre",
        "Alm",
        "AluAcier",
        "AlmAcier",
    }
)
_ENUM_HIERARCHIE_BT: frozenset[str] = frozenset(
    {
        "Reseau",
        "LiaisonReseau",
        "DerivationIndividuelle",
        "TronconCommun",
    }
)
# Le typo « Commissionning » (deux n) est volontaire : il reflète la
# chaîne réellement présente dans le XSD officiel StaR-Elec et dans
# tous les GML produits. Cf. regles_metier._STATUT_EN_ATTENTE pour le
# même commentaire et l'historique du bug R001/R003.
_ENUM_STATUT: frozenset[str] = frozenset(
    {
        "Decommissioned",
        "Dismantled",
        "Functional",
        "UnderCommissionning",
        "Projected",
    }
)
_ENUM_MATERIAU_CHEMINEMENT: frozenset[str] = frozenset(
    {
        "CastIron",
        "Concrete",
        "Masonry",
        "Other",
        "PE",
        "PEX",
        "PVC",
        "Steel",
    }
)
_ENUM_CLASSE_PRECISION: frozenset[str] = frozenset({"A", "B", "C"})
_ENUM_ETAT_COUPE: frozenset[str] = frozenset({"Provisoire", "Definitive"})
_ENUM_MODE_POSE: frozenset[str] = frozenset(
    {
        "EnFacade",
        "Supporte",
        "SurLeSol",
    }
)
_ENUM_TYPE_JONCTION: frozenset[str] = frozenset(
    {
        "Derivation",
        "ExtremiteReseau",
        "Jonction",
        "RemonteeAeroSouterraine",
        "EpanouissementHTA",
        "Telecom",
    }
)
_ENUM_LEVE_TYPE: frozenset[str] = frozenset(
    {
        "AltitudeGeneratrice",
        "ChargeGeneratrice",
    }
)
_ENUM_SRS: frozenset[str] = frozenset(
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

# Theme RecoStaR : §9 impose la valeur unique "ELECTRD" pour un fichier
# RPD, plus stricte que la CodeList NatureReseauValue §10.6.2.
_ENUM_THEME_RPD: frozenset[str] = frozenset({"ELECTRD"})


# ---------------------------------------------------------------------------
# CodeLists ouvertes (PDF §10, extensibles)
# ---------------------------------------------------------------------------

_CL_FONCTION_CABLE: frozenset[str] = frozenset(
    {
        "Autre",
        "Communication",
        "DistributionEnergie",
        "MiseTerre",
        "Equipotentialite",
        "MaltEquipot",
        "ProtectionCathodique",
        "TransportEnergie",
    }
)
_CL_FONCTION_TELECOM: frozenset[str] = frozenset({"RRTT", "TLC"})
_CL_TECHNO_CABLE: frozenset[str] = frozenset({"Cuivre", "Fibre"})
_CL_NATURE_CABLE_TERRE: frozenset[str] = frozenset(
    {
        "CuivreNu",
        "CuivreIsol",
        "Sans",
        "VertJaune",
    }
)
_CL_IMPLANTATION_ARMOIRE: frozenset[str] = frozenset(
    {
        "Encastree",
        "IntegreeDansLocal",
        "Saillie",
        "SurSocleAluminium",
        "SurSocleBeton",
        "SurSoclePolyester",
    }
)
_CL_TYPE_COFFRET: frozenset[str] = frozenset(
    {
        "RMBT300",
        "RMBT450",
        "RMBT600",
        "CIBE",
        "CGV",
        "ECP2D",
        "ECP3D",
        "ArmoireComptage",
        "Telecom",
        "Autre",
    }
)
_CL_FONCTION_COFFRET: frozenset[str] = frozenset(
    {
        "Manoeuvrable",
        "Separable",
    }
)
_CL_NATURE_SUPPORT: frozenset[str] = frozenset(
    {
        "Poteau",
        "Facade",
        "Autre",
    }
)
_CL_MATIERE: frozenset[str] = frozenset(
    {
        "Autre",
        "Beton",
        "Bois",
        "Metal",
    }
)
_CL_CLASSE_SUPPORT: frozenset[str] = frozenset(
    {
        "A",
        "B",
        "C",
        "CFX",
        "CFY",
        "CFZ",
        "CH",
        "D",
        "E",
        "ER",
        "HS",
        "JA",
        "JB",
        "JC",
        "JD",
        "JE",
        "JER",
        "JS",
        "M",
        "PA",
        "PB",
        "PC",
        "PCH",
        "PCHX",
        "PD",
        "PE",
        "PER",
        "PJA",
        "PJB",
        "PJC",
        "PJD",
        "PJE",
        "PJER",
        "PJS",
        "PJX",
        "PM",
        "PS",
        "PX",
        "S",
    }
)
_CL_NATURE_TERRE: frozenset[str] = frozenset(
    {
        "TerreMasses",
        "TerreNeutre",
    }
)
_CL_CATEGORIE_POSTE: frozenset[str] = frozenset(
    {
        "Distribution",
        "Manoeuvre",
        "PosteSource",
        "RepartitionHTA",
    }
)
_CL_TYPE_POSTE: frozenset[str] = frozenset(
    {
        "ACM",
        "ACMD",
        "AC3M",
        "ACT",
        "AC3T",
        "CB",
        "CC",
        "CH",
        "IM",
        "EN",
        "PSSA",
        "PSSB",
        "PRCS",
        "PUIE",
        "H6",
        "PO",
        "RC",
        "RS",
        "UC",
        "UP",
        "GRSC",
        "GR1",
        "GR2A",
        "GR2B",
        "GR2C",
        "GR2D",
        "GR2E",
        "GR2F",
        "GR3",
        "GHTA",
    }
)


# ---------------------------------------------------------------------------
# Familles de types RPD partageant une même règle
# ---------------------------------------------------------------------------

# Statut : tous les ouvrages sauf RPD_ModuleRaccordement_Reco (qui ne le porte
# pas selon sa séquence XSD).
_TYPES_AVEC_STATUT: frozenset[str] = frozenset(
    {
        "RPD_CableElectrique_Reco",
        "RPD_CableTelecommunication_Reco",
        "RPD_CableTerre_Reco",
        "RPD_BatimentTechnique_Reco",
        "RPD_Coffret_Reco",
        "RPD_EnceinteCloturee_Reco",
        "RPD_Support_Reco",
        "RPD_CoupeCircuitAFusibles_Reco",
        "RPD_JeuBarres_Reco",
        "RPD_Jonction_Reco",
        "RPD_OuvrageCollectifBranchement_Reco",
        "RPD_PointDeComptage_Reco",
        "RPD_PosteElectrique_Reco",
        "RPD_SupportModules_Reco",
        "RPD_Terre_Reco",
    }
)

# Classes de précision : cheminements, conteneurs, certains nœuds, géométrie sup.
_TYPES_AVEC_PRECISION: frozenset[str] = frozenset(
    {
        "RPD_Aerien_Reco",
        "RPD_Fourreau_Reco",
        "RPD_Galerie_Reco",
        "RPD_PleineTerre_Reco",
        "RPD_ProtectionMecanique_Reco",
        "RPD_BatimentTechnique_Reco",
        "RPD_Coffret_Reco",
        "RPD_EnceinteCloturee_Reco",
        "RPD_Support_Reco",
        "RPD_Jonction_Reco",
        "RPD_OuvrageCollectifBranchement_Reco",
        "RPD_PointDeComptage_Reco",
        "RPD_GeometrieSupplementaire_Reco",
    }
)


# ---------------------------------------------------------------------------
# Modèles de règle et fabriques
# ---------------------------------------------------------------------------


# Signature de l'évaluateur : vrai si la valeur respecte la règle.
Evaluateur = Callable[[str], bool]


class RegleValeur(NamedTuple):
    """Règle de validation portant sur la valeur d'un champ d'un type RPD.

    Attributs :
        identifiant      : Code unique pour traçabilité (ex: "E_DOMAINE_TENSION")
        types_rpd        : Ensemble des types RPD qui portent ce champ
        champ            : Nom local du champ (ex: "DomaineTension")
        evaluateur       : Fonction (str -> bool) ; vrai si la valeur est conforme
        code_erreur      : Code de la taxonomie d'erreur (VALEUR_HORS_ENUMERATION…)
        severite         : SEVERITE_ERREUR ou SEVERITE_AVERTISSEMENT
        source           : Référence PDF pour traçabilité
        description      : Description lisible des valeurs/format attendus
    """

    identifiant: str
    types_rpd: frozenset[str]
    champ: str
    evaluateur: Evaluateur
    code_erreur: str
    severite: str
    source: str
    description: str


def _description_enum(valeurs: frozenset[str]) -> str:
    """Liste triée des valeurs autorisées, pour message d'erreur lisible."""
    return "Valeurs autorisées : " + ", ".join(sorted(valeurs))


def _regle_enum(
    identifiant: str,
    types_rpd: frozenset[str],
    champ: str,
    valeurs: frozenset[str],
    *,
    severite: str,
    source: str,
    code_erreur: str = CODE_VALEUR_HORS_ENUMERATION,
) -> RegleValeur:
    """Fabrique : règle d'appartenance à un ensemble fermé/ouvert de valeurs.

    L'évaluateur capture `valeurs` via closure ; lookup O(1) sur frozenset.
    """
    return RegleValeur(
        identifiant=identifiant,
        types_rpd=types_rpd,
        champ=champ,
        evaluateur=lambda v: v in valeurs,
        code_erreur=code_erreur,
        severite=severite,
        source=source,
        description=_description_enum(valeurs),
    )


def _regle_motif(
    identifiant: str,
    types_rpd: frozenset[str],
    champ: str,
    motif: str,
    *,
    severite: str,
    source: str,
    description: str,
) -> RegleValeur:
    """Fabrique : règle de conformité à une expression régulière.

    Le motif est pré-compilé une seule fois (au chargement du module) puis
    réutilisé par fullmatch : évite la recompilation à chaque évaluation.
    """
    motif_compile = re.compile(motif)
    return RegleValeur(
        identifiant=identifiant,
        types_rpd=types_rpd,
        champ=champ,
        evaluateur=lambda v: bool(motif_compile.fullmatch(v)),
        code_erreur=CODE_FORMAT_INVALIDE,
        severite=severite,
        source=source,
        description=description,
    )


# ---------------------------------------------------------------------------
# Catalogue déclaratif des règles V1.1
# ---------------------------------------------------------------------------

REGLES_VALEURS: tuple[RegleValeur, ...] = (
    # ----- Énumérations strictes (PDF §10) — ERREUR -----
    _regle_enum(
        "E_DOMAINE_TENSION",
        frozenset({"RPD_CableElectrique_Reco", "RPD_Jonction_Reco"}),
        "DomaineTension",
        _ENUM_DOMAINE_TENSION,
        severite=SEVERITE_ERREUR,
        source="PDF §10.1.1",
    ),
    _regle_enum(
        "E_ISOLANT",
        frozenset({"RPD_CableElectrique_Reco"}),
        "Isolant",
        _ENUM_ISOLANT,
        severite=SEVERITE_ERREUR,
        source="PDF §10.1.2",
    ),
    _regle_enum(
        "E_MATERIAU_CABLE",
        frozenset({"RPD_CableElectrique_Reco", "RPD_CableTerre_Reco"}),
        "Materiau",
        _ENUM_MATERIAU_CABLE,
        severite=SEVERITE_ERREUR,
        source="PDF §10.1.3",
    ),
    _regle_enum(
        "E_HIERARCHIE_BT",
        frozenset({"RPD_CableElectrique_Reco"}),
        "HierarchieBT",
        _ENUM_HIERARCHIE_BT,
        severite=SEVERITE_ERREUR,
        source="PDF §10.1.4",
    ),
    _regle_enum(
        "E_STATUT",
        _TYPES_AVEC_STATUT,
        "Statut",
        _ENUM_STATUT,
        severite=SEVERITE_ERREUR,
        source="PDF §10.1.5",
    ),
    _regle_enum(
        "E_MATERIAU_CHEMINEMENT",
        frozenset({"RPD_Fourreau_Reco", "RPD_ProtectionMecanique_Reco"}),
        "Materiau",
        _ENUM_MATERIAU_CHEMINEMENT,
        severite=SEVERITE_ERREUR,
        source="PDF §10.2.1",
    ),
    _regle_enum(
        "E_PRECISION_XY",
        _TYPES_AVEC_PRECISION,
        "PrecisionXY",
        _ENUM_CLASSE_PRECISION,
        severite=SEVERITE_ERREUR,
        source="PDF §10.2.2",
    ),
    _regle_enum(
        "E_PRECISION_Z",
        _TYPES_AVEC_PRECISION,
        "PrecisionZ",
        _ENUM_CLASSE_PRECISION,
        severite=SEVERITE_ERREUR,
        source="PDF §10.2.2",
    ),
    _regle_enum(
        "E_ETAT_COUPE_TYPE",
        frozenset(
            {
                "RPD_Fourreau_Reco",
                "RPD_PleineTerre_Reco",
                "RPD_ProtectionMecanique_Reco",
            }
        ),
        "EtatCoupeType",
        _ENUM_ETAT_COUPE,
        severite=SEVERITE_ERREUR,
        source="PDF §10.2.3",
    ),
    _regle_enum(
        "E_MODE_POSE",
        frozenset({"RPD_Aerien_Reco"}),
        "ModePose",
        _ENUM_MODE_POSE,
        severite=SEVERITE_ERREUR,
        source="PDF §10.2.4",
    ),
    _regle_enum(
        "E_TYPE_JONCTION",
        frozenset({"RPD_Jonction_Reco"}),
        "TypeJonction",
        _ENUM_TYPE_JONCTION,
        severite=SEVERITE_ERREUR,
        source="PDF §10.4.1",
    ),
    _regle_enum(
        "E_LEVE_TYPE",
        frozenset({"RPD_PointLeveOuvrageReseau_Reco"}),
        "LeveType",
        _ENUM_LEVE_TYPE,
        severite=SEVERITE_ERREUR,
        source="PDF §10.5.1",
    ),
    _regle_enum(
        "E_SRS",
        frozenset({"Metadata"}),
        "SRS",
        _ENUM_SRS,
        severite=SEVERITE_ERREUR,
        source="PDF §10.6.1",
    ),
    # ----- Contraintes RPD-spécifiques plus strictes que le XSD/CodeList -----
    _regle_enum(
        "E_THEME_RPD",
        frozenset({"ReseauUtilite"}),
        "Theme",
        _ENUM_THEME_RPD,
        severite=SEVERITE_ERREUR,
        source="PDF §9",
    ),
    _regle_motif(
        "F_NUMERO_PRM",
        frozenset({"RPD_PointDeComptage_Reco"}),
        "NumeroPRM",
        r"\d{14}",
        severite=SEVERITE_ERREUR,
        source="PDF §6.6",
        description="14 chiffres exactement (CharacterString 14 chiffres)",
    ),
    # ----- CodeLists ouvertes (PDF §10) — AVERTISSEMENT -----
    _regle_enum(
        "C_FONCTION_CABLE",
        frozenset({"RPD_CableElectrique_Reco", "RPD_CableTerre_Reco"}),
        "FonctionCable",
        _CL_FONCTION_CABLE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.1.6",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_FONCTION_TELECOM",
        frozenset({"RPD_CableTelecommunication_Reco"}),
        "Fonction",
        _CL_FONCTION_TELECOM,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.1.7",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_TECHNO_CABLE",
        frozenset({"RPD_CableTelecommunication_Reco"}),
        "TechnoCable",
        _CL_TECHNO_CABLE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.1.8",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_NATURE_CABLE_TERRE",
        frozenset({"RPD_CableTerre_Reco"}),
        "NatureCableTerre",
        _CL_NATURE_CABLE_TERRE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.1.9",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_IMPLANTATION_ARMOIRE",
        frozenset({"RPD_Coffret_Reco"}),
        "ImplantationArmoire",
        _CL_IMPLANTATION_ARMOIRE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.1",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_TYPE_COFFRET",
        frozenset({"RPD_Coffret_Reco"}),
        "TypeCoffret",
        _CL_TYPE_COFFRET,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.2",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_FONCTION_COFFRET",
        frozenset({"RPD_Coffret_Reco"}),
        "FonctionCoffret",
        _CL_FONCTION_COFFRET,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.3",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_NATURE_SUPPORT",
        frozenset({"RPD_Support_Reco"}),
        "NatureSupport",
        _CL_NATURE_SUPPORT,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.4",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_MATIERE",
        frozenset({"RPD_Support_Reco"}),
        "Matiere",
        _CL_MATIERE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.5",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_CLASSE_SUPPORT",
        frozenset({"RPD_Support_Reco"}),
        "Classe",
        _CL_CLASSE_SUPPORT,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.3.6",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_NATURE_TERRE",
        frozenset({"RPD_Terre_Reco"}),
        "NatureTerre",
        _CL_NATURE_TERRE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.4.2",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_CATEGORIE_POSTE",
        frozenset({"RPD_PosteElectrique_Reco"}),
        "Categorie",
        _CL_CATEGORIE_POSTE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.4.3",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
    _regle_enum(
        "C_TYPE_POSTE",
        frozenset({"RPD_PosteElectrique_Reco"}),
        "TypePoste",
        _CL_TYPE_POSTE,
        severite=SEVERITE_AVERTISSEMENT,
        source="PDF §10.4.4",
        code_erreur=CODE_VALEUR_HORS_CODELIST,
    ),
)


# ---------------------------------------------------------------------------
# Pré-indexation pour lookup O(1)
# ---------------------------------------------------------------------------


def construire_index(
    regles: tuple[RegleValeur, ...] = REGLES_VALEURS,
) -> dict[tuple[str, str], RegleValeur]:
    """Construit l'index (type_rpd, champ) → RegleValeur.

    Détecte les conflits de catalogue à l'import du module (un même
    couple (type, champ) ne peut être couvert que par une seule règle).
    Échec rapide = bug catalogue impossible à manquer en CI.

    Le paramètre `regles` permet d'indexer le catalogue d'une autre version
    (V1.0) avec le même contrôle de cohérence : la logique d'indexation n'est
    pas dupliquée dans le module `versions`.
    """
    index: dict[tuple[str, str], RegleValeur] = {}
    for regle in regles:
        for type_rpd in regle.types_rpd:
            cle = (type_rpd, regle.champ)
            if cle in index:
                raise ValueError(
                    f"Catalogue regles_valeurs incohérent : couple {cle} "
                    f"couvert par {index[cle].identifiant} ET {regle.identifiant}"
                )
            index[cle] = regle
    return index


_INDEX_REGLES: dict[tuple[str, str], RegleValeur] = construire_index()

# Ensembles de lookup pour filtrer rapidement les feature members non concernés.
TYPES_AVEC_REGLES: frozenset[str] = frozenset(cle[0] for cle in _INDEX_REGLES)


# ---------------------------------------------------------------------------
# Type d'erreur de valeur
# ---------------------------------------------------------------------------


class ErreurValeur:
    """Erreur de valeur détectée sur un champ d'un objet RPD."""

    # __slots__ : économie mémoire significative sur fichiers à milliers
    # d'erreurs (typique d'un GML mal calibré post-conversion).
    __slots__ = (
        "type_rpd",
        "gml_id",
        "champ",
        "valeur_trouvee",
        "code",
        "severite",
        "regle",
        "source",
        "message",
    )

    def __init__(
        self,
        type_rpd: str,
        gml_id: str,
        champ: str,
        valeur_trouvee: str,
        code: str,
        severite: str,
        regle: str,
        source: str,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        self.gml_id = gml_id
        self.champ = champ
        self.valeur_trouvee = valeur_trouvee
        self.code = code
        self.severite = severite
        self.regle = regle
        self.source = source
        self.message = message

    def vers_dict(self) -> dict:
        """Sérialise l'erreur en dictionnaire pour le rapport JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "champ": self.champ,
            "valeur_trouvee": self.valeur_trouvee,
            "code": self.code,
            "severite": self.severite,
            "regle": self.regle,
            "source": self.source,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Moteur d'évaluation
# ---------------------------------------------------------------------------


def _construire_erreur(
    regle: RegleValeur,
    type_rpd: str,
    gml_id: str,
    valeur: str,
) -> ErreurValeur:
    """Construit une ErreurValeur à partir d'une règle violée."""
    return ErreurValeur(
        type_rpd=type_rpd,
        gml_id=gml_id,
        champ=regle.champ,
        valeur_trouvee=valeur,
        code=regle.code_erreur,
        severite=regle.severite,
        regle=regle.identifiant,
        source=regle.source,
        message=(
            f"Valeur '{valeur}' invalide pour {type_rpd}/{regle.champ}. {regle.description} (source : {regle.source})."
        ),
    )


def evaluer_valeur(
    type_rpd: str,
    champ: str,
    valeur: str | None,
    gml_id: str,
    index: dict[tuple[str, str], RegleValeur] | None = None,
) -> ErreurValeur | None:
    """Évalue une valeur portée par un champ.

    Retourne None si :
    - aucune règle ne concerne (type_rpd, champ) ;
    - la valeur est absente (None ou chaîne vide) — l'absence est traitée
      par les contrôles E110 (manquant) ou E111 (conditionnellement requis) ;
    - la valeur est conforme à la règle.

    Retourne une ErreurValeur sinon.

    Le paramètre `index` sélectionne le catalogue de valeurs à appliquer.
    Par défaut, le catalogue V1.1 du module ; une autre version (V1.0) y
    injecte son propre index.
    """
    table = index if index is not None else _INDEX_REGLES
    regle = table.get((type_rpd, champ))
    if regle is None:
        return None
    if valeur is None or not valeur.strip():
        return None
    if regle.evaluateur(valeur):
        return None
    return _construire_erreur(regle, type_rpd, gml_id, valeur)
