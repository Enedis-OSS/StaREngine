"""
Tests unitaires du module sequenceur_xsd.
Couvre la validation de séquences XSD pour les types RPD RecoStar.
"""

import pytest
from sequenceur_xsd import (
    NOMS_RPD,
    SEQUENCES_RPD,
    ErreurOrdre,
    SlotSequence,
    _optionnel,
    _repetable,
    _requis,
    _trouver_slot,
    valider_sequence,
)

# ---------------------------------------------------------------------------
# Tests des constantes et structures de données
# ---------------------------------------------------------------------------


class TestConstantes:
    """Tests des constantes du module."""

    def test_noms_rpd_est_frozenset(self):
        """Vérifie que NOMS_RPD est un frozenset pour lookup O(1)."""
        assert isinstance(NOMS_RPD, frozenset)

    def test_noms_rpd_non_vide(self):
        """Vérifie que NOMS_RPD contient des types RPD."""
        assert len(NOMS_RPD) > 0

    def test_noms_rpd_coherent_avec_sequences(self):
        """Vérifie que NOMS_RPD correspond exactement aux clés de SEQUENCES_RPD."""
        assert NOMS_RPD == frozenset(SEQUENCES_RPD.keys())

    def test_aucun_type_ep_dans_noms_rpd(self):
        """Vérifie qu'aucun type EP n'est présent dans les séquences RPD."""
        for nom in NOMS_RPD:
            assert not nom.startswith("EP_"), f"Type EP inattendu : {nom}"

    def test_tous_types_rpd_commencent_par_rpd(self):
        """Vérifie que tous les types commencent par RPD_."""
        for nom in NOMS_RPD:
            assert nom.startswith("RPD_"), f"Type non RPD inattendu : {nom}"

    def test_types_rpd_attendus_presents(self):
        """Vérifie la présence des types RPD principaux."""
        types_attendus = {
            "RPD_Aerien_Reco",
            "RPD_CableElectrique_Reco",
            "RPD_Coffret_Reco",
            "RPD_Jonction_Reco",
            "RPD_GeometrieSupplementaire_Reco",
            "RPD_Materiel_Reco",
            "RPD_PointLeveOuvrageReseau_Reco",
        }
        assert types_attendus <= NOMS_RPD


# ---------------------------------------------------------------------------
# Tests des constructeurs de slots
# ---------------------------------------------------------------------------


class TestConstructeursSlots:
    """Tests des fonctions de création de slots."""

    def test_requis_cree_slot_requis(self):
        """Vérifie que _requis crée un slot avec min=1 et max=1."""
        slot = _requis("Statut")
        assert slot.nom == "Statut"
        assert slot.min_occurs == 1
        assert slot.max_occurs == 1

    def test_optionnel_cree_slot_optionnel(self):
        """Vérifie que _optionnel crée un slot avec min=0 et max=1."""
        slot = _optionnel("Commentaire")
        assert slot.nom == "Commentaire"
        assert slot.min_occurs == 0
        assert slot.max_occurs == 1

    def test_repetable_cree_slot_repete_zero_plus(self):
        """Vérifie que _repetable() crée un slot 0+ (min=0, max=-1)."""
        slot = _repetable("reseau")
        assert slot.nom == "reseau"
        assert slot.min_occurs == 0
        assert slot.max_occurs == -1

    def test_repetable_avec_min_un(self):
        """Vérifie que _repetable(min=1) crée un slot 1+ (min=1, max=-1)."""
        slot = _repetable("reseau", 1)
        assert slot.min_occurs == 1
        assert slot.max_occurs == -1

    def test_slot_sequence_est_namedtuple(self):
        """Vérifie que SlotSequence est un NamedTuple immuable."""
        slot = SlotSequence("test", 1, 1)
        with pytest.raises(AttributeError):
            slot.nom = "autre"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests de la fonction utilitaire _trouver_slot
# ---------------------------------------------------------------------------


