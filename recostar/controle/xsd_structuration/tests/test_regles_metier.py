"""
Tests unitaires du module regles_metier.
Couvre le catalogue des règles, les déclencheurs et le moteur d'évaluation.
"""

import pytest
from regles_metier import (
    REGLES_METIER,
    REGLES_PAR_TYPE,
    TYPES_RPD_AVEC_REGLES,
    ErreurMetier,
    RegleMetier,
    _champ_present,
    _domaine_tension_bt,
    _statut_en_attente,
    _support_poteau_en_attente,
    evaluer_regles,
)

# ---------------------------------------------------------------------------
# Tests des constantes et de l'index
# ---------------------------------------------------------------------------


class TestConstantes:
    """Tests des structures de données globales du module."""

    def test_regles_metier_est_tuple(self):
        """Le catalogue est immuable (tuple)."""
        assert isinstance(REGLES_METIER, tuple)

    def test_regles_metier_non_vide(self):
        """Le catalogue contient au moins une règle."""
        assert len(REGLES_METIER) > 0

    def test_chaque_regle_est_regle_metier(self):
        """Toutes les entrées du catalogue sont du type attendu."""
        for regle in REGLES_METIER:
            assert isinstance(regle, RegleMetier)

    def test_identifiants_uniques(self):
        """Chaque règle a un identifiant unique (utile pour traçabilité)."""
        identifiants = [r.identifiant for r in REGLES_METIER]
        assert len(identifiants) == len(set(identifiants))

    def test_types_rpd_avec_regles_est_frozenset(self):
        """L'index des types est un frozenset pour lookup O(1)."""
        assert isinstance(TYPES_RPD_AVEC_REGLES, frozenset)

    def test_types_rpd_avec_regles_coherent(self):
        """TYPES_RPD_AVEC_REGLES correspond exactement aux clés de REGLES_PAR_TYPE."""
        assert TYPES_RPD_AVEC_REGLES == frozenset(REGLES_PAR_TYPE.keys())

    def test_regles_par_type_couvre_catalogue(self):
        """Chaque règle est référencée dans l'index par son type RPD."""
        for regle in REGLES_METIER:
            assert regle in REGLES_PAR_TYPE[regle.type_rpd]


# ---------------------------------------------------------------------------
# Tests des déclencheurs
# ---------------------------------------------------------------------------


class TestDeclencheurs:
    """Tests des fonctions qui décident de l'applicabilité d'une règle."""

    def test_statut_en_attente_vrai(self):
        """UnderCommissionning déclenche la règle."""
        assert _statut_en_attente({"Statut": "UnderCommissionning"}) is True

    def test_statut_en_attente_faux_si_fonctional(self):
        """Functional ne déclenche pas la règle."""
        assert _statut_en_attente({"Statut": "Functional"}) is False

    def test_statut_en_attente_faux_si_absent(self):
        """Statut absent ne déclenche pas la règle."""
        assert _statut_en_attente({}) is False

    def test_domaine_tension_bt_vrai(self):
        """BT déclenche la règle HierarchieBT."""
        assert _domaine_tension_bt({"DomaineTension": "BT"}) is True

    def test_domaine_tension_bt_faux_si_hta(self):
        """HTA ne déclenche pas la règle BT."""
        assert _domaine_tension_bt({"DomaineTension": "HTA"}) is False

    def test_support_poteau_en_attente_vrai(self):
        """Poteau + UnderCommissionning déclenche la règle."""
        valeurs = {"NatureSupport": "Poteau", "Statut": "UnderCommissionning"}
        assert _support_poteau_en_attente(valeurs) is True

    def test_support_poteau_en_attente_faux_si_facade(self):
        """Façade + UnderCommissionning ne déclenche pas la règle."""
        valeurs = {"NatureSupport": "Facade", "Statut": "UnderCommissionning"}
        assert _support_poteau_en_attente(valeurs) is False

    def test_support_poteau_en_attente_faux_si_fonctional(self):
        """Poteau + Functional ne déclenche pas la règle (deux conditions cumulatives)."""
        valeurs = {"NatureSupport": "Poteau", "Statut": "Functional"}
        assert _support_poteau_en_attente(valeurs) is False


# ---------------------------------------------------------------------------
# Tests de _champ_present
# ---------------------------------------------------------------------------


