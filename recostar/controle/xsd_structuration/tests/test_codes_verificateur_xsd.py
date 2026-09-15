#!/usr/bin/env python3
"""Tests de la correspondance des regles de structuration vers les codes du verificateur."""

import pytest

from recostar.controle.xsd_structuration import regles_document, regles_entete, regles_geometrie, regles_srs_dimension
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
    codes_version,
)
from recostar.controle.xsd_structuration.codes_verificateur_xsd import (
    CODE_PAR_DEFAUT_RANG,
    CORRESPONDANCES_XSD,
    REGLES_SANS_CODE,
    VERSION_REFERENTIEL,
    codes_possibles_rang,
    rang_depuis_code_controle,
    resoudre_code_erreur_xsd,
)

# Codes de regle emis par le sequenceur d'ordre (E0110 / E0010).
REGLES_ORDRE: frozenset[str] = frozenset({"ELEMENT_REQUIS_MANQUANT", "ORDRE_INCORRECT", "ELEMENT_INATTENDU"})


def _codes_declares(module) -> frozenset[str]:
    """Releve les codes de regle declares par un module de regles."""
    return frozenset(
        valeur for nom, valeur in vars(module).items() if nom.startswith("CODE_") and isinstance(valeur, str)
    )


def _regles_entete() -> frozenset[str]:
    """Releve les codes de regle declares par `regles_entete`."""
    return _codes_declares(regles_entete)


def _regles_geometrie() -> frozenset[str]:
    """Releve les codes de regle declares par `regles_geometrie` (E0115 / E0015)."""
    return _codes_declares(regles_geometrie)


def _regles_document() -> set[str]:
    """Codes de regle emis par E0118 / E0018, releves a la source."""
    return {regles_document.CODE_ILLISIBLE, regles_document.CODE_VIDE}


def _regles_srs_dimension() -> set[str]:
    """Codes de regle emis par E0119 / E0019, releves a la source."""
    return {
        regles_srs_dimension.CODE_ABSENTE,
        regles_srs_dimension.CODE_INCORRECTE,
        regles_srs_dimension.CODE_INCOHERENTE,
    }


def _regles_emises() -> set[tuple[int, str]]:
    """Tous les couples (rang, code de regle) que la famille sait produire."""
    return (
        {(RANG_ORDRE, r) for r in REGLES_ORDRE}
        | {(RANG_ENTETE, r) for r in _regles_entete()}
        | {(RANG_GEOMETRIE, r) for r in _regles_geometrie()}
        | {(RANG_DOCUMENT, r) for r in _regles_document()}
        | {(RANG_SRS_DIMENSION, r) for r in _regles_srs_dimension()}
    )


class TestIntegriteTable:
    """La table doit rester lisible et coherente avec l'echelle des rangs."""

    def test_version_alignee_sur_le_referentiel(self) -> None:
        assert VERSION_REFERENTIEL == "2.14.0"

    def test_defauts_couvrent_tous_les_rangs(self) -> None:
        assert len(CODE_PAR_DEFAUT_RANG) == NB_CONTROLES

    def test_rangs_de_la_table_valides(self) -> None:
        for rang, _regle in CORRESPONDANCES_XSD:
            assert 0 <= rang < NB_CONTROLES

    def test_format_des_codes_erreur(self) -> None:
        codes = set(CORRESPONDANCES_XSD.values()) | {c for c in CODE_PAR_DEFAUT_RANG if c is not None}
        for code in codes:
            assert code.startswith("E-"), code
            assert code[2:].isdigit() and len(code[2:]) == 4, code

    def test_aucune_regle_a_la_fois_correspondue_et_ecartee(self) -> None:
        assert not REGLES_SANS_CODE & set(CORRESPONDANCES_XSD)


