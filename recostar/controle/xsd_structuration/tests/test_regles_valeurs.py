"""
Tests unitaires du module regles_valeurs.
Couvre le catalogue déclaratif, l'index par couple (type_rpd, champ),
et le moteur d'évaluation.
"""

import pytest
from priorites_structuration import PRIORITE_BLOQUANT, PRIORITE_MINEUR
from regles_valeurs import (
    _INDEX_REGLES,
    CODE_FORMAT_INVALIDE,
    CODE_VALEUR_HORS_CODELIST,
    CODE_VALEUR_HORS_ENUMERATION,
    REGLES_VALEURS,
    SEVERITE_ERREUR,
    TYPES_AVEC_REGLES,
    ErreurValeur,
    RegleValeur,
    construire_index,
    evaluer_valeur,
)

# ---------------------------------------------------------------------------
# Tests des constantes et de l'index
# ---------------------------------------------------------------------------


class TestCatalogueStructure:
    """Cohérence interne du catalogue REGLES_VALEURS."""

    def test_catalogue_est_tuple_immuable(self):
        """REGLES_VALEURS est un tuple, donc figé à l'exécution."""
        assert isinstance(REGLES_VALEURS, tuple)

    def test_catalogue_non_vide(self):
        assert len(REGLES_VALEURS) > 0

    def test_chaque_regle_est_regle_valeur(self):
        for regle in REGLES_VALEURS:
            assert isinstance(regle, RegleValeur)

    def test_identifiants_uniques(self):
        """Les identifiants servent à tracer les violations, donc uniques."""
        identifiants = [r.identifiant for r in REGLES_VALEURS]
        assert len(identifiants) == len(set(identifiants))

    def test_severites_valides(self):
        """E114 est mono-sévérité : toutes les règles sont en ERREUR."""
        for regle in REGLES_VALEURS:
            assert regle.severite == SEVERITE_ERREUR


class TestIndexLookup:
    """Index pré-calculé (type_rpd, champ) → RegleValeur."""

    def test_index_est_dict(self):
        assert isinstance(_INDEX_REGLES, dict)

    def test_index_contient_toutes_les_regles(self):
        """Chaque règle est référencée pour chacun de ses types_rpd."""
        for regle in REGLES_VALEURS:
            for type_rpd in regle.types_rpd:
                assert _INDEX_REGLES[(type_rpd, regle.champ)] is regle

    def test_types_avec_regles_aligne_sur_index(self):
        """TYPES_AVEC_REGLES contient exactement les types de l'index."""
        attendus = frozenset(t for t, _ in _INDEX_REGLES)
        assert TYPES_AVEC_REGLES == attendus

    def test_construire_index_detecte_doublon(self):
        """Le constructeur d'index échoue si deux règles couvrent même couple."""
        regle_dup_1 = RegleValeur(
            identifiant="DUP1",
            types_rpd=frozenset({"TypeX"}),
            champ="ChampY",
            evaluateur=lambda v: True,
            code_erreur=CODE_VALEUR_HORS_ENUMERATION,
            severite=SEVERITE_ERREUR,
            source="test",
            description="d",
        )
        regle_dup_2 = regle_dup_1._replace(identifiant="DUP2")
        catalogue_corrompu = (regle_dup_1, regle_dup_2)
        # construire_index étant paramétrable, on lui passe directement le
        # catalogue corrompu : pas besoin de réimplémenter l'indexation ici.
        with pytest.raises(ValueError, match="couvert par"):
            construire_index(catalogue_corrompu)

    def test_index_reconstruit_identique(self):
        """construire_index() est déterministe et idempotent."""
        index_bis = construire_index()
        assert index_bis == _INDEX_REGLES


# ---------------------------------------------------------------------------
# Tests du moteur evaluer_valeur
# ---------------------------------------------------------------------------


