"""
Tests unitaires du module regles_entete.
Couvre le catalogue déclaratif et la classe ErreurEntete.
"""

import pytest
from regles_entete import (
    CARDINALITES_ENTETE,
    FRAGMENT_URL_MAIN,
    FRAGMENT_URL_XSD_V1_1,
    NAMESPACES_ATTENDUS,
    SEQUENCES_ENTETE,
    SRS_AUTORISES,
    TYPES_ENTETE,
    URI_RECOSTAR,
    ErreurEntete,
)
from sequenceur_xsd import SlotSequence

# ---------------------------------------------------------------------------
# Tests des constantes de namespaces
# ---------------------------------------------------------------------------


class TestNamespacesAttendus:
    """Cohérence du catalogue des namespaces obligatoires."""

    def test_prefixes_obligatoires_presents(self):
        """Les 4 préfixes attendus par PDF §[1] sont déclarés."""
        attendus = {"RecoStaR", "gml", "xlink", "xsi"}
        assert attendus == set(NAMESPACES_ATTENDUS.keys())

    def test_uri_recostar_avec_casse_exacte(self):
        """L'URI RecoStaR conserve la casse 'StaR-Elec' (sensibilité critique)."""
        assert NAMESPACES_ATTENDUS["RecoStaR"] == "http://StaR-Elec.com"

    def test_uri_recostar_coherent_avec_constante(self):
        """La constante URI_RECOSTAR est alignée sur NAMESPACES_ATTENDUS."""
        assert URI_RECOSTAR == NAMESPACES_ATTENDUS["RecoStaR"]

    def test_uri_gml_version_3_2(self):
        """L'URI GML cible bien la version 3.2 utilisée par le XSD."""
        assert NAMESPACES_ATTENDUS["gml"] == "http://www.opengis.net/gml/3.2"


# ---------------------------------------------------------------------------
# Tests des fragments d'URL du schemaLocation
# ---------------------------------------------------------------------------


class TestFragmentsUrl:
    """Validations des marqueurs d'URL utilisés pour détecter la version."""

    def test_fragment_v1_1_contient_tag_version(self):
        """Le fragment cible le tag RecoStar-v1.1 et non la branche main."""
        assert "RecoStar-v1.1" in FRAGMENT_URL_XSD_V1_1

    def test_fragment_main_distinct_de_v1_1(self):
        """Les deux fragments sont distincts pour permettre une détection sans ambiguïté."""
        assert FRAGMENT_URL_MAIN != FRAGMENT_URL_XSD_V1_1


# ---------------------------------------------------------------------------
# Tests des SRS autorisés
# ---------------------------------------------------------------------------


class TestSrsAutorises:
    """Catalogue d'EPSG conformes à PDF §10.6.1."""

    def test_est_frozenset(self):
        """L'ensemble est immuable et permet un lookup O(1)."""
        assert isinstance(SRS_AUTORISES, frozenset)

    def test_contient_rgf93_lambert_93(self):
        """RGF93 Lambert-93 (cas usuel métropolitain) est autorisé."""
        assert "EPSG:2154" in SRS_AUTORISES

    def test_contient_cc_zones(self):
        """Les Conic Conformal 42-50 sont tous présents."""
        for code in range(3942, 3951):
            assert f"EPSG:{code}" in SRS_AUTORISES

    def test_exclut_wgs84(self):
        """WGS84 n'est pas dans la liste fermée RecoStaR."""
        assert "EPSG:4326" not in SRS_AUTORISES


# ---------------------------------------------------------------------------
# Tests des séquences d'en-tête
# ---------------------------------------------------------------------------


