"""
Tests du modele normalise des resultats de controle.

Couvre :
  - la ventilation des anomalies par priorite (trois conventions de rapport)
  - la normalisation d'un controle (succes / echec)
  - le statut d'une famille (Conforme / Non conforme / Incomplet / Non execute)
  - les priorites effectivement presentes
  - l'agregation globale
"""

from synthese_controles import (
    ORDRE_PRIORITES,
    PRIORITE_BLOQUANT,
    PRIORITE_INCONNUE,
    PRIORITE_INFORMATION,
    STATUT_CONFORME,
    STATUT_INCOMPLET,
    STATUT_NON_CONFORME,
    STATUT_NON_EXECUTE,
    ResultatControle,
    ResultatFamille,
    agreger,
    nombre_anomalies_rapport,
    normaliser_controle,
    priorites_presentes,
    ventiler_anomalies,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _controle(
    code: str = "E500",
    succes: bool = True,
    nombre: int = 0,
    priorites: dict[str, int] | None = None,
) -> ResultatControle:
    """ResultatControle minimal pour les tests d'agregation."""
    return ResultatControle(
        code=code,
        libelle=f"Libelle {code}",
        succes=succes,
        nombre_anomalies=nombre,
        anomalies_par_priorite=priorites or {},
        erreur=None if succes else "motif",
    )


# --------------------------------------------------------------------------- #
# Extraction du nombre d'anomalies
# --------------------------------------------------------------------------- #


class TestNombreAnomaliesRapport:
    """Tests de nombre_anomalies_rapport."""

    def test_convention_geojson(self) -> None:
        assert nombre_anomalies_rapport({"nombre_anomalies": 4}) == 4

    def test_convention_xsd(self) -> None:
        """Le pipeline de structuration expose nb_erreurs, pas nombre_anomalies."""
        assert nombre_anomalies_rapport({"nb_erreurs": 7}) == 7

    def test_aucune_cle(self) -> None:
        assert nombre_anomalies_rapport({}) == 0

    def test_valeur_non_numerique_ignoree(self) -> None:
        assert nombre_anomalies_rapport({"nombre_anomalies": "beaucoup"}) == 0


# --------------------------------------------------------------------------- #
# Ventilation par priorite
# --------------------------------------------------------------------------- #


class TestVentilerAnomalies:
    """Tests de ventiler_anomalies."""

    def test_priorite_scalaire(self) -> None:
        """Convention majoritaire (E200 a E507 hors E506)."""
        rapport = {"nombre_anomalies": 3, "priorite": PRIORITE_BLOQUANT}
        assert ventiler_anomalies(rapport) == {PRIORITE_BLOQUANT: 3}

    def test_multi_priorites_convention_e506(self) -> None:
        """Un controle multi-regles ventile ses anomalies par type."""
        rapport = {
            "nombre_anomalies": 18,
            "priorites": {
                "cable_sans_noeud": PRIORITE_BLOQUANT,
                "extremite_non_raccordee": PRIORITE_BLOQUANT,
                "cable_terre_non_raccorde": PRIORITE_INFORMATION,
            },
            "anomalies_par_type": {
                "cable_sans_noeud": 1,
                "extremite_non_raccordee": 1,
                "cable_terre_non_raccorde": 16,
            },
        }
        assert ventiler_anomalies(rapport) == {PRIORITE_BLOQUANT: 2, PRIORITE_INFORMATION: 16}

    def test_priorite_par_defaut_de_la_famille(self) -> None:
        """Le pipeline XSD ne porte pas de priorite : celle de la famille s'applique."""
        rapport = {"nb_erreurs": 5, "conformite": "NON_CONFORME"}
        assert ventiler_anomalies(rapport, PRIORITE_BLOQUANT) == {PRIORITE_BLOQUANT: 5}

    def test_priorite_absente_sans_defaut(self) -> None:
        assert ventiler_anomalies({"nombre_anomalies": 2}) == {PRIORITE_INCONNUE: 2}

    def test_aucune_anomalie(self) -> None:
        assert ventiler_anomalies({"nombre_anomalies": 0, "priorite": PRIORITE_BLOQUANT}) == {}

    def test_type_non_declare_dans_priorites(self) -> None:
        rapport = {
            "nombre_anomalies": 2,
            "priorites": {"connu": PRIORITE_BLOQUANT},
            "anomalies_par_type": {"connu": 1, "inconnu": 1},
        }
        assert ventiler_anomalies(rapport) == {PRIORITE_BLOQUANT: 1, PRIORITE_INCONNUE: 1}


# --------------------------------------------------------------------------- #
# Normalisation d'un controle
# --------------------------------------------------------------------------- #


class TestNormaliserControle:
    """Tests de normaliser_controle."""

    def test_controle_reussi(self) -> None:
        rapport = {"succes": True, "nombre_anomalies": 2, "priorite": PRIORITE_BLOQUANT}
        resultat = normaliser_controle("E500", "Libelle", rapport)
        assert resultat.succes is True
        assert resultat.nombre_anomalies == 2
        assert resultat.anomalies_par_priorite == {PRIORITE_BLOQUANT: 2}
        assert resultat.erreur is None

    def test_controle_en_echec(self) -> None:
        """Un controle en echec ne porte aucune anomalie exploitable."""
        rapport = {"succes": False, "erreur": "Fichier introuvable"}
        resultat = normaliser_controle("E303", "Libelle", rapport)
        assert resultat.succes is False
        assert resultat.nombre_anomalies == 0
        assert resultat.anomalies_par_priorite == {}
        assert resultat.erreur == "Fichier introuvable"

    def test_echec_sans_motif(self) -> None:
        resultat = normaliser_controle("E303", "Libelle", {"succes": False})
        assert resultat.erreur == "Echec non precise"


# --------------------------------------------------------------------------- #
# Statut d'une famille
# --------------------------------------------------------------------------- #


class TestStatutFamille:
    """Tests de ResultatFamille.statut."""

    def test_conforme(self) -> None:
        famille = ResultatFamille("cable", "Cable", (_controle(), _controle("E501")))
        assert famille.statut == STATUT_CONFORME

    def test_non_conforme_si_anomalie_bloquante(self) -> None:
        famille = ResultatFamille("cable", "Cable", (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}),))
        assert famille.statut == STATUT_NON_CONFORME

    def test_conforme_malgre_anomalies_information(self) -> None:
        """Une anomalie d'information est comptee mais ne declasse pas."""
        famille = ResultatFamille("cable", "Cable", (_controle(nombre=16, priorites={PRIORITE_INFORMATION: 16}),))
        assert famille.statut == STATUT_CONFORME
        assert famille.nombre_anomalies == 16

    def test_incomplet_si_controle_en_echec(self) -> None:
        """Aucun defaut bloquant, mais la conformite n'est pas verifiable."""
        famille = ResultatFamille("projection", "Projection", (_controle(), _controle("E303", succes=False)))
        assert famille.statut == STATUT_INCOMPLET

    def test_non_conforme_prime_sur_incomplet(self) -> None:
        """Un defaut avere reste avere, meme si la verification est partielle."""
        famille = ResultatFamille(
            "projection",
            "Projection",
            (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}), _controle("E303", succes=False)),
        )
        assert famille.statut == STATUT_NON_CONFORME

    def test_non_execute(self) -> None:
        famille = ResultatFamille("structuration", "Structuration", execute=False, motif="Aucun GML")
        assert famille.statut == STATUT_NON_EXECUTE

    def test_famille_vide_est_conforme(self) -> None:
        assert ResultatFamille("x", "X").statut == STATUT_CONFORME