class TestTrouverSlot:
    """Tests de la recherche de slot dans une séquence."""

    def test_trouver_slot_present(self):
        """Trouve un slot existant à partir de l'index 0."""
        slots = [_requis("A"), _optionnel("B"), _requis("C")]
        assert _trouver_slot("B", slots, 0) == 1

    def test_trouver_slot_depuis_index_intermediaire(self):
        """Ne trouve pas un slot situé avant l'index de départ."""
        slots = [_requis("A"), _optionnel("B"), _requis("C")]
        assert _trouver_slot("A", slots, 1) == -1

    def test_trouver_slot_absent(self):
        """Retourne -1 pour un slot inconnu."""
        slots = [_requis("A"), _requis("B")]
        assert _trouver_slot("X", slots, 0) == -1

    def test_trouver_slot_au_debut(self):
        """Trouve le premier slot."""
        slots = [_requis("A"), _requis("B")]
        assert _trouver_slot("A", slots, 0) == 0

    def test_trouver_slot_en_fin(self):
        """Trouve le dernier slot."""
        slots = [_requis("A"), _requis("B"), _requis("C")]
        assert _trouver_slot("C", slots, 0) == 2


# ---------------------------------------------------------------------------
# Tests de valider_sequence — cas nominaux
# ---------------------------------------------------------------------------


