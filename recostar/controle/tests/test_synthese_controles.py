"""
Tests du modele normalise des resultats de controle.

Couvre :
  - la ventilation des anomalies par priorite (quatre conventions de rapport)
  - la normalisation d'un controle (succes / echec)
  - le statut d'une famille (Conforme / Non conforme / Incomplet / Non execute)
  - les priorites effectivement presentes
  - l'agregation globale
"""

from recostar.controle.synthese_controles import (
    LIBELLES_PRIORITES,
    ORDRE_PRIORITES,
    PRIORITE_BASSE,
    PRIORITE_BLOQUANTE,
    PRIORITE_FORTE,
    PRIORITE_INCONNUE,
    PRIORITE_MOYENNE,
    PRIORITES_DECLASSANTES,
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
    code: str = "E-9500",
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
        """Convention majoritaire des controles GeoJSON."""
        rapport = {"nombre_anomalies": 3, "priorite": PRIORITE_FORTE}
        assert ventiler_anomalies(rapport) == {PRIORITE_FORTE: 3}

    def test_ventilation_prete_convention_xsd(self) -> None:
        """Le pipeline XSD ventile lui-meme : sa ventilation est reprise telle quelle."""
        rapport = {
            "nb_erreurs": 7,
            "anomalies_par_priorite": {PRIORITE_FORTE: 5, PRIORITE_MOYENNE: 1, PRIORITE_BASSE: 1},
        }
        assert ventiler_anomalies(rapport) == {
            PRIORITE_FORTE: 5,
            PRIORITE_MOYENNE: 1,
            PRIORITE_BASSE: 1,
        }

    def test_ventilation_prete_prime_sur_la_priorite_par_defaut(self) -> None:
        """Une ventilation etablie a la source fait autorite sur le defaut famille."""
        rapport = {"nb_erreurs": 1, "anomalies_par_priorite": {PRIORITE_MOYENNE: 1}}
        assert ventiler_anomalies(rapport, PRIORITE_FORTE) == {PRIORITE_MOYENNE: 1}

    def test_ventilation_prete_vide_retombe_sur_le_defaut(self) -> None:
        """Une ventilation absente ou vide laisse le repli famille s'appliquer."""
        rapport = {"nb_erreurs": 4, "anomalies_par_priorite": {}}
        assert ventiler_anomalies(rapport, PRIORITE_FORTE) == {PRIORITE_FORTE: 4}

    def test_multi_priorites_convention_e0506(self) -> None:
        """Un controle multi-regles ventile ses anomalies par type."""
        rapport = {
            "nombre_anomalies": 18,
            "priorites": {
                "cable_sans_noeud": PRIORITE_FORTE,
                "extremite_non_raccordee": PRIORITE_FORTE,
                "cable_terre_non_raccorde": PRIORITE_BASSE,
            },
            "anomalies_par_type": {
                "cable_sans_noeud": 1,
                "extremite_non_raccordee": 1,
                "cable_terre_non_raccorde": 16,
            },
        }
        assert ventiler_anomalies(rapport) == {PRIORITE_FORTE: 2, PRIORITE_BASSE: 16}

    def test_priorite_par_defaut_de_la_famille(self) -> None:
        """Rapport sans aucune priorite : celle de la famille s'applique."""
        rapport = {"nb_erreurs": 5, "conformite": "NON_CONFORME"}
        assert ventiler_anomalies(rapport, PRIORITE_FORTE) == {PRIORITE_FORTE: 5}

    def test_priorite_absente_sans_defaut(self) -> None:
        assert ventiler_anomalies({"nombre_anomalies": 2}) == {PRIORITE_INCONNUE: 2}

    def test_aucune_anomalie(self) -> None:
        assert ventiler_anomalies({"nombre_anomalies": 0, "priorite": PRIORITE_FORTE}) == {}

    def test_type_non_declare_dans_priorites(self) -> None:
        rapport = {
            "nombre_anomalies": 2,
            "priorites": {"connu": PRIORITE_FORTE},
            "anomalies_par_type": {"connu": 1, "inconnu": 1},
        }
        assert ventiler_anomalies(rapport) == {PRIORITE_FORTE: 1, PRIORITE_INCONNUE: 1}


# --------------------------------------------------------------------------- #
# Normalisation d'un controle
# --------------------------------------------------------------------------- #


class TestNormaliserControle:
    """Tests de normaliser_controle."""

    def test_controle_reussi(self) -> None:
        rapport = {"succes": True, "nombre_anomalies": 2, "priorite": PRIORITE_FORTE}
        resultat = normaliser_controle("E-9500", "Libelle", rapport)
        assert resultat.succes is True
        assert resultat.nombre_anomalies == 2
        assert resultat.anomalies_par_priorite == {PRIORITE_FORTE: 2}
        assert resultat.erreur is None

    def test_controle_en_echec(self) -> None:
        """Un controle en echec ne porte aucune anomalie exploitable."""
        rapport = {"succes": False, "erreur": "Fichier introuvable"}
        resultat = normaliser_controle("E-5106", "Libelle", rapport)
        assert resultat.succes is False
        assert resultat.nombre_anomalies == 0
        assert resultat.anomalies_par_priorite == {}
        assert resultat.erreur == "Fichier introuvable"

    def test_echec_sans_motif(self) -> None:
        resultat = normaliser_controle("E-5106", "Libelle", {"succes": False})
        assert resultat.erreur == "Echec non precise"


# --------------------------------------------------------------------------- #
# Statut d'une famille
# --------------------------------------------------------------------------- #


class TestStatutFamille:
    """Tests de ResultatFamille.statut."""

    def test_conforme(self) -> None:
        famille = ResultatFamille("cable", "Cable", (_controle(), _controle("E-3104")))
        assert famille.statut == STATUT_CONFORME

    def test_non_conforme_si_anomalie_bloquante(self) -> None:
        famille = ResultatFamille("cable", "Cable", (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}),))
        assert famille.statut == STATUT_NON_CONFORME

    def test_conforme_malgre_anomalies_information(self) -> None:
        """Une anomalie d'information est comptee mais ne declasse pas."""
        famille = ResultatFamille("cable", "Cable", (_controle(nombre=16, priorites={PRIORITE_BASSE: 16}),))
        assert famille.statut == STATUT_CONFORME
        assert famille.nombre_anomalies == 16

    def test_conforme_malgre_anomalies_majeures(self) -> None:
        """Une anomalie majeure est signalee et comptee mais ne declasse pas.

        Convention appliquee par E-5201 et E-6111 : l'ecart doit
        etre corrige, mais il ne bloque pas la livraison du recolement.
        """
        famille = ResultatFamille("altimetrie", "Altimétrie", (_controle(nombre=19, priorites={PRIORITE_MOYENNE: 19}),))
        assert famille.statut == STATUT_CONFORME
        assert famille.nombre_anomalies == 19
        assert famille.nombre_anomalies_declassantes == 0

    def test_conforme_malgre_anomalies_mineures(self) -> None:
        famille = ResultatFamille("cable", "Cable", (_controle(nombre=3, priorites={PRIORITE_MOYENNE: 3}),))
        assert famille.statut == STATUT_CONFORME

    def test_bloquant_declasse_meme_avec_des_majeures(self) -> None:
        """Une seule anomalie bloquante suffit, quel que soit le reste."""
        famille = ResultatFamille(
            "altimetrie",
            "Altimétrie",
            (
                _controle("E-5201", nombre=19, priorites={PRIORITE_MOYENNE: 19}),
                _controle("E-5107", nombre=1, priorites={PRIORITE_FORTE: 1}),
            ),
        )
        assert famille.statut == STATUT_NON_CONFORME
        assert famille.nombre_anomalies_declassantes == 1