class TestEvaluerValeurEnumerations:
    """Énumérations strictes — sévérité ERREUR."""

    def test_domaine_tension_valide_aucune_erreur(self):
        assert evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "HTA", "id1") is None

    def test_domaine_tension_invalide_signale(self):
        erreur = evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "MTA", "id1")
        assert erreur is not None
        assert erreur.code == CODE_VALEUR_HORS_ENUMERATION
        assert erreur.severite == SEVERITE_ERREUR
        assert erreur.valeur_trouvee == "MTA"
        assert erreur.regle == "E_DOMAINE_TENSION"

    def test_statut_under_commissionning_avec_deux_n(self):
        """Le typo officiel du XSD/PDF doit être accepté."""
        assert evaluer_valeur("RPD_CableElectrique_Reco", "Statut", "UnderCommissionning", "id1") is None

    def test_statut_under_commissioning_un_n_rejete(self):
        """L'orthographe « correcte » (un seul n) est en réalité invalide."""
        erreur = evaluer_valeur("RPD_CableElectrique_Reco", "Statut", "UnderCommissioning", "id1")
        assert erreur is not None
        assert erreur.severite == SEVERITE_ERREUR

    def test_srs_metropole_valide(self):
        assert evaluer_valeur("Metadata", "SRS", "EPSG:2154", "meta_001") is None

    def test_srs_wgs84_rejete(self):
        """WGS84 n'est pas dans la liste fermée RecoStaR."""
        erreur = evaluer_valeur("Metadata", "SRS", "EPSG:4326", "meta_001")
        assert erreur is not None
        assert erreur.code == CODE_VALEUR_HORS_ENUMERATION


class TestEvaluerValeurMateriauPolymorphisme:
    """Le champ 'Materiau' admet des valeurs différentes selon le type RPD."""

    def test_materiau_alu_valide_sur_cable(self):
        assert evaluer_valeur("RPD_CableElectrique_Reco", "Materiau", "Alu", "id1") is None

    def test_materiau_pe_invalide_sur_cable(self):
        """PE est valide sur cheminement mais pas sur câble."""
        erreur = evaluer_valeur("RPD_CableElectrique_Reco", "Materiau", "PE", "id1")
        assert erreur is not None
        assert erreur.regle == "E_MATERIAU_CABLE"

    def test_materiau_pe_valide_sur_fourreau(self):
        assert evaluer_valeur("RPD_Fourreau_Reco", "Materiau", "PE", "id1") is None

    def test_materiau_alu_invalide_sur_fourreau(self):
        """Alu est valide sur câble mais pas sur cheminement."""
        erreur = evaluer_valeur("RPD_Fourreau_Reco", "Materiau", "Alu", "id1")
        assert erreur is not None
        assert erreur.regle == "E_MATERIAU_CHEMINEMENT"


class TestEvaluerValeurCodeLists:
    """CodeLists documentées — sévérité ERREUR (politique RPD stricte)."""

    def test_type_coffret_valide_aucune_erreur(self):
        assert evaluer_valeur("RPD_Coffret_Reco", "TypeCoffret", "RMBT300", "cof_001") is None

    def test_type_coffret_inconnu_emet_erreur(self):
        erreur = evaluer_valeur("RPD_Coffret_Reco", "TypeCoffret", "ExtensionLocaleXYZ", "cof_001")
        assert erreur is not None
        assert erreur.code == CODE_VALEUR_HORS_CODELIST
        assert erreur.severite == SEVERITE_ERREUR

    def test_classe_support_valeur_inconnue_erreur(self):
        erreur = evaluer_valeur("RPD_Support_Reco", "Classe", "Inconnu123", "sup_001")
        assert erreur is not None
        assert erreur.severite == SEVERITE_ERREUR


class TestEvaluerValeurThemeRpd:
    """Theme RPD : §9 impose ELECTRD, plus strict que la CodeList §10.6.2."""

    def test_theme_electrd_valide(self):
        assert evaluer_valeur("ReseauUtilite", "Theme", "ELECTRD", "reseau_001") is None

    def test_theme_elec_rejete(self):
        """ELEC est un code valide de la CodeList NatureReseauValue mais
        invalide pour un fichier RPD."""
        erreur = evaluer_valeur("ReseauUtilite", "Theme", "ELEC", "reseau_001")
        assert erreur is not None
        assert erreur.severite == SEVERITE_ERREUR
        assert erreur.regle == "E_THEME_RPD"

    def test_theme_elec_priorite_mineure(self):
        """La détection et le message sont inchangés : seule la priorité l'est."""
        erreur = evaluer_valeur("ReseauUtilite", "Theme", "ELEC", "reseau_001")
        assert erreur is not None
        assert erreur.priorite == PRIORITE_MINEUR
        assert erreur.message == (
            "Valeur 'ELEC' invalide pour ReseauUtilite/Theme. Valeurs autorisées : ELECTRD (source : PDF §9)."
        )
        assert erreur.vers_dict()["priorite"] == PRIORITE_MINEUR


