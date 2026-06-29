#!/usr/bin/env python3
"""
Définition des séquences XSD attendues pour chaque type RPD RecoStar.
Conforme au schéma XSD SchemaStarElecRecoStar.xsd version 1.1.

Chaque séquence modélise la contrainte xs:sequence du type correspondant,
en intégrant les éléments hérités des types parents (via xs:extension).
"""

from typing import NamedTuple

# ---------------------------------------------------------------------------
# Modèle d'un slot de séquence XSD
# ---------------------------------------------------------------------------


class SlotSequence(NamedTuple):
    """Représente un élément attendu dans une séquence XSD.

    Attributs :
        nom         : Nom local de l'élément XSD (sans namespace)
        min_occurs  : Occurrences minimales (0 = optionnel, 1 = requis)
        max_occurs  : Occurrences maximales (-1 = non borné / unbounded)
    """

    nom: str
    min_occurs: int = 1
    max_occurs: int = 1


def _requis(nom: str) -> SlotSequence:
    """Slot requis : exactement 1 occurrence."""
    return SlotSequence(nom, 1, 1)


def _optionnel(nom: str) -> SlotSequence:
    """Slot optionnel : 0 ou 1 occurrence."""
    return SlotSequence(nom, 0, 1)


def _repetable(nom: str, min_occurs: int = 0) -> SlotSequence:
    """Slot répétable : min_occurs à unbounded occurrences."""
    return SlotSequence(nom, min_occurs, -1)


# ---------------------------------------------------------------------------
# Séquences hérités des types parents (réutilisées par composition)
# ---------------------------------------------------------------------------

# ElementReseauType → reseau (1+), Commentaire (0-1)
_SEQ_ELEMENT_RESEAU: list[SlotSequence] = [
    _repetable("reseau", 1),
    _optionnel("Commentaire"),
]

# OuvrageType étend ElementReseauType → ajoute geometriesupplementaire (0+)
_SEQ_OUVRAGE: list[SlotSequence] = _SEQ_ELEMENT_RESEAU + [
    _repetable("geometriesupplementaire"),
]

# NoeudReseauType étend OuvrageType → ajoute conteneur (0-1)
_SEQ_NOEUD_RESEAU: list[SlotSequence] = _SEQ_OUVRAGE + [
    _optionnel("conteneur"),
]


# ---------------------------------------------------------------------------
# Table des séquences attendues par type RPD
# Clé : nom local de l'élément RPD (sans namespace)
# ---------------------------------------------------------------------------