class TestSequencesEntete:
    """Structure du catalogue SEQUENCES_ENTETE."""

    def test_types_attendus(self):
        """Le catalogue référence exactement Metadata et ReseauUtilite."""
        assert set(SEQUENCES_ENTETE.keys()) == {"Metadata", "ReseauUtilite"}

    def test_types_entete_aligne_sur_sequences(self):
        """TYPES_ENTETE et SEQUENCES_ENTETE désignent les mêmes types."""
        assert TYPES_ENTETE == frozenset(SEQUENCES_ENTETE.keys())

    def test_metadata_attendu_cinq_champs(self):
        """Metadata exige 5 champs obligatoires (PDF §[3])."""
        slots = SEQUENCES_ENTETE["Metadata"]
        assert len(slots) == 5
        noms = {s.nom for s in slots}
        assert noms == {"Datecreation", "Logiciel", "Producteur", "Responsable", "SRS"}

    def test_metadata_tous_obligatoires(self):
        """Chacun des champs Metadata est requis (min_occurs=1)."""
        for slot in SEQUENCES_ENTETE["Metadata"]:
            assert slot.min_occurs == 1, f"{slot.nom} doit être obligatoire"

    def test_reseau_utilite_attendu_quatre_champs(self):
        """ReseauUtilite exige 4 champs obligatoires (PDF §9)."""
        slots = SEQUENCES_ENTETE["ReseauUtilite"]
        assert len(slots) == 4
        noms = {s.nom for s in slots}
        assert noms == {"Mention", "Nom", "Responsable", "Theme"}

    def test_slots_sont_des_slotsequence(self):
        """Chaque slot est une instance SlotSequence (réutilisation moteur E110)."""
        for slots in SEQUENCES_ENTETE.values():
            for slot in slots:
                assert isinstance(slot, SlotSequence)


# ---------------------------------------------------------------------------
# Tests des cardinalités
# ---------------------------------------------------------------------------


class TestCardinalitesEntete:
    """Cardinalités attendues des objets d'en-tête au sein du fichier."""

    def test_metadata_singleton(self):
        """Exactement 1 Metadata par fichier (PDF §[3])."""
        assert CARDINALITES_ENTETE["Metadata"] == (1, 1)

    def test_reseau_utilite_au_moins_un(self):
        """Au moins 1 ReseauUtilite, plusieurs autorisés (tranches de travaux)."""
        cardinalite = CARDINALITES_ENTETE["ReseauUtilite"]
        assert cardinalite[0] == 1
        # max = -1 désigne « non borné » selon la convention SlotSequence.
        assert cardinalite[1] == -1

    def test_couvre_tous_les_types_entete(self):
        """Chaque type d'en-tête dispose d'une cardinalité documentée."""
        assert set(CARDINALITES_ENTETE.keys()) == set(TYPES_ENTETE)


# ---------------------------------------------------------------------------
# Tests de la classe ErreurEntete
# ---------------------------------------------------------------------------


class TestErreurEntete:
    """Comportement de la classe d'erreur."""

    def test_vers_dict_champs_complets(self):
        """vers_dict expose tous les attributs sérialisables."""
        err = ErreurEntete(
            code="CODE_TEST",
            element="ElemX",
            valeur_trouvee="A",
            valeur_attendue="B",
            message="msg",
        )
        attendus = {
            "code",
            "severite",
            "element",
            "valeur_trouvee",
            "valeur_attendue",
            "message",
        }
        assert set(err.vers_dict().keys()) == attendus

    def test_vers_dict_valeurs_correctes(self):
        """vers_dict reflète fidèlement les attributs de l'instance."""
        err = ErreurEntete("C", "E", "T", "A", "M")
        d = err.vers_dict()
        assert d["code"] == "C"
        assert d["element"] == "E"
        assert d["valeur_trouvee"] == "T"
        assert d["valeur_attendue"] == "A"
        assert d["message"] == "M"

    def test_valeurs_optionnelles_acceptent_none(self):
        """element, valeur_trouvee, valeur_attendue peuvent être None."""
        err = ErreurEntete("C", None, None, None, "msg")
        d = err.vers_dict()
        assert d["element"] is None
        assert d["valeur_trouvee"] is None
        assert d["valeur_attendue"] is None

    def test_slots_interdit_attributs_dynamiques(self):
        """__slots__ empêche l'ajout d'attributs non déclarés."""
        err = ErreurEntete("C", "E", "T", "A", "M")
        with pytest.raises(AttributeError):
            err.attribut_inconnu = "x"  # type: ignore[attr-defined]
