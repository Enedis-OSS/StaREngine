"""
Tests du module codes_controle : identité des contrôles selon la version.

Vérifient la correspondance version → code (V1.1 → E110-E114, V1.0 →
E010-E014), la cohérence des trois formes dérivées (code, `type_controle`,
suffixe de rapport) et le rejet des rangs hors périmètre.
"""

import pytest
import versions
from codes_controle import (
    NB_CONTROLES,
    RANG_ENTETE,
    RANG_METIER,
    RANG_ORDRE,
    RANG_VALEURS,
    RANG_XSD_NATIF,
    SUFFIXES_TYPE,
    codes_version,
    identite_controle,
)

# Codes attendus par version, dans l'ordre d'exécution des contrôles.
CODES_V1_1 = ("E110", "E111", "E112", "E113", "E114")
CODES_V1_0 = ("E010", "E011", "E012", "E013", "E014")


class TestRangs:
    """Les rangs couvrent exactement les cinq contrôles de la famille."""

    def test_rangs_distincts_et_ordonnes(self) -> None:
        rangs = (RANG_ORDRE, RANG_METIER, RANG_XSD_NATIF, RANG_ENTETE, RANG_VALEURS)
        assert rangs == tuple(range(NB_CONTROLES))

    def test_nb_controles_coherent_avec_les_suffixes(self) -> None:
        assert NB_CONTROLES == len(SUFFIXES_TYPE) == 5


class TestCodesParVersion:
    """La série de codes appliquée dépend de la version contrôlée."""

    def test_codes_v1_1(self) -> None:
        assert codes_version("1.1") == CODES_V1_1

    def test_codes_v1_0(self) -> None:
        assert codes_version("1.0") == CODES_V1_0

    def test_series_disjointes(self) -> None:
        """Aucun code n'est partagé entre les deux versions."""
        assert set(CODES_V1_0).isdisjoint(CODES_V1_1)

    def test_toutes_les_versions_supportees_ont_une_serie(self) -> None:
        for version in versions.VERSIONS_SUPPORTEES:
            assert len(codes_version(version)) == NB_CONTROLES


class TestIdentiteControle:
    """Les trois formes dérivées restent cohérentes entre elles."""

    @pytest.mark.parametrize(
        ("version", "rang", "code", "type_controle", "suffixe"),
        [
            ("1.1", RANG_ORDRE, "E110", "E110_ORDRE", "_controle_e110.json"),
            ("1.1", RANG_VALEURS, "E114", "E114_VALEURS", "_controle_e114.json"),
            ("1.0", RANG_ORDRE, "E010", "E010_ORDRE", "_controle_e010.json"),
            ("1.0", RANG_METIER, "E011", "E011_METIER", "_controle_e011.json"),
            ("1.0", RANG_XSD_NATIF, "E012", "E012_XSD_NATIF", "_controle_e012.json"),
            ("1.0", RANG_ENTETE, "E013", "E013_ENTETE", "_controle_e013.json"),
            ("1.0", RANG_VALEURS, "E014", "E014_VALEURS", "_controle_e014.json"),
        ],
    )
    def test_identites_attendues(
        self,
        version: str,
        rang: int,
        code: str,
        type_controle: str,
        suffixe: str,
    ) -> None:
        identite = identite_controle(version, rang)
        assert identite.code == code
        assert identite.type_controle == type_controle
        assert identite.suffixe_rapport == suffixe

    def test_suffixe_derive_du_code(self) -> None:
        """Le suffixe de rapport est toujours le code en minuscules."""
        for version in versions.VERSIONS_SUPPORTEES:
            for rang in range(NB_CONTROLES):
                identite = identite_controle(version, rang)
                assert identite.suffixe_rapport == f"_controle_{identite.code.lower()}.json"

    def test_type_controle_derive_du_code_et_du_suffixe(self) -> None:
        for version in versions.VERSIONS_SUPPORTEES:
            for rang in range(NB_CONTROLES):
                identite = identite_controle(version, rang)
                assert identite.type_controle == f"{identite.code}_{SUFFIXES_TYPE[rang]}"

    def test_version_par_defaut(self) -> None:
        """Sans argument, l'identité porte celle de la version par défaut."""
        attendu = identite_controle(versions.VERSION_DEFAUT, RANG_ORDRE)
        assert identite_controle() == attendu

    def test_identite_immuable(self) -> None:
        identite = identite_controle("1.0", RANG_ORDRE)
        with pytest.raises(AttributeError):
            identite.code = "E999"  # type: ignore[misc]


class TestCasLimites:
    """Rangs et versions hors périmètre sont rejetés explicitement."""

    @pytest.mark.parametrize("rang", [-1, NB_CONTROLES, 42])
    def test_rang_invalide(self, rang: int) -> None:
        with pytest.raises(ValueError, match="Rang de contrôle XSD inconnu"):
            identite_controle("1.1", rang)

    def test_version_inconnue(self) -> None:
        with pytest.raises(ValueError, match="Version RecoStaR inconnue"):
            identite_controle("9.9", RANG_ORDRE)


class TestPrefixesProfils:
    """Chaque profil de version déclare un préfixe de code unique."""

    def test_prefixes_declares(self) -> None:
        assert versions.resoudre_profil("1.0").prefixe_code == "E01"
        assert versions.resoudre_profil("1.1").prefixe_code == "E11"

    def test_prefixes_uniques(self) -> None:
        prefixes = [versions.resoudre_profil(v).prefixe_code for v in versions.VERSIONS_SUPPORTEES]
        assert len(set(prefixes)) == len(prefixes)