class TestPrioritesCatalogue:
    """Une seule règle de valeur déroge à la priorité bloquante."""

    def test_seule_regle_theme_est_mineure(self):
        derogations = {r.identifiant: r.priorite for r in REGLES_VALEURS if r.priorite != PRIORITE_BLOQUANT}
        assert derogations == {"E_THEME_RPD": PRIORITE_MINEUR}

    def test_toutes_les_autres_restent_bloquantes(self):
        autres = [r for r in REGLES_VALEURS if r.identifiant != "E_THEME_RPD"]
        assert autres, "le catalogue doit contenir d'autres règles"
        assert {r.priorite for r in autres} == {PRIORITE_BLOQUANT}

    def test_regle_sans_priorite_declaree_est_bloquante(self):
        """Le défaut du modèle : oublier la priorité ne relâche jamais le contrôle."""
        regle = RegleValeur(
            identifiant="X",
            types_rpd=frozenset({"T"}),
            champ="C",
            evaluateur=lambda v: False,
            code_erreur=CODE_VALEUR_HORS_ENUMERATION,
            severite=SEVERITE_ERREUR,
            source="src",
            description="desc",
        )
        assert regle.priorite == PRIORITE_BLOQUANT

    def test_erreur_herite_de_la_priorite_de_sa_regle(self):
        """Une règle bloquante voisine produit bien une erreur bloquante."""
        erreur = evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "MTA", "cable_001")
        assert erreur is not None
        assert erreur.priorite == PRIORITE_BLOQUANT


class TestEvaluerValeurNumeroPRM:
    """Format NumeroPRM : 14 chiffres exactement."""

    def test_quatorze_chiffres_valide(self):
        assert (
            evaluer_valeur(
                "RPD_PointDeComptage_Reco",
                "NumeroPRM",
                "12345678901234",
                "pdc_001",
            )
            is None
        )

    def test_treize_chiffres_rejete(self):
        erreur = evaluer_valeur(
            "RPD_PointDeComptage_Reco",
            "NumeroPRM",
            "1234567890123",
            "pdc_001",
        )
        assert erreur is not None
        assert erreur.code == CODE_FORMAT_INVALIDE
        assert erreur.regle == "F_NUMERO_PRM"

    def test_quatorze_caracteres_dont_lettres_rejete(self):
        erreur = evaluer_valeur(
            "RPD_PointDeComptage_Reco",
            "NumeroPRM",
            "1234567890123A",
            "pdc_001",
        )
        assert erreur is not None
        assert erreur.code == CODE_FORMAT_INVALIDE


class TestEvaluerValeurCasLimites:
    """Cas où le moteur doit retourner None silencieusement."""

    def test_type_rpd_sans_regle_retourne_none(self):
        assert evaluer_valeur("TYPE_INEXISTANT", "DomaineTension", "BT", "id1") is None

    def test_champ_sans_regle_retourne_none(self):
        """Un champ non couvert par le catalogue est ignoré."""
        assert evaluer_valeur("RPD_CableElectrique_Reco", "ChampInconnu", "valeur", "id1") is None

    def test_valeur_none_retourne_none(self):
        """L'absence est traitée par E110/E111, pas par E114."""
        assert evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", None, "id1") is None

    def test_valeur_chaine_vide_retourne_none(self):
        assert evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "", "id1") is None

    def test_valeur_blancs_seulement_retourne_none(self):
        assert evaluer_valeur("RPD_CableElectrique_Reco", "DomaineTension", "   ", "id1") is None