class TestChampPresent:
    """Tests de la détection de champs vides/manquants."""

    def test_champ_avec_valeur(self):
        """Une valeur non vide est considérée présente."""
        assert _champ_present({"X": "valeur"}, "X") is True

    def test_champ_absent_du_dict(self):
        """Une clé absente est considérée comme champ manquant."""
        assert _champ_present({}, "X") is False

    def test_champ_valeur_none(self):
        """Une valeur None est considérée comme manquante."""
        assert _champ_present({"X": None}, "X") is False

    def test_champ_chaine_vide(self):
        """Une chaîne vide est considérée comme manquante."""
        assert _champ_present({"X": ""}, "X") is False

    def test_champ_uniquement_espaces(self):
        """Une chaîne ne contenant que des espaces est considérée manquante."""
        assert _champ_present({"X": "   "}, "X") is False

    def test_champ_valeur_zero_preservee(self):
        """La valeur littérale '0' est considérée présente (non vide)."""
        assert _champ_present({"X": "0"}, "X") is True


# ---------------------------------------------------------------------------
# Tests du moteur evaluer_regles : règle R001 (Câble électrique en attente)
# ---------------------------------------------------------------------------


class TestRegleR001CableEnAttente:
    """Tests de la règle R001_CABLE_ELEC_EN_ATTENTE."""

    def _valeurs_completes(self) -> dict[str, str | None]:
        """Câble électrique en attente avec tous les champs requis."""
        return {
            "DomaineTension": "HTA",
            "FonctionCable": "DistributionEnergie",
            "NombreConducteurs": "3",
            "Section": "240",
            "Isolant": "Reticulee",
            "Materiau": "Alu",
            "Statut": "UnderCommissionning",
        }

    def test_cable_en_attente_complet_aucune_erreur(self):
        """Câble en attente avec tous les champs requis : aucune erreur."""
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", self._valeurs_completes())
        # Le câble n'est pas en BT, donc seule R001 s'applique et elle est satisfaite.
        assert not [e for e in erreurs if e.regle == "R001_CABLE_ELEC_EN_ATTENTE"]

    def test_cable_en_attente_sans_section(self):
        """Section manquante sur un câble en attente : règle R001 violée."""
        valeurs = self._valeurs_completes()
        del valeurs["Section"]
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert any(e.champ_attendu == "Section" for e in erreurs)

    def test_cable_en_attente_sans_isolant(self):
        """Isolant manquant sur un câble en attente : règle R001 violée."""
        valeurs = self._valeurs_completes()
        del valeurs["Isolant"]
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert any(e.champ_attendu == "Isolant" for e in erreurs)

    def test_cable_en_attente_quatre_champs_manquants(self):
        """Aucun des quatre champs métier présents : 4 erreurs distinctes."""
        valeurs = {"Statut": "UnderCommissionning"}
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        champs_manquants = {e.champ_attendu for e in erreurs}
        assert {
            "NombreConducteurs",
            "Section",
            "Isolant",
            "Materiau",
        } <= champs_manquants

    def test_cable_fonctional_pas_de_regle_r001(self):
        """Câble en service (Functional) : R001 ne se déclenche pas."""
        valeurs = {"Statut": "Functional", "DomaineTension": "HTA"}
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert not [e for e in erreurs if e.regle == "R001_CABLE_ELEC_EN_ATTENTE"]


# ---------------------------------------------------------------------------
# Tests du moteur evaluer_regles : règle R002 (Câble BT)
# ---------------------------------------------------------------------------


class TestRegleR002CableBT:
    """Tests de la règle R002_CABLE_ELEC_BT."""

    def test_cable_bt_avec_hierarchie(self):
        """Câble BT avec HierarchieBT renseigné : aucune erreur."""
        valeurs = {
            "DomaineTension": "BT",
            "HierarchieBT": "Reseau",
            "Statut": "Functional",
        }
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert not [e for e in erreurs if e.regle == "R002_CABLE_ELEC_BT"]

    def test_cable_bt_sans_hierarchie(self):
        """Câble BT sans HierarchieBT : règle R002 violée."""
        valeurs = {"DomaineTension": "BT", "Statut": "Functional"}
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        violations = [e for e in erreurs if e.regle == "R002_CABLE_ELEC_BT"]
        assert len(violations) == 1
        assert violations[0].champ_attendu == "HierarchieBT"

    def test_cable_hta_pas_de_regle_r002(self):
        """Câble HTA : R002 ne se déclenche pas (HierarchieBT non requis)."""
        valeurs = {"DomaineTension": "HTA", "Statut": "Functional"}
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert not [e for e in erreurs if e.regle == "R002_CABLE_ELEC_BT"]


# ---------------------------------------------------------------------------
# Tests du moteur evaluer_regles : règle R003 (Support poteau en attente)
# ---------------------------------------------------------------------------