SEQUENCES_RPD: dict[str, list[SlotSequence]] = {
    # --- Cheminements (extends ElementReseauType via CheminementType) ---
    "RPD_Aerien_Reco": _SEQ_ELEMENT_RESEAU
    + [
        _requis("Geometrie"),
        _requis("ModePose"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
    ],
    "RPD_Fourreau_Reco": _SEQ_ELEMENT_RESEAU
    + [
        _optionnel("CoupeType"),
        _requis("DiametreDuFourreau"),
        _optionnel("EtatCoupeType"),
        _requis("Geometrie"),
        _requis("Materiau"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _optionnel("ProfondeurMinNonReg"),
    ],
    "RPD_Galerie_Reco": _SEQ_ELEMENT_RESEAU
    + [
        _requis("Geometrie"),
        _requis("Hauteur"),
        _requis("Largeur"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _optionnel("ProfondeurMinNonReg"),
    ],
    "RPD_PleineTerre_Reco": _SEQ_ELEMENT_RESEAU
    + [
        _optionnel("CoupeType"),
        _optionnel("EtatCoupeType"),
        _requis("Geometrie"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _optionnel("ProfondeurMinNonReg"),
    ],
    "RPD_ProtectionMecanique_Reco": _SEQ_ELEMENT_RESEAU
    + [
        _optionnel("CoupeType"),
        _optionnel("EtatCoupeType"),
        _requis("Geometrie"),
        _requis("Materiau"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _optionnel("ProfondeurMinNonReg"),
    ],
    # --- Câbles (extends OuvrageType via CablesType) ---
    "RPD_CableElectrique_Reco": _SEQ_OUVRAGE
    + [
        _requis("DomaineTension"),
        _optionnel("Etiquette"),
        _requis("FonctionCable"),
        _optionnel("HierarchieBT"),
        _optionnel("Isolant"),
        _optionnel("Materiau"),
        _optionnel("NombreConducteurs"),
        _optionnel("Section"),
        _optionnel("SectionNeutre"),
        _requis("Statut"),
    ],
    "RPD_CableTelecommunication_Reco": _SEQ_OUVRAGE
    + [
        _optionnel("Capacite"),
        _optionnel("Fonction"),
        _optionnel("Section"),
        _requis("Statut"),
        _optionnel("TechnoCable"),
    ],
    "RPD_CableTerre_Reco": _SEQ_OUVRAGE
    + [
        _requis("FonctionCable"),
        _requis("Materiau"),
        _optionnel("NatureCableTerre"),
        _optionnel("noeudReseau"),
        _requis("Section"),
        _requis("Statut"),
    ],
    # --- Conteneurs (extends OuvrageType via ConteneurType) ---
    "RPD_BatimentTechnique_Reco": _SEQ_OUVRAGE
    + [
        _requis("Geometrie"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _requis("Statut"),
    ],
    "RPD_Coffret_Reco": _SEQ_OUVRAGE
    + [
        _requis("FonctionCoffret"),
        _requis("Geometrie"),
        _optionnel("ImplantationArmoire"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _requis("Statut"),
        _requis("TypeCoffret"),
    ],
    "RPD_EnceinteCloturee_Reco": _SEQ_OUVRAGE
    + [
        _requis("Geometrie"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _requis("Statut"),
    ],
    "RPD_Support_Reco": _SEQ_OUVRAGE
    + [
        _optionnel("Classe"),
        _optionnel("Effort"),
        _requis("Geometrie"),
        _optionnel("HauteurPoteau"),
        _optionnel("Matiere"),
        _requis("NatureSupport"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _requis("Statut"),
    ],
    # --- Noeuds réseau (extends OuvrageType via NoeudReseauType) ---
    "RPD_CoupeCircuitAFusibles_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("Statut"),
    ],
    "RPD_JeuBarres_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("Statut"),
    ],
    "RPD_Jonction_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("DomaineTension"),
        _optionnel("Geometrie"),
        _optionnel("PrecisionXY"),
        _optionnel("PrecisionZ"),
        _requis("Statut"),
        _requis("TypeJonction"),
    ],
    "RPD_ModuleRaccordement_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("Coupure"),
        _requis("NbPlagesOccupees"),
        _requis("noeudParent"),
        _requis("Protection"),
    ],
    "RPD_OuvrageCollectifBranchement_Reco": _SEQ_NOEUD_RESEAU
    + [
        _optionnel("Geometrie"),
        _optionnel("PrecisionXY"),
        _optionnel("PrecisionZ"),
        _requis("Statut"),
    ],
    "RPD_PointDeComptage_Reco": _SEQ_NOEUD_RESEAU
    + [
        _optionnel("Geometrie"),
        _optionnel("NumeroPRM"),
        _optionnel("PrecisionXY"),
        _optionnel("PrecisionZ"),
        _requis("Statut"),
    ],
    "RPD_PosteElectrique_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("Categorie"),
        _requis("Code"),
        _requis("InformationSupplementaire"),
        _requis("Statut"),
        _requis("TypePoste"),
    ],
    "RPD_SupportModules_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("Statut"),
    ],
    "RPD_Terre_Reco": _SEQ_NOEUD_RESEAU
    + [
        _requis("NatureTerre"),
        _optionnel("Resistance"),
        _requis("Statut"),
    ],
    # --- Types sans héritage ElementReseau ---
    "RPD_GeometrieSupplementaire_Reco": [
        _optionnel("Commentaire"),
        _repetable("Ligne3D"),
        _requis("PrecisionXY"),
        _requis("PrecisionZ"),
        _repetable("Surface3D"),
    ],
    "RPD_Materiel_Reco": [
        _requis("Fabricant"),
        _requis("Modele"),
        _requis("NumeroLot"),
        _requis("NumeroSerie"),
    ],
    "RPD_PointLeveOuvrageReseau_Reco": [
        _optionnel("ChargeGeneratrice"),
        _requis("Geometrie"),
        _optionnel("Horodatage"),
        _requis("NumeroPoint"),
        _requis("PrecisionXYnum"),
        _requis("PrecisionZnum"),
        _requis("Producteur"),
    ],
}

# Ensemble des types RPD connus (recherche O(1))
NOMS_RPD: frozenset[str] = frozenset(SEQUENCES_RPD.keys())


# ---------------------------------------------------------------------------
# Modèle d'erreur
# ---------------------------------------------------------------------------


class ErreurOrdre:
    """Erreur d'ordre ou de structure détectée dans un objet RPD."""

    __slots__ = (
        "type_rpd",
        "gml_id",
        "type_erreur",
        "position",
        "element_trouve",
        "element_attendu",
        "message",
    )

    # Sévérité fixe : le contrôle d'ordre ne produit que des erreurs (jamais
    # d'avertissement). Attribut de classe pour harmoniser le format de rapport
    # avec les autres contrôles E1xx sans alourdir le constructeur.
    severite = "ERREUR"

    def __init__(
        self,
        type_rpd: str,
        gml_id: str,
        type_erreur: str,
        position: int | None,
        element_trouve: str | None,
        element_attendu: str | None,
        message: str,
    ) -> None:
        self.type_rpd = type_rpd
        self.gml_id = gml_id
        self.type_erreur = type_erreur
        self.position = position
        self.element_trouve = element_trouve
        self.element_attendu = element_attendu
        self.message = message

    def vers_dict(self) -> dict:
        """Convertit l'erreur en dictionnaire pour sérialisation JSON."""
        return {
            "type_rpd": self.type_rpd,
            "gml_id": self.gml_id,
            "severite": self.severite,
            "type_erreur": self.type_erreur,
            "position": self.position,
            "element_trouve": self.element_trouve,
            "element_attendu": self.element_attendu,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Fonctions de validation de séquence
# ---------------------------------------------------------------------------


def _trouver_slot(nom: str, slots: list[SlotSequence], depuis: int) -> int:
    """Recherche la première correspondance de 'nom' à partir de 'depuis'.

    Retourne l'index du slot trouvé, ou -1 si absent dans les slots restants.
    """
    for i in range(depuis, len(slots)):
        if slots[i].nom == nom:
            return i
    return -1


def _signaler_slots_sautes(
    slots: list[SlotSequence],
    counts: list[int],
    seq_idx: int,
    slot_cible: int,
    type_rpd: str,
    gml_id: str,
    position: int,
    erreurs: list[ErreurOrdre],
) -> None:
    """Signale les éléments requis dont la position a été sautée lors d'un saut en avant."""
    for i in range(seq_idx, slot_cible):
        slot = slots[i]
        # Seuls les slots requis non encore atteints déclenchent une erreur
        if slot.min_occurs > counts[i]:
            msg = (
                f"Élément requis '{slot.nom}' absent ou hors séquence "
                f"(attendu avant la position {position} dans '{type_rpd}')"
            )
            erreurs.append(
                ErreurOrdre(
                    type_rpd=type_rpd,
                    gml_id=gml_id,
                    type_erreur="ELEMENT_REQUIS_MANQUANT",
                    position=position,
                    element_trouve=None,
                    element_attendu=slot.nom,
                    message=msg,
                )
            )


def _signaler_element_non_conforme(
    nom: str,
    slots: list[SlotSequence],
    seq_idx: int,
    type_rpd: str,
    gml_id: str,
    position: int,
    erreurs: list[ErreurOrdre],
) -> None:
    """Signale un élément absent des slots restants (hors ordre ou inattendu)."""
    # Vérifier si l'élément appartient à un slot déjà dépassé → hors ordre
    for i in range(seq_idx):
        if slots[i].nom == nom:
            attendu_apres = slots[seq_idx].nom if seq_idx < len(slots) else "<fin>"
            msg = (
                f"Élément '{nom}' hors séquence à la position {position} "
                f"(attendu avant '{attendu_apres}' dans '{type_rpd}')"
            )
            erreurs.append(
                ErreurOrdre(
                    type_rpd=type_rpd,
                    gml_id=gml_id,
                    type_erreur="ORDRE_INCORRECT",
                    position=position,
                    element_trouve=nom,
                    element_attendu=slots[i].nom,
                    message=msg,
                )
            )
            return

    # Élément non défini dans ce type RPD
    msg = f"Élément '{nom}' inattendu à la position {position} pour le type '{type_rpd}'"
    erreurs.append(
        ErreurOrdre(
            type_rpd=type_rpd,
            gml_id=gml_id,
            type_erreur="ELEMENT_INATTENDU",
            position=position,
            element_trouve=nom,
            element_attendu=None,
            message=msg,
        )
    )


def _signaler_slots_restants(
    slots: list[SlotSequence],
    counts: list[int],
    seq_idx: int,
    type_rpd: str,
    gml_id: str,
    erreurs: list[ErreurOrdre],
) -> None:
    """Signale les éléments requis non rencontrés après traitement de tous les enfants."""
    for i in range(seq_idx, len(slots)):
        slot = slots[i]
        if slot.min_occurs > counts[i]:
            msg = f"Élément requis '{slot.nom}' absent dans '{type_rpd}' (gml:id='{gml_id}')"
            erreurs.append(
                ErreurOrdre(
                    type_rpd=type_rpd,
                    gml_id=gml_id,
                    type_erreur="ELEMENT_REQUIS_MANQUANT",
                    position=None,
                    element_trouve=None,
                    element_attendu=slot.nom,
                    message=msg,
                )
            )


def valider_sequence(
    type_rpd: str,
    gml_id: str,
    noms_enfants: list[str],
    sequences: dict[str, list[SlotSequence]] | None = None,
) -> list[ErreurOrdre]:
    """Valide l'ordre des éléments enfants d'un objet contre une séquence XSD.

    Détecte trois types d'anomalies :
    - ORDRE_INCORRECT        : élément présent mais placé après sa position attendue
    - ELEMENT_REQUIS_MANQUANT: élément requis absent
    - ELEMENT_INATTENDU      : élément non défini dans le type

    Le paramètre `sequences` permet de réutiliser le moteur pour d'autres
    catalogues que les types RPD (par exemple Metadata et ReseauUtilite pour
    le contrôle E113). Par défaut, la table des séquences RPD est utilisée.

    Retourne une liste d'ErreurOrdre (vide si conforme).
    """
    table = sequences if sequences is not None else SEQUENCES_RPD
    slots = table.get(type_rpd, [])
    if not slots:
        return []

    erreurs: list[ErreurOrdre] = []
    seq_idx = 0
    # Pré-allocation : taille connue à l'avance
    counts: list[int] = [0] * len(slots)

    for position, nom in enumerate(noms_enfants):
        slot_idx = _trouver_slot(nom, slots, seq_idx)

        if slot_idx >= 0:
            # Signaler les slots requis sautés lors du saut en avant
            if slot_idx > seq_idx:
                _signaler_slots_sautes(
                    slots,
                    counts,
                    seq_idx,
                    slot_idx,
                    type_rpd,
                    gml_id,
                    position,
                    erreurs,
                )
            seq_idx = slot_idx
            counts[seq_idx] += 1
            # Avancer si le slot est épuisé (max_occurs borné atteint)
            slot = slots[seq_idx]
            if slot.max_occurs != -1 and counts[seq_idx] >= slot.max_occurs:
                seq_idx += 1
        else:
            _signaler_element_non_conforme(
                nom,
                slots,
                seq_idx,
                type_rpd,
                gml_id,
                position,
                erreurs,
            )

    # Vérifier les slots requis non atteints en fin de séquence
    _signaler_slots_restants(slots, counts, seq_idx, type_rpd, gml_id, erreurs)
    return erreurs