class TestAgregationFamille:
    """Tests des proprietes d'agregation de ResultatFamille."""

    def test_nombre_controles(self) -> None:
        famille = ResultatFamille("c", "C", (_controle("E1"), _controle("E2")))
        assert famille.nombre_controles == 2

    def test_nombre_anomalies(self) -> None:
        famille = ResultatFamille("c", "C", (_controle(nombre=2), _controle("E2", nombre=3)))
        assert famille.nombre_anomalies == 5

    def test_ventilation_cumulee(self) -> None:
        famille = ResultatFamille(
            "c",
            "C",
            (
                _controle("E1", nombre=2, priorites={PRIORITE_BLOQUANT: 2}),
                _controle("E2", nombre=4, priorites={PRIORITE_BLOQUANT: 1, PRIORITE_INFORMATION: 3}),
            ),
        )
        assert famille.anomalies_par_priorite == {PRIORITE_BLOQUANT: 3, PRIORITE_INFORMATION: 3}

    def test_controles_en_echec(self) -> None:
        famille = ResultatFamille("c", "C", (_controle("E1"), _controle("E2", succes=False)))
        assert famille.controles_en_echec == ("E2",)


# --------------------------------------------------------------------------- #
# Priorites presentes
# --------------------------------------------------------------------------- #