class TestPrioritesDeclassantes:
    """Composition de l'ensemble des priorites qui invalident la conformite."""

    def test_bloquante_et_forte_declassent(self) -> None:
        """Echelle du verificateur : les deux premiers niveaux declassent la famille."""
        assert PRIORITES_DECLASSANTES == frozenset({PRIORITE_BLOQUANTE, PRIORITE_FORTE})

    def test_moyenne_et_basse_ne_declassent_pas(self) -> None:
        assert PRIORITE_MOYENNE not in PRIORITES_DECLASSANTES
        assert PRIORITE_BASSE not in PRIORITES_DECLASSANTES

    def test_toutes_declassantes_sont_dans_l_echelle(self) -> None:
        """Une priorite declassante absente de l'echelle ne serait jamais comptee."""
        assert PRIORITES_DECLASSANTES <= set(ORDRE_PRIORITES)

    def test_toute_priorite_de_l_echelle_a_un_libelle(self) -> None:
        assert set(ORDRE_PRIORITES) == set(LIBELLES_PRIORITES)

    def test_incomplet_si_controle_en_echec(self) -> None:
        """Aucun defaut bloquant, mais la conformite n'est pas verifiable."""
        famille = ResultatFamille("projection", "Projection", (_controle(), _controle("E-5106", succes=False)))
        assert famille.statut == STATUT_INCOMPLET

    def test_non_conforme_prime_sur_incomplet(self) -> None:
        """Un defaut avere reste avere, meme si la verification est partielle."""
        famille = ResultatFamille(
            "projection",
            "Projection",
            (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}), _controle("E-5106", succes=False)),
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
                _controle("E1", nombre=2, priorites={PRIORITE_FORTE: 2}),
                _controle("E2", nombre=4, priorites={PRIORITE_FORTE: 1, PRIORITE_BASSE: 3}),
            ),
        )
        assert famille.anomalies_par_priorite == {PRIORITE_FORTE: 3, PRIORITE_BASSE: 3}

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
            ResultatFamille("a", "A", (_controle(nombre=1, priorites={PRIORITE_BASSE: 1}),)),
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}),)),
        )
        assert priorites_presentes(familles) == (PRIORITE_FORTE, PRIORITE_BASSE)

    def test_seules_les_priorites_alimentees(self) -> None:
        """Aucune colonne vide n'est affichee dans le rapport."""
        familles = (ResultatFamille("a", "A", (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}),)),)
        assert priorites_presentes(familles) == (PRIORITE_FORTE,)

    def test_aucune_anomalie(self) -> None:
        assert priorites_presentes((ResultatFamille("a", "A", (_controle(),)),)) == ()

    def test_ordre_priorites_couvre_les_libelles(self) -> None:
        from recostar.controle.synthese_controles import LIBELLES_PRIORITES

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
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}),)),
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
            ResultatFamille("b", "B", (_controle(nombre=1, priorites={PRIORITE_FORTE: 1}),)),
        )
        assert agreger(familles)["statut_global"] == STATUT_NON_CONFORME

    def test_famille_non_executee_exclue_des_totaux(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(nombre=2, priorites={PRIORITE_FORTE: 2}),)),
            ResultatFamille("b", "B", execute=False, motif="Aucune donnee"),
        )
        synthese = agreger(familles)
        assert synthese["nombre_familles_executees"] == 1
        assert synthese["nombre_anomalies_total"] == 2

    def test_ventilation_globale(self) -> None:
        familles = (
            ResultatFamille("a", "A", (_controle(nombre=2, priorites={PRIORITE_FORTE: 2}),)),
            ResultatFamille("b", "B", (_controle("E2", nombre=3, priorites={PRIORITE_BASSE: 3}),)),
        )
        assert agreger(familles)["anomalies_par_priorite"] == {PRIORITE_FORTE: 2, PRIORITE_BASSE: 3}