class TestRegleR003SupportPoteau:
    """Tests de la règle R003_SUPPORT_POTEAU_EN_ATTENTE."""

    def test_poteau_en_attente_complet(self):
        """Poteau en attente avec tous les champs requis : aucune erreur."""
        valeurs = {
            "NatureSupport": "Poteau",
            "Statut": "UnderCommissionning",
            "Classe": "M",
            "Effort": "1000",
            "HauteurPoteau": "10",
            "Matiere": "Beton",
        }
        erreurs = evaluer_regles("RPD_Support_Reco", "id1", valeurs)
        assert erreurs == []

    def test_poteau_en_attente_sans_classe(self):
        """Poteau en attente sans Classe : violation R003."""
        valeurs = {
            "NatureSupport": "Poteau",
            "Statut": "UnderCommissionning",
            "Effort": "1000",
            "HauteurPoteau": "10",
            "Matiere": "Beton",
        }
        erreurs = evaluer_regles("RPD_Support_Reco", "id1", valeurs)
        assert any(e.champ_attendu == "Classe" for e in erreurs)

    def test_facade_en_attente_aucune_regle(self):
        """Façade en attente : R003 ne s'applique pas (NatureSupport != Poteau)."""
        valeurs = {
            "NatureSupport": "Facade",
            "Statut": "UnderCommissionning",
        }
        erreurs = evaluer_regles("RPD_Support_Reco", "id1", valeurs)
        assert erreurs == []

    def test_poteau_fonctional_aucune_regle(self):
        """Poteau en service (Functional) : R003 ne s'applique pas."""
        valeurs = {"NatureSupport": "Poteau", "Statut": "Functional"}
        erreurs = evaluer_regles("RPD_Support_Reco", "id1", valeurs)
        assert erreurs == []


# ---------------------------------------------------------------------------
# Tests du moteur : cas génériques
# ---------------------------------------------------------------------------


class TestEvaluerReglesGenerique:
    """Tests des comportements génériques du moteur."""

    def test_type_sans_regle_retourne_vide(self):
        """Un type RPD non référencé ne génère aucune erreur."""
        erreurs = evaluer_regles("RPD_Jonction_Reco", "id1", {"Statut": "UnderCommissionning"})
        assert erreurs == []

    def test_type_inconnu_retourne_vide(self):
        """Un type RPD totalement inconnu ne génère aucune erreur."""
        erreurs = evaluer_regles("TYPE_INEXISTANT", "id1", {})
        assert erreurs == []

    def test_champ_avec_valeur_vide_signale(self):
        """Un champ requis présent mais avec valeur vide est signalé manquant."""
        valeurs = {
            "Statut": "UnderCommissionning",
            "NombreConducteurs": "",
            "Section": "240",
            "Isolant": "Reticulee",
            "Materiau": "Alu",
        }
        erreurs = evaluer_regles("RPD_CableElectrique_Reco", "id1", valeurs)
        assert any(e.champ_attendu == "NombreConducteurs" for e in erreurs)


# ---------------------------------------------------------------------------
# Tests de ErreurMetier
# ---------------------------------------------------------------------------


class TestErreurMetier:
    """Tests de la classe d'erreur métier."""

    def test_vers_dict_champs_complets(self):
        """vers_dict expose tous les champs attendus."""
        err = ErreurMetier(
            type_rpd="RPD_X",
            gml_id="id1",
            regle="R001",
            champ_attendu="Section",
            contexte="contexte_test",
            message="msg",
        )
        d = err.vers_dict()
        attendus = {
            "type_rpd",
            "gml_id",
            "severite",
            "regle",
            "champ_attendu",
            "contexte",
            "message",
        }
        assert attendus == set(d.keys())

    def test_vers_dict_valeurs_correctes(self):
        """vers_dict reflète fidèlement les valeurs portées par l'instance."""
        err = ErreurMetier("A", "B", "C", "D", "E", "F")
        d = err.vers_dict()
        assert d["type_rpd"] == "A"
        assert d["gml_id"] == "B"
        assert d["regle"] == "C"
        assert d["champ_attendu"] == "D"
        assert d["contexte"] == "E"
        assert d["message"] == "F"

    def test_slots_interdit_attributs_dynamiques(self):
        """__slots__ empêche l'ajout d'attributs non déclarés."""
        err = ErreurMetier("A", "B", "C", "D", "E", "F")
        with pytest.raises(AttributeError):
            err.attribut_inconnu = "x"  # type: ignore[attr-defined]