class TestExhaustivite:
    """Toute regle emise doit etre soit correspondue, soit ecartee explicitement."""

    def test_regles_ordre_statuees(self) -> None:
        for regle in REGLES_ORDRE:
            cle = (RANG_ORDRE, regle)
            assert cle in CORRESPONDANCES_XSD or cle in REGLES_SANS_CODE, regle

    def test_regles_entete_statuees(self) -> None:
        for regle in _regles_entete():
            cle = (RANG_ENTETE, regle)
            assert cle in CORRESPONDANCES_XSD or cle in REGLES_SANS_CODE, regle

    def test_releve_entete_non_vide(self) -> None:
        """Garde-fou du releve : un extracteur muet rendrait le test precedent vert."""
        assert len(_regles_entete()) >= 11

    def test_regles_geometrie_statuees(self) -> None:
        for regle in _regles_geometrie():
            cle = (RANG_GEOMETRIE, regle)
            assert cle in CORRESPONDANCES_XSD or cle in REGLES_SANS_CODE, regle

    def test_releve_geometrie_non_vide(self) -> None:
        """Garde-fou du releve : E0115 emet deux codes de regle."""
        assert len(_regles_geometrie()) == 2

    def test_aucune_regle_ecartee_orpheline(self) -> None:
        assert REGLES_SANS_CODE <= _regles_emises()

    def test_aucune_correspondance_orpheline(self) -> None:
        assert set(CORRESPONDANCES_XSD) <= _regles_emises()


class TestResolution:
    """Comportement de `resoudre_code_erreur_xsd`."""

    def test_correspondance_explicite(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_ENTETE, "GML_ID_DUPLIQUE") == "E-0008"

    def test_deux_regles_vers_un_meme_code(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_ENTETE, "NAMESPACE_MANQUANT") == "E-1103"
        assert resoudre_code_erreur_xsd(RANG_ENTETE, "NAMESPACE_URI_INCORRECTE") == "E-1103"

    def test_code_par_defaut_du_controle(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_XSD_NATIF, "N_IMPORTE_QUOI") == "E-1104"
        assert resoudre_code_erreur_xsd(RANG_METIER, "E_DOMAINE_TENSION") == "E-2102"
        assert resoudre_code_erreur_xsd(RANG_VALEURS, "VALEUR_HORS_DOMAINE") == "E-2100"

    def test_regle_absente_sans_defaut(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_ORDRE, "REGLE_INCONNUE") is None

    def test_regle_ecartee(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_ORDRE, "ORDRE_INCORRECT") is None
        assert resoudre_code_erreur_xsd(RANG_ENTETE, "CHAMP_HORS_ORDRE") is None

    def test_regle_nulle_retombe_sur_le_defaut(self) -> None:
        assert resoudre_code_erreur_xsd(RANG_XSD_NATIF, None) == "E-1104"
        assert resoudre_code_erreur_xsd(RANG_ORDRE, None) is None

    def test_rang_hors_echelle(self) -> None:
        assert resoudre_code_erreur_xsd(-1, "GML_ID_DUPLIQUE") is None
        assert resoudre_code_erreur_xsd(NB_CONTROLES, "GML_ID_DUPLIQUE") is None


class TestRangDepuisCodeControle:
    """Le rang doit se deduire du code affichable, quelle que soit la version."""

    def test_series_e11x_et_e01x_partagent_le_rang(self) -> None:
        assert rang_depuis_code_controle("E0113") == rang_depuis_code_controle("E0013") == RANG_ENTETE

    def test_tous_les_codes_courants_resolus(self) -> None:
        for rang, code in enumerate(codes_version()):
            assert rang_depuis_code_controle(code) == rang

    def test_code_vide(self) -> None:
        assert rang_depuis_code_controle("") is None

    def test_code_non_numerique(self) -> None:
        assert rang_depuis_code_controle("E11X") is None

    def test_rang_hors_echelle(self) -> None:
        assert rang_depuis_code_controle("E0130") is None


class TestCodesPossiblesRang:
    """Codes du verificateur couverts par un controle de structuration."""

    def test_rang_a_code_unique(self):
        """Un controle dont toutes les regles partagent un code n'en rend qu'un."""
        assert codes_possibles_rang(RANG_XSD_NATIF) == ("E-1104",)

    def test_rang_a_codes_multiples(self):
        """Un controle transverse rend tous les codes qu'il couvre, tries."""
        codes = codes_possibles_rang(RANG_ORDRE)
        assert codes == tuple(sorted(codes))
        assert len(codes) > 1
        assert all(code.startswith("E-") for code in codes)

    def test_regles_sans_code_absentes(self):
        """Une regle declaree sans equivalent n'ajoute aucun code."""
        assert "ORDRE_INCORRECT" not in codes_possibles_rang(RANG_ORDRE)

    @pytest.mark.parametrize("rang", [-1, NB_CONTROLES, 999])
    def test_rang_hors_bornes(self, rang):
        """Un rang inconnu ne rend aucun code plutot que de lever."""
        assert codes_possibles_rang(rang) == ()