# ---------------------------------------------------------------------------
# Tests d'ErreurValeur
# ---------------------------------------------------------------------------


class TestErreurValeur:
    """Comportement de la classe d'erreur."""

    def test_vers_dict_champs_complets(self):
        err = ErreurValeur(
            type_rpd="RPD_X",
            gml_id="id1",
            champ="Statut",
            valeur_trouvee="Bidon",
            code=CODE_VALEUR_HORS_ENUMERATION,
            severite=SEVERITE_ERREUR,
            regle="E_STATUT",
            source="PDF §10.1.5",
            message="msg",
        )
        attendus = {
            "type_rpd",
            "gml_id",
            "champ",
            "valeur_trouvee",
            "code",
            "severite",
            "priorite",
            "regle",
            "source",
            "message",
        }
        assert set(err.vers_dict().keys()) == attendus

    def test_vers_dict_valeurs_correctes(self):
        err = ErreurValeur("A", "B", "C", "D", "E", "F", "G", "H", "I")
        d = err.vers_dict()
        assert d["type_rpd"] == "A"
        assert d["gml_id"] == "B"
        assert d["champ"] == "C"
        assert d["valeur_trouvee"] == "D"
        assert d["code"] == "E"
        assert d["severite"] == "F"
        assert d["regle"] == "G"
        assert d["source"] == "H"
        assert d["message"] == "I"

    def test_slots_interdit_attributs_dynamiques(self):
        err = ErreurValeur("A", "B", "C", "D", "E", "F", "G", "H", "I")
        with pytest.raises(AttributeError):
            err.attribut_inconnu = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Test paramétré : couverture nominale + cas limite par règle
# ---------------------------------------------------------------------------


_CAS_PAR_REGLE = [
    # (identifiant, type_rpd, champ, valeur_valide, valeur_invalide)
    ("E_DOMAINE_TENSION", "RPD_CableElectrique_Reco", "DomaineTension", "BT", "MTA"),
    ("E_ISOLANT", "RPD_CableElectrique_Reco", "Isolant", "Nu", "Plastique"),
    ("E_HIERARCHIE_BT", "RPD_CableElectrique_Reco", "HierarchieBT", "Reseau", "Foo"),
    ("E_STATUT", "RPD_PosteElectrique_Reco", "Statut", "Functional", "Active"),
    ("E_PRECISION_XY", "RPD_Coffret_Reco", "PrecisionXY", "A", "D"),
    ("E_PRECISION_Z", "RPD_Coffret_Reco", "PrecisionZ", "B", "X"),
    (
        "E_ETAT_COUPE_TYPE",
        "RPD_Fourreau_Reco",
        "EtatCoupeType",
        "Provisoire",
        "Inconnu",
    ),
    ("E_MODE_POSE", "RPD_Aerien_Reco", "ModePose", "EnFacade", "Aerien"),
    ("E_TYPE_JONCTION", "RPD_Jonction_Reco", "TypeJonction", "Derivation", "BoiteX"),
    (
        "E_LEVE_TYPE",
        "RPD_PointLeveOuvrageReseau_Reco",
        "LeveType",
        "AltitudeGeneratrice",
        "Lambda",
    ),
]


class TestCoutureParRegle:
    """Couverture rapide : pour chaque règle, un cas valide + un cas invalide."""

    @pytest.mark.parametrize("identifiant,type_rpd,champ,valide,invalide", _CAS_PAR_REGLE)
    def test_cas_valide_aucune_erreur(
        self,
        identifiant: str,
        type_rpd: str,
        champ: str,
        valide: str,
        invalide: str,
    ):
        assert evaluer_valeur(type_rpd, champ, valide, "id") is None

    @pytest.mark.parametrize("identifiant,type_rpd,champ,valide,invalide", _CAS_PAR_REGLE)
    def test_cas_invalide_emet_erreur(
        self,
        identifiant: str,
        type_rpd: str,
        champ: str,
        valide: str,
        invalide: str,
    ):
        erreur = evaluer_valeur(type_rpd, champ, invalide, "id")
        assert erreur is not None
        assert erreur.regle == identifiant
