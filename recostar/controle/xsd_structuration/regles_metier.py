#!/usr/bin/env python3
"""
Définition déclarative des règles métier RecoStaR RPD V1.1.

Ces règles complètent la validation XSD (contrôle E110) en encodant les
obligations conditionnelles non exprimables dans le schéma XSD : champs
requis selon le statut de l'ouvrage, son domaine de tension, sa nature, etc.

Référence : "Structuration des informations attendue pour les fichiers
de récolement des ouvrages RécoStaR" V1.1.

Architecture évolutive : une règle est un n-uplet immuable (RegleMetier)
combinant un déclencheur (fonction sur les valeurs) et la liste des champs
requis quand le déclencheur est vrai. Ajouter une règle = ajouter une ligne
dans REGLES_METIER, sans toucher au moteur.
"""

from collections.abc import Callable, Mapping
from typing import NamedTuple

from priorites_structuration import PRIORITE_PAR_DEFAUT

# ---------------------------------------------------------------------------
# Type d'erreur métier
# ---------------------------------------------------------------------------


class ErreurMetier:
    """Erreur métier : champ requis manquant sous condition contextuelle."""

    # __slots__ : économie mémoire significative lorsqu'on instancie plusieurs
    # milliers d'erreurs lors du parcours d'un gros GML.
    __slots__ = (
        "type_rpd",
        "gml_id",
        "regle",
        "champ_attendu",
        "contexte",
        "message",
    )

    # Sévérité fixe : une obligation métier non respectée est toujours une
    # erreur. Attribut de classe pour homogénéiser le rapport JSON avec E114.
    severite = "ERREUR"

    # Priorité fixe : un champ requis sous condition et absent rend l'ouvrage
    # inexploitable, aucune dérogation n'est prévue pour ce contrôle.
    priorite = PRIORITE_PAR_DEFAUT

    def __init__(
        self,
        type_rpd: str,
        gml_id: str,
        regle: str,
        champ_attendu: str,
        contexte: str,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        self.gml_id = gml_id
        self.regle = regle
        self.champ_attendu = champ_attendu
        self.contexte = contexte
        self.message = message

    def vers_dict(self) -> dict:
        """Sérialise l'erreur en dictionnaire pour le rapport JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "priorite": self.priorite,
            "regle": self.regle,
            "champ_attendu": self.champ_attendu,
            "contexte": self.contexte,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Modèle d'une règle métier
# ---------------------------------------------------------------------------


# Signature d'un déclencheur : reçoit le mapping des valeurs extraites du RPD,
# retourne vrai si la règle s'applique au contexte courant. Mapping (et non
# dict) est utilisé car le paramètre est en lecture seule et covariant sur le
# type des valeurs : un dict[str, str] reste ainsi acceptable.
Declencheur = Callable[[Mapping[str, str | None]], bool]


class RegleMetier(NamedTuple):
    """Règle métier conditionnelle pour un type RPD.

    Attributs :
        identifiant   : Code unique pour traçabilité (ex: "R001_CABLE_EN_ATTENTE")
        type_rpd      : Type RPD ciblé (ex: "RPD_CableElectrique_Reco")
        declencheur   : Fonction (valeurs) -> bool qui décide de l'applicabilité
        champs_requis : Champs devenant requis quand le déclencheur est vrai
        contexte      : Description du contexte (intégrée au message d'erreur)
    """

    identifiant: str
    type_rpd: str
    declencheur: Declencheur
    champs_requis: tuple[str, ...]
    contexte: str


# ---------------------------------------------------------------------------
# Déclencheurs (fonctions locales réutilisables)
# ---------------------------------------------------------------------------

# Valeur normalisée du statut « En attente de mise en exploitation » issue
# de l'énumération ConditionOfFacilityValueRecoType (cf. XSD ligne 112 et
# PDF §10.1.5). Le typo « Commissionning » (deux n) est volontaire : il
# reflète la chaîne réellement présente dans le XSD officiel StaR-Elec et
# dans tous les GML produits par les outils conformes. Ne pas « corriger »
# en « UnderCommissioning » sous peine de désactiver silencieusement R001
# et R003.
_STATUT_EN_ATTENTE = "UnderCommissionning"


def _statut_en_attente(valeurs: Mapping[str, str | None]) -> bool:
    """Vrai si l'ouvrage est au statut « En attente de mise en exploitation »."""
    return valeurs.get("Statut") == _STATUT_EN_ATTENTE


def _domaine_tension_bt(valeurs: Mapping[str, str | None]) -> bool:
    """Vrai si le domaine de tension est BT (Basse Tension)."""
    return valeurs.get("DomaineTension") == "BT"


def _support_poteau_en_attente(valeurs: Mapping[str, str | None]) -> bool:
    """Vrai si le support est de nature « Poteau » et au statut « En attente »."""
    # Combinaison de deux conditions : nature physique + statut administratif.
    return valeurs.get("NatureSupport") == "Poteau" and _statut_en_attente(valeurs)


# ---------------------------------------------------------------------------
# Catalogue déclaratif des règles métier V1.1
# ---------------------------------------------------------------------------

# tuple immuable : empêche toute modification accidentelle à l'exécution.
REGLES_METIER: tuple[RegleMetier, ...] = (
    RegleMetier(
        identifiant="R001_CABLE_ELEC_EN_ATTENTE",
        type_rpd="RPD_CableElectrique_Reco",
        declencheur=_statut_en_attente,
        # Cf. PDF V1.1 §3.1 : NombreConducteurs, Section, Isolant, Materiau
        # deviennent obligatoires pour les ouvrages en attente d'exploitation.
        champs_requis=("NombreConducteurs", "Section", "Isolant", "Materiau"),
        contexte="câble électrique au statut « En attente de mise en exploitation »",
    ),
    RegleMetier(
        identifiant="R002_CABLE_ELEC_BT",
        type_rpd="RPD_CableElectrique_Reco",
        declencheur=_domaine_tension_bt,
        # PDF V1.1 §3.1 : HierarchieBT obligatoire au niveau BT.
        champs_requis=("HierarchieBT",),
        contexte="câble électrique au domaine de tension BT",
    ),
    RegleMetier(
        identifiant="R003_SUPPORT_POTEAU_EN_ATTENTE",
        type_rpd="RPD_Support_Reco",
        declencheur=_support_poteau_en_attente,
        # PDF V1.1 §5.4 : Classe, Effort, HauteurPoteau, Matiere obligatoires
        # pour les poteaux en attente d'exploitation (pas pour les façades).
        champs_requis=("Classe", "Effort", "HauteurPoteau", "Matiere"),
        contexte="support de type poteau au statut « En attente de mise en exploitation »",
    ),
)


# ---------------------------------------------------------------------------
# Pré-indexation pour lookup O(1) par type RPD
# ---------------------------------------------------------------------------


def indexer_regles_par_type(
    regles: tuple[RegleMetier, ...] = REGLES_METIER,
) -> dict[str, tuple[RegleMetier, ...]]:
    """Construit l'index type_rpd -> tuple des règles applicables.

    Pré-calculé au chargement du module pour éviter une boucle sur l'ensemble
    des règles à chaque évaluation (lookup direct O(1) au lieu de O(n)).

    Le paramètre `regles` permet de bâtir l'index d'un catalogue de version
    différente (V1.0) sans dupliquer la logique d'indexation : c'est le
    support multi-version réutilisé par le module `versions`.
    """
    accumulateur: dict[str, list[RegleMetier]] = {}
    for regle in regles:
        accumulateur.setdefault(regle.type_rpd, []).append(regle)
    # Conversion finale en tuples immuables.
    return {tr: tuple(regles_type) for tr, regles_type in accumulateur.items()}


REGLES_PAR_TYPE: dict[str, tuple[RegleMetier, ...]] = indexer_regles_par_type()

# Ensemble des types RPD soumis à au moins une règle métier (test d'appartenance O(1)).
TYPES_RPD_AVEC_REGLES: frozenset[str] = frozenset(REGLES_PAR_TYPE.keys())


# ---------------------------------------------------------------------------
# Moteur d'évaluation
# ---------------------------------------------------------------------------


def _champ_present(valeurs: Mapping[str, str | None], champ: str) -> bool:
    """Indique si un champ porte une valeur exploitable.

    Considère comme manquant : champ absent du dict, valeur None, chaîne vide
    après strip. Préserve les valeurs "0" et autres littéraux non vides.
    """
    valeur = valeurs.get(champ)
    if valeur is None:
        return False
    # Une chaîne ne contenant que des espaces est traitée comme absente.
    return bool(valeur.strip())


def _construire_erreur(
    regle: RegleMetier,
    type_rpd: str,
    gml_id: str,
    champ: str,
) -> ErreurMetier:
    """Construit une ErreurMetier à partir d'une règle déclenchée et d'un champ manquant."""
    message = f"Champ requis '{champ}' manquant pour {regle.contexte} (règle {regle.identifiant})"
    return ErreurMetier(
        type_rpd=type_rpd,
        gml_id=gml_id,
        regle=regle.identifiant,
        champ_attendu=champ,
        contexte=regle.contexte,
        message=message,
    )


def evaluer_regles(
    type_rpd: str,
    gml_id: str,
    valeurs: Mapping[str, str | None],
    regles_par_type: dict[str, tuple[RegleMetier, ...]] | None = None,
) -> list[ErreurMetier]:
    """Évalue toutes les règles métier applicables à un objet RPD.

    Pour chaque règle dont le déclencheur s'active, vérifie la présence des
    champs requis. Génère une ErreurMetier distincte par champ manquant
    (utile pour un rapport actionnable).

    Args :
        type_rpd        : Nom local du type RPD (sans namespace)
        gml_id          : Identifiant gml:id de l'objet
        valeurs         : Dictionnaire {nom_champ : valeur | None}
        regles_par_type : Index des règles à appliquer. Par défaut, le
                          catalogue V1.1 du module. Une autre version (V1.0)
                          passe ici son propre index sans toucher au moteur.

    Retourne :
        Liste d'erreurs métier (vide si conforme).
    """
    table = regles_par_type if regles_par_type is not None else REGLES_PAR_TYPE
    regles_applicables = table.get(type_rpd)
    if regles_applicables is None:
        return []

    erreurs: list[ErreurMetier] = []
    for regle in regles_applicables:
        # Filtrage rapide : si le déclencheur est faux, on ne vérifie aucun champ.
        if not regle.declencheur(valeurs):
            continue
        for champ in regle.champs_requis:
            if not _champ_present(valeurs, champ):
                erreurs.append(_construire_erreur(regle, type_rpd, gml_id, champ))
    return erreurs