class TestValiderSequenceCasNominaux:
    """Tests de validation de séquences conformes."""

    def test_sequence_vide_conforme(self):
        """Une séquence vide est conforme si tous les éléments sont optionnels."""
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", [])
        # Vérifie seulement les erreurs ELEMENT_REQUIS_MANQUANT pour les requis
        manquants = [e for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"]
        assert len(manquants) > 0  # reseau, DomaineTension, Statut, TypeJonction requis

    def test_jonction_sequence_complete_correcte(self):
        """RPD_Jonction_Reco avec séquence complète et conforme."""
        noms = [
            "reseau",
            "Commentaire",
            "conteneur",
            "DomaineTension",
            "Geometrie",
            "PrecisionXY",
            "PrecisionZ",
            "Statut",
            "TypeJonction",
        ]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        assert erreurs == []

    def test_jonction_sans_optionnels(self):
        """RPD_Jonction_Reco avec seulement les éléments requis."""
        noms = ["reseau", "DomaineTension", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        assert erreurs == []

    def test_aerien_sequence_correcte(self):
        """RPD_Aerien_Reco avec séquence conforme."""
        noms = [
            "reseau",
            "reseau",
            "Geometrie",
            "ModePose",
            "PrecisionXY",
            "PrecisionZ",
        ]
        erreurs = valider_sequence("RPD_Aerien_Reco", "id1", noms)
        assert erreurs == []

    def test_aerien_multi_reseau(self):
        """RPD_Aerien_Reco avec plusieurs éléments reseau (1+)."""
        noms = [
            "reseau",
            "reseau",
            "reseau",
            "Geometrie",
            "ModePose",
            "PrecisionXY",
            "PrecisionZ",
        ]
        erreurs = valider_sequence("RPD_Aerien_Reco", "id1", noms)
        assert erreurs == []

    def test_geom_supplementaire_avec_lignes_et_surfaces(self):
        """RPD_GeometrieSupplementaire_Reco avec éléments répétés."""
        noms = [
            "Commentaire",
            "Ligne3D",
            "Ligne3D",
            "PrecisionXY",
            "PrecisionZ",
            "Surface3D",
            "Surface3D",
        ]
        erreurs = valider_sequence("RPD_GeometrieSupplementaire_Reco", "id1", noms)
        assert erreurs == []

    def test_geom_supplementaire_minimal(self):
        """RPD_GeometrieSupplementaire_Reco avec uniquement les éléments requis."""
        noms = ["PrecisionXY", "PrecisionZ"]
        erreurs = valider_sequence("RPD_GeometrieSupplementaire_Reco", "id1", noms)
        assert erreurs == []

    def test_materiel_sequence_complete(self):
        """RPD_Materiel_Reco avec séquence complète conforme."""
        noms = ["Fabricant", "Modele", "NumeroLot", "NumeroSerie"]
        erreurs = valider_sequence("RPD_Materiel_Reco", "id1", noms)
        assert erreurs == []

    def test_point_leve_minimal(self):
        """RPD_PointLeveOuvrageReseau_Reco avec éléments requis uniquement."""
        noms = [
            "Geometrie",
            "NumeroPoint",
            "PrecisionXYnum",
            "PrecisionZnum",
            "Producteur",
        ]
        erreurs = valider_sequence("RPD_PointLeveOuvrageReseau_Reco", "id1", noms)
        assert erreurs == []

    def test_cable_electrique_avec_optionnels(self):
        """RPD_CableElectrique_Reco avec plusieurs éléments optionnels inclus."""
        noms = [
            "reseau",
            "DomaineTension",
            "Etiquette",
            "FonctionCable",
            "HierarchieBT",
            "Section",
            "Statut",
        ]
        erreurs = valider_sequence("RPD_CableElectrique_Reco", "id1", noms)
        assert erreurs == []

    def test_type_inconnu_retourne_liste_vide(self):
        """Un type RPD non reconnu ne génère aucune erreur."""
        erreurs = valider_sequence("TYPE_INCONNU", "id1", ["Statut"])
        assert erreurs == []

    def test_coffret_sequence_complete_conforme(self):
        """RPD_Coffret_Reco avec sa séquence complète d'éléments requis est conforme."""
        # Standard V1.1 : TypeCoffret et FonctionCoffret sont requis (cardinalité 1).
        noms = [
            "reseau",
            "FonctionCoffret",
            "Geometrie",
            "PrecisionXY",
            "PrecisionZ",
            "Statut",
            "TypeCoffret",
        ]
        erreurs = valider_sequence("RPD_Coffret_Reco", "coffret_001", noms)
        assert erreurs == []


# ---------------------------------------------------------------------------
# Tests de valider_sequence — détection d'erreurs d'ordre
# ---------------------------------------------------------------------------


class TestValiderSequenceCatalogueExterne:
    """Vérifie que valider_sequence accepte un catalogue de séquences externe.

    Cette extension est utilisée par le contrôle E113 pour valider les objets
    Metadata et ReseauUtilite sans dupliquer le moteur d'ordonnancement.
    """

    def _catalogue_test(self) -> dict[str, list[SlotSequence]]:
        """Mini-catalogue ad hoc pour exercer le paramètre `sequences`."""
        return {
            "TypeFictif": [
                SlotSequence("ChampA", 1, 1),
                SlotSequence("ChampB", 0, 1),
                SlotSequence("ChampC", 1, 1),
            ],
        }

    def test_catalogue_externe_sequence_conforme(self):
        """Séquence conforme évaluée contre un catalogue passé en paramètre."""
        erreurs = valider_sequence(
            "TypeFictif",
            "id1",
            ["ChampA", "ChampB", "ChampC"],
            sequences=self._catalogue_test(),
        )
        assert erreurs == []

    def test_catalogue_externe_requis_manquant_detecte(self):
        """Un champ requis manquant dans le catalogue externe est signalé."""
        erreurs = valider_sequence(
            "TypeFictif",
            "id1",
            ["ChampA"],
            sequences=self._catalogue_test(),
        )
        manquants = [e for e in erreurs if e.element_attendu == "ChampC"]
        assert len(manquants) == 1

    def test_catalogue_externe_type_inconnu_ignore(self):
        """Type absent du catalogue externe : aucune erreur (parité avec RPD)."""
        erreurs = valider_sequence(
            "TypeAbsent",
            "id1",
            ["X", "Y"],
            sequences=self._catalogue_test(),
        )
        assert erreurs == []

    def test_defaut_pointe_sur_sequences_rpd(self):
        """Sans paramètre `sequences`, on utilise toujours SEQUENCES_RPD."""
        # RPD_Jonction_Reco est défini dans SEQUENCES_RPD, pas dans le catalogue test.
        erreurs = valider_sequence(
            "RPD_Jonction_Reco",
            "id1",
            ["reseau", "DomaineTension", "Statut", "TypeJonction"],
        )
        assert erreurs == []


class TestValiderSequenceOrdreIncorrect:
    """Tests de détection des erreurs d'ordre (ORDRE_INCORRECT)."""

    def test_conteneur_apres_domaine_tension(self):
        """Détecte conteneur placé après DomaineTension (doit être avant)."""
        noms = ["reseau", "DomaineTension", "conteneur", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert len(ordres) == 1
        assert ordres[0].element_trouve == "conteneur"

    def test_statut_avant_fonction_cable(self):
        """Détecte FonctionCable signalé hors ordre quand Statut le précède dans CableTerre.

        Comportement : l'algorithme consomme Statut à son slot correct (8), puis signale
        FonctionCable comme ORDRE_INCORRECT car son slot (3) est déjà dépassé.
        """
        noms = ["reseau", "Statut", "FonctionCable", "Materiau", "Section"]
        erreurs = valider_sequence("RPD_CableTerre_Reco", "id1", noms)
        # FonctionCable est signalé hors ordre (slot 3 dépassé après consommation de Statut)
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert any(e.element_trouve == "FonctionCable" for e in ordres)
        # Les éléments requis sauts sont aussi signalés
        manquants = {e.element_attendu for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"}
        assert "FonctionCable" in manquants or "Materiau" in manquants

    def test_precision_xy_avant_geometrie_dans_support(self):
        """Détecte Geometrie signalé hors ordre quand PrecisionXY le précède dans Support.

        Comportement : l'algorithme consomme PrecisionXY à son slot correct (9), puis signale
        Geometrie comme ORDRE_INCORRECT car son slot (5) est déjà dépassé.
        """
        noms = [
            "reseau",
            "PrecisionXY",
            "Geometrie",
            "NatureSupport",
            "PrecisionZ",
            "Statut",
        ]
        erreurs = valider_sequence("RPD_Support_Reco", "id1", noms)
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert any(e.element_trouve == "Geometrie" for e in ordres)

    def test_erreur_contient_position(self):
        """Vérifie que la position est renseignée dans l'erreur."""
        noms = ["reseau", "DomaineTension", "conteneur", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert ordres[0].position is not None

    def test_erreur_contient_type_rpd_et_gml_id(self):
        """Vérifie que type_rpd et gml_id sont correctement renseignés."""
        noms = ["reseau", "DomaineTension", "conteneur", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "jonction_XYZ", noms)
        ordres = [e for e in erreurs if e.type_erreur == "ORDRE_INCORRECT"]
        assert ordres[0].type_rpd == "RPD_Jonction_Reco"
        assert ordres[0].gml_id == "jonction_XYZ"


# ---------------------------------------------------------------------------
# Tests de valider_sequence — éléments requis manquants
# ---------------------------------------------------------------------------


class TestValiderSequenceElemManquants:
    """Tests de détection des éléments requis manquants."""

    def test_reseau_manquant_dans_aerien(self):
        """Détecte l'absence de reseau (requis 1+) dans RPD_Aerien_Reco."""
        noms = ["Geometrie", "ModePose", "PrecisionXY", "PrecisionZ"]
        erreurs = valider_sequence("RPD_Aerien_Reco", "id1", noms)
        manquants = [e for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"]
        assert any(e.element_attendu == "reseau" for e in manquants)

    def test_statut_manquant_dans_jonction(self):
        """Détecte l'absence de Statut (requis) dans RPD_Jonction_Reco."""
        noms = ["reseau", "DomaineTension", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        manquants = [e for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"]
        assert any(e.element_attendu == "Statut" for e in manquants)

    def test_geometrie_manquante_dans_fourreau(self):
        """Détecte l'absence de Geometrie (requis) dans RPD_Fourreau_Reco."""
        noms = ["reseau", "DiametreDuFourreau", "Materiau", "PrecisionXY", "PrecisionZ"]
        erreurs = valider_sequence("RPD_Fourreau_Reco", "id1", noms)
        manquants = [e for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"]
        assert any(e.element_attendu == "Geometrie" for e in manquants)

    def test_sequence_completement_vide_signale_elements_requis(self):
        """Une séquence vide signale tous les éléments requis manquants."""
        erreurs = valider_sequence("RPD_Materiel_Reco", "id1", [])
        manquants = {e.element_attendu for e in erreurs if e.type_erreur == "ELEMENT_REQUIS_MANQUANT"}
        assert {"Fabricant", "Modele", "NumeroLot", "NumeroSerie"} == manquants

    def test_optionnel_absent_ne_declenche_pas_erreur(self):
        """L'absence d'un élément optionnel ne génère pas d'erreur."""
        # Commentaire est optionnel dans RPD_Aerien_Reco
        noms = ["reseau", "Geometrie", "ModePose", "PrecisionXY", "PrecisionZ"]
        erreurs = valider_sequence("RPD_Aerien_Reco", "id1", noms)
        assert all(e.element_attendu != "Commentaire" for e in erreurs)


# ---------------------------------------------------------------------------
# Tests de valider_sequence — éléments inattendus
# ---------------------------------------------------------------------------


class TestValiderSequenceElemInattendu:
    """Tests de détection des éléments inattendus."""

    def test_element_inconnu_dans_type_rpd(self):
        """Détecte un élément inconnu dans une séquence RPD."""
        noms = ["reseau", "DomaineTension", "CHAMP_INCONNU", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        inattendus = [e for e in erreurs if e.type_erreur == "ELEMENT_INATTENDU"]
        assert len(inattendus) == 1
        assert inattendus[0].element_trouve == "CHAMP_INCONNU"

    def test_element_ep_dans_enfants_signale_comme_inattendu(self):
        """Un élément EP_ dans les enfants d'un RPD est signalé comme inattendu."""
        noms = ["reseau", "EP_Geometrie", "DomaineTension", "Statut", "TypeJonction"]
        erreurs = valider_sequence("RPD_Jonction_Reco", "id1", noms)
        inattendus = [e for e in erreurs if e.type_erreur == "ELEMENT_INATTENDU"]
        assert any(e.element_trouve == "EP_Geometrie" for e in inattendus)


# ---------------------------------------------------------------------------
# Tests de ErreurOrdre.vers_dict
# ---------------------------------------------------------------------------


class TestErreurOrdreVersDict:
    """Tests de sérialisation des erreurs."""

    def test_vers_dict_contient_tous_les_champs(self):
        """Vérifie que vers_dict retourne tous les champs requis."""
        erreur = ErreurOrdre(
            type_rpd="RPD_Jonction_Reco",
            gml_id="jonction_001",
            type_erreur="ORDRE_INCORRECT",
            position=3,
            element_trouve="conteneur",
            element_attendu="conteneur",
            message="test",
        )
        d = erreur.vers_dict()
        champs_attendus = {
            "type_rpd",
            "gml_id",
            "severite",
            "priorite",
            "type_erreur",
            "position",
            "element_trouve",
            "element_attendu",
            "message",
        }
        assert champs_attendus == set(d.keys())

    def test_vers_dict_valeurs_correctes(self):
        """Vérifie les valeurs retournées par vers_dict."""
        erreur = ErreurOrdre(
            type_rpd="RPD_Test",
            gml_id="id_test",
            type_erreur="ORDRE_INCORRECT",
            position=2,
            element_trouve="X",
            element_attendu="Y",
            message="msg",
        )
        d = erreur.vers_dict()
        assert d["type_rpd"] == "RPD_Test"
        assert d["gml_id"] == "id_test"
        assert d["type_erreur"] == "ORDRE_INCORRECT"
        assert d["position"] == 2
        assert d["element_trouve"] == "X"
        assert d["element_attendu"] == "Y"

    def test_slots_interdit_attributs_dynamiques(self):
        """Vérifie que __slots__ empêche l'ajout d'attributs non définis."""
        erreur = ErreurOrdre("A", "B", "C", 0, None, None, "msg")
        with pytest.raises(AttributeError):
            erreur.champ_inconnu = "valeur"  # type: ignore[attr-defined]