class TestPrioritesPresentes:
    """Tests de priorites_presentes."""

    def test_ordre_de_gravite(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(nombre=1, priorites={PRIORITE_INFORMATION: 1}),)),
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}),)),
        )
        assert priorites_presentes(familles) == (PRIORITE_BLOQUANT, PRIORITE_INFORMATION)

    def test_seules_les_priorites_alimentees(self) -> None:
        """Aucune colonne vide n'est affichee dans le rapport."""
        familles = (ResultatFamille("a", "A", (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}),)),)
        assert priorites_presentes(familles) == (PRIORITE_BLOQUANT,)

    def test_aucune_anomalie(self) -> None:
        assert priorites_presentes((ResultatFamille("a", "A", (_controle(),)),)) == ()

    def test_ordre_priorites_couvre_les_libelles(self) -> None:
        from synthese_controles import LIBELLES_PRIORITES

        assert set(ORDRE_PRIORITES) == set(LIBELLES_PRIORITES)


# --------------------------------------------------------------------------- #
# Agregation globale
# --------------------------------------------------------------------------- #


class TestAgreger:
    """Tests de agreger."""

    def test_statut_global_conforme(self) -> None:
        familles = (ResultatFamille("a", "A", (_controle(),)),)
        assert agreger(familles)["statut_global"] == STATUT_CONFORME

    def test_statut_global_non_conforme(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(),)),
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}),)),
        )
        synthese = agreger(familles)
        assert synthese["statut_global"] == STATUT_NON_CONFORME
        assert synthese["familles_non_conformes"] == ("b",)

    def test_statut_global_incomplet(self) -> None:
        familles = (ResultatFamille("a", "A", (_controle("E1", succes=False),)),)
        synthese = agreger(familles)
        assert synthese["statut_global"] == STATUT_INCOMPLET
        assert synthese["familles_incompletes"] == ("a",)
        assert synthese["nombre_controles_en_echec"] == 1

    def test_non_conforme_prime_sur_incomplet(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle("E1", succes=False),)),
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_BLOQUANT: 1}),)),
        )
        assert agreger(familles)["statut_global"] == STATUT_NON_CONFORME

    def test_famille_non_executee_exclue_des_totaux(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(nombre=2, priorites={PRIORITE_BLOQUANT: 2}),)),
            ResultatFamille("b", "B", execute=False, motif="Aucune donnee"),
        )
        synthese = agreger(familles)
        assert synthese["nombre_familles_executees"] == 1
        assert synthese["nombre_anomalies_total"] == 2

    def test_ventilation_globale(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(nombre=2, priorites={PRIORITE_BLOQUANT: 2}),)),
            ResultatFamille("b", "B", (_controle("E2", nombre=3, priorites={PRIORITE_INFORMATION: 3}),)),
        )
        assert agreger(familles)["anomalies_par_priorite"] == {PRIORITE_BLOQUANT: 2, PRIORITE_INFORMATION: 3}
