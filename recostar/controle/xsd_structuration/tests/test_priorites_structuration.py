"""
Tests unitaires du module priorites_structuration.

Couvre l'échelle de priorité, la ventilation, la conformité qui en découle, et
la propagation des deux dérogations aux deux versions supportées (V1.1 et V1.0).
"""

import pytest

from recostar.controle.xsd_structuration.priorites_structuration import (
    CONFORME,
    NON_CONFORME,
    PRIORITE_BASSE,
    PRIORITE_FORTE,
    PRIORITE_MOYENNE,
    PRIORITE_PAR_DEFAUT,
    PRIORITES_DECLASSANTES,
    compter_bloquantes,
    statut_conformite,
    ventiler_par_priorite,
)
from recostar.controle.xsd_structuration.regles_entete import PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN
from recostar.controle.xsd_structuration.versions import VERSIONS_SUPPORTEES, resoudre_profil

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
        assert PRIORITE_PAR_DEFAUT == PRIORITE_FORTE

    def test_seule_la_priorite_forte_declasse(self):
        """`bloquante` est ramenee a `forte` ici : elle n'a pas d'existence propre."""
        assert PRIORITES_DECLASSANTES == frozenset({PRIORITE_FORTE})

    def test_libelles_alignes_sur_la_synthese(self):
        """Les littéraux doivent rester ceux que `synthese_controles` connaît.

        Ce module ne peut pas importer `synthese_controles` (import à plat) :
        le test tient lieu de garde-fou contre une divergence silencieuse, qui
        ferait basculer toutes les anomalies en « non précisée » au rapport.
        """
        assert (PRIORITE_FORTE, PRIORITE_MOYENNE, PRIORITE_BASSE) == (
            "forte",
            "moyenne",
            "basse",
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
        assert ventiler_par_priorite([_Anomalie(), _Anomalie()]) == {PRIORITE_FORTE: 2}

    def test_priorites_melangees(self):
        anomalies = [
            _Anomalie(),
            _Anomalie(PRIORITE_MOYENNE),
            _Anomalie(PRIORITE_BASSE),
            _Anomalie(PRIORITE_BASSE),
        ]
        assert ventiler_par_priorite(anomalies) == {
            PRIORITE_FORTE: 1,
            PRIORITE_MOYENNE: 1,
            PRIORITE_BASSE: 2,
        }

    def test_total_conserve(self):
        """La ventilation ne perd aucune anomalie."""
        anomalies = [_Anomalie(PRIORITE_MOYENNE)] * 3 + [_Anomalie()] * 2
        assert sum(ventiler_par_priorite(anomalies).values()) == len(anomalies)


class TestCompterBloquantes:
    """Extraction du sous-total déclassant."""

    def test_ventilation_vide(self):
        assert compter_bloquantes({}) == 0

    def test_ignore_les_non_declassantes(self):
        assert compter_bloquantes({PRIORITE_MOYENNE: 4, PRIORITE_BASSE: 7}) == 0

    def test_compte_les_declassantes(self):
        assert compter_bloquantes({PRIORITE_FORTE: 3, PRIORITE_BASSE: 7}) == 3


# ---------------------------------------------------------------------------
# Conformité
# ---------------------------------------------------------------------------


class TestStatutConformite:
    """Seules les anomalies bloquantes invalident la conformité."""

    def test_aucune_anomalie(self):
        assert statut_conformite({}) == CONFORME

    @pytest.mark.parametrize("priorite", [PRIORITE_MOYENNE, PRIORITE_BASSE])
    def test_non_bloquante_reste_conforme(self, priorite: str):
        assert statut_conformite({priorite: 12}) == CONFORME

    def test_bloquante_declasse(self):
        assert statut_conformite({PRIORITE_FORTE: 1}) == NON_CONFORME

    def test_une_seule_bloquante_suffit(self):
        ventilation = {PRIORITE_FORTE: 1, PRIORITE_MOYENNE: 40, PRIORITE_BASSE: 90}
        assert statut_conformite(ventilation) == NON_CONFORME


# ---------------------------------------------------------------------------
# Dérogations effectivement en service
# ---------------------------------------------------------------------------


class TestDerogations:
    """Les deux seules règles dérogeant à la priorité bloquante."""

    def test_schema_location_branche_main_est_majeure(self):
        assert PRIORITE_SCHEMA_LOCATION_BRANCHE_MAIN == PRIORITE_MOYENNE

    @pytest.mark.parametrize("version", sorted(VERSIONS_SUPPORTEES))
    def test_theme_mineur_dans_toutes_les_versions(self, version: str):
        """La V1.0 dérive son catalogue de la V1.1 : la dérogation doit suivre."""
        index = resoudre_profil(version).index_regles_valeurs
        regle = index[("ReseauUtilite", "Theme")]
        assert regle.identifiant == _ID_REGLE_THEME
        assert regle.priorite == PRIORITE_BASSE

    @pytest.mark.parametrize("version", sorted(VERSIONS_SUPPORTEES))
    def test_aucune_autre_derogation_dans_les_catalogues(self, version: str):
        """Garde-fou : la modification ne doit pas s'être propagée ailleurs."""
        index = resoudre_profil(version).index_regles_valeurs
        derogations = {r.identifiant for r in index.values() if r.priorite != PRIORITE_FORTE}
        assert derogations == {_ID_REGLE_THEME}