class TestCodeAffichable:
    """Code porte par la colonne du rapport."""

    def _controle(self, codes: tuple[str, ...]) -> ResultatControle:
        """Resultat de controle portant les codes d'erreur donnes."""
        return ResultatControle(
            code="E0110",
            libelle="Ordre de structure",
            succes=True,
            nombre_anomalies=0,
            anomalies_par_priorite={},
            codes_erreur=codes,
        )

    def test_sans_codes_erreur(self):
        """Un controle dont le code est deja celui du verificateur l'affiche tel quel."""
        assert self._controle(()).code_affichable == "E0110"

    def test_code_unique(self):
        """Un seul code emis remplace l'identifiant du controle."""
        assert self._controle(("E-1104",)).code_affichable == "E-1104"

    def test_deux_codes_listes(self):
        """Deux codes tiennent dans la colonne et sont listes."""
        assert self._controle(("E-1108", "E-1109")).code_affichable == "E-1108, E-1109"

    def test_codes_nombreux_abreges(self):
        """Au-dela de deux codes, seuls les bornes sont affichees."""
        codes = ("E-0003", "E-0008", "E-0010", "E-1107")
        assert self._controle(codes).code_affichable == "E-0003 \u2026E-1107"


class TestCodesErreurRapport:
    """Lecture des codes d'erreur declares par un rapport de controle."""

    def _rapport(self, **extra) -> dict:
        """Rapport de controle reussi, enrichi des cles donnees."""
        return {"succes": True, "nb_erreurs": 0, **extra}

    def test_codes_lus(self):
        """Les codes declares remontent au resultat normalise."""
        controle = normaliser_controle("E0112", "XSD natif", self._rapport(codes_erreur=["E-1104"]))
        assert controle.codes_erreur == ("E-1104",)

    def test_cle_absente(self):
        """Un rapport sans la cle laisse le controle sans codes : son code suffit."""
        controle = normaliser_controle("E-5107", "Altitude Z", self._rapport())
        assert controle.codes_erreur == ()

    def test_cle_mal_typee_ignoree(self):
        """Une valeur qui n'est pas une liste est ignoree plutot que de lever."""
        controle = normaliser_controle("E0112", "XSD natif", self._rapport(codes_erreur="E-1104"))
        assert controle.codes_erreur == ()

    def test_entrees_vides_ecartees(self):
        """Les entrees vides ne produisent pas de code fantome."""
        controle = normaliser_controle("E0112", "XSD natif", self._rapport(codes_erreur=["E-1104", "", None]))
        assert controle.codes_erreur == ("E-1104",)

    def test_controle_en_echec_sans_codes(self):
        """Un controle en echec ne porte aucun code : il n'a rien releve."""
        rapport = {"succes": False, "erreur": "motif", "codes_erreur": ["E-1104"]}
        assert normaliser_controle("E0112", "XSD natif", rapport).codes_erreur == ()
