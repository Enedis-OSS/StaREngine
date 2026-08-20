"""
Tests unitaires du module priorites_structuration.

Couvre l'échelle de priorité, la ventilation, la conformité qui en découle, et
la propagation des deux dérogations aux deux versions supportées (V1.1 et V1.0).
"""

import pytest
from priorites_structuration import (
    CONFORME,
    NON_CONFORME,
    PRIORITE_BLOQUANT,
    PRIORITE_MAJEUR,
    PRIORITE_MINEUR,
    PRIORITE_PAR_DEFAUT,
    PRIORITES_DECLASSANTES,
    compter_bloquantes,
    statut_conformite,
    ventiler_par_priorite,
)
from regles_entete import PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN
from versions import VERSIONS_SUPPORTEES, resoudre_profil

# Identifiant de la seule règle de valeur dérogeant à la priorité par défaut.
_ID_REGLE_THEME = "E_THEME_RPD"


class _Anomalie:
    """Double de test minimal satisfaisant le protocole AnalomieStructuration."""

    __slots__ = ("priorite",)

    def __init__(self, priorite: str = PRIORITE_PAR_DEFAUT) -> None:
        self.priorite = priorite


# ---------------------------------------------------------------------------
# Échelle de priorité
# ---------------------------------------------------------------------------


class TestEchellePriorite:
    """Invariants de l'échelle, alignés sur synthese_controles."""

    def test_defaut_est_bloquant(self):
        """Le défaut protège : une règle non annotée ne relâche rien."""
        assert PRIORITE_PAR_DEFAUT == PRIORITE_BLOQUANT

    def test_seul_bloquant_declasse(self):
        assert PRIORITES_DECLASSANTES == frozenset({PRIORITE_BLOQUANT})

    def test_libelles_alignes_sur_la_synthese(self):
        """Les littéraux doivent rester ceux que `synthese_controles` connaît.

        Ce module ne peut pas importer `synthese_controles` (import à plat) :
        le test tient lieu de garde-fou contre une divergence silencieuse, qui
        ferait basculer toutes les anomalies en « non précisée » au rapport.
        """
        assert (PRIORITE_BLOQUANT, PRIORITE_MAJEUR, PRIORITE_MINEUR) == (
            "bloquant",
            "majeur",
            "mineur",
        )


# ---------------------------------------------------------------------------
# Ventilation
# ---------------------------------------------------------------------------


class TestVentilerParPriorite:
    """Comptage des anomalies par niveau."""

    def test_aucune_anomalie_ventilation_vide(self):
        """Pas de compteur à zéro : le rapport JSON reste lisible."""
        assert ventiler_par_priorite([]) == {}

    def test_priorite_unique(self):
        assert ventiler_par_priorite([_Anomalie(), _Anomalie()]) == {PRIORITE_BLOQUANT: 2}

    def test_priorites_melangees(self):
        anomalies = [
            _Anomalie(),
            _Anomalie(PRIORITE_MAJEUR),
            _Anomalie(PRIORITE_MINEUR),
            _Anomalie(PRIORITE_MINEUR),
        ]
        assert ventiler_par_priorite(anomalies) == {
            PRIORITE_BLOQUANT: 1,
            PRIORITE_MAJEUR: 1,
            PRIORITE_MINEUR: 2,
        }

    def test_total_conserve(self):
        """La ventilation ne perd aucune anomalie."""
        anomalies = [_Anomalie(PRIORITE_MAJEUR)] * 3 + [_Anomalie()] * 2
        assert sum(ventiler_par_priorite(anomalies).values()) == len(anomalies)


class TestCompterBloquantes:
    """Extraction du sous-total déclassant."""

    def test_ventilation_vide(self):
        assert compter_bloquantes({}) == 0

    def test_ignore_les_non_declassantes(self):
        assert compter_bloquantes({PRIORITE_MAJEUR: 4, PRIORITE_MINEUR: 7}) == 0

    def test_compte_les_declassantes(self):
        assert compter_bloquantes({PRIORITE_BLOQUANT: 3, PRIORITE_MINEUR: 7}) == 3


# ---------------------------------------------------------------------------
# Conformité
# ---------------------------------------------------------------------------


class TestStatutConformite:
    """Seules les anomalies bloquantes invalident la conformité."""

    def test_aucune_anomalie(self):
        assert statut_conformite({}) == CONFORME

    @pytest.mark.parametrize("priorite", [PRIORITE_MAJEUR, PRIORITE_MINEUR])
    def test_non_bloquante_reste_conforme(self, priorite: str):
        assert statut_conformite({priorite: 12}) == CONFORME

    def test_bloquante_declasse(self):
        assert statut_conformite({PRIORITE_BLOQUANT: 1}) == NON_CONFORME

    def test_une_seule_bloquante_suffit(self):
        ventilation = {PRIORITE_BLOQUANT: 1, PRIORITE_MAJEUR: 40, PRIORITE_MINEUR: 90}
        assert statut_conformite(ventilation) == NON_CONFORME


# ---------------------------------------------------------------------------
# Dérogations effectivement en service
# ---------------------------------------------------------------------------


class TestDerogations:
    """Les deux seules règles dérogeant à la priorité bloquante."""

    def test_schema_location_branche_main_est_majeure(self):
        assert PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN == PRIORITE_MAJEUR

    @pytest.mark.parametrize("version", sorted(VERSIONS_SUPPORTEES))
    def test_theme_mineur_dans_toutes_les_versions(self, version: str):
        """La V1.0 dérive son catalogue de la V1.1 : la dérogation doit suivre."""
        index = resoudre_profil(version).index_regles_valeurs
        regle = index[("ReseauUtilite", "Theme")]
        assert regle.identifiant == _ID_REGLE_THEME
        assert regle.priorite == PRIORITE_MINEUR

    @pytest.mark.parametrize("version", sorted(VERSIONS_SUPPORTEES))
    def test_aucune_autre_derogation_dans_les_catalogues(self, version: str):
        """Garde-fou : la modification ne doit pas s'être propagée ailleurs."""
        index = resoudre_profil(version).index_regles_valeurs
        derogations = {r.identifiant for r in index.values() if r.priorite != PRIORITE_BLOQUANT}
        assert derogations == {_ID_REGLE_THEME}
