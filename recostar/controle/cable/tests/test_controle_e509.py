"""
Tests unitaires du controle E509 — discretisation des courbes des cables.

Couvre la geometrie de l'arc (cercle 3 points, relation rayon-fleche-corde), le
nettoyage du trace, le filtrage des sommets sous 3 degres, le regroupement en
portions, la detection des anomalies, la sortie GeoJSON et l'orchestration CLI.

Les geometries de reference sont des arcs de cercle exacts : le rayon attendu
est connu analytiquement, ce qui permet de verifier la mesure contre une valeur
de reference et non contre le resultat du code lui-meme.
"""

import json
import math
import os
from typing import Any

from controle_e504 import FICHIER_AERIEN
from controle_e509 import (
    DESCRIPTIONS_ANOMALIES,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_SORTIE,
    PRIORITE_ANOMALIE,
    SEUIL_ANGLE,
    SEUIL_CORDE_COURTE,
    SEUIL_FLECHE_FORTE,
    SEUIL_FLECHE_NEGLIGEABLE,
    SEUIL_RAYON_ARC_SERRE,
    SEUILS_DEFAUT,
    STATUT_CONTROLE,
    TOLERANCE_COLINEARITE,
    TYPE_COURBE_MAL_DISCRETISEE,
    TYPE_COURBE_NON_DISCRETISEE,
    MesureSommet,
    SeuilsDiscretisation,
    _grouper_sommets_consecutifs,
    _mesurer_sommet,
    analyser_geometrie,
    classer_sommet,
    compter_anomalies_par_type,
    compter_cables_controles,
    construire_geojson_ecarts,
    detecter_anomalies,
    executer_controle_cli,
    fleche_arc,
    mesurer_sommets,
    nettoyer_sommets,
    rayon_cercle_3_points,
)
from utils_tests import ecrire_collection

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _arc_de_cercle(
    nb_segments: int,
    rayon: float = 50.0,
    ouverture: float = 90.0,
) -> list[list[float]]:
    """Arc de cercle exact, discretise en nb_segments cordes egales.

    Le rayon etant connu, la fleche attendue se calcule analytiquement :
    la corde vaut 2 R sin(o / 2n) et la fleche R - racine(R^2 - c^2 / 4).
    """
    pas = math.radians(ouverture) / nb_segments
    return [[rayon * math.cos(i * pas), rayon * math.sin(i * pas)] for i in range(nb_segments + 1)]


def _fleche_attendue(rayon: float, nb_segments: int, ouverture: float = 90.0) -> float:
    """Fleche theorique d'un arc discretise, calculee independamment du code teste."""
    corde = 2.0 * rayon * math.sin(math.radians(ouverture) / (2.0 * nb_segments))
    return rayon - math.sqrt(rayon * rayon - corde * corde / 4.0)


def _encadrer(arc: list[list[float]], angle_raccord: float = 2.0, longueur: float = 40.0) -> list[list[float]]:
    """Encadre un arc de deux segments droits raccordes sous le seuil d'angle.

    Les deux sommets de raccord tournent de `angle_raccord` degres, soit moins
    que SEUIL_ANGLE : ils sont donc ignores et la portion fautive s'arrete
    exactement aux bornes de l'arc.
    """
    direction_amont = math.atan2(arc[1][1] - arc[0][1], arc[1][0] - arc[0][0]) - math.radians(angle_raccord)
    direction_aval = math.atan2(arc[-1][1] - arc[-2][1], arc[-1][0] - arc[-2][0]) + math.radians(angle_raccord)
    amont = [arc[0][0] - longueur * math.cos(direction_amont), arc[0][1] - longueur * math.sin(direction_amont)]
    aval = [arc[-1][0] + longueur * math.cos(direction_aval), arc[-1][1] + longueur * math.sin(direction_aval)]
    return [amont, *arc, aval]


# Rayon des arcs de reference : 50 m, valeur courante d'un rayon de cintrage.
RAYON_REFERENCE: float = 50.0

# Arc de 90 degres rendu par 4 cordes de 19,5 m : fleche de 96 cm, tres au-dela
# des 40 cm toleres. C'est la courbe non conforme de reference.
COURBE_GROSSIERE: list[list[float]] = _arc_de_cercle(4, RAYON_REFERENCE)

# Meme arc rendu par 16 cordes de 4,9 m : fleche de 6 cm des deux cotes, sous le
# seuil de negligeabilite, donc conforme. Chaque sommet tourne de 5,6 degres,
# soit au-dessus du seuil d'angle : il est bien evalue — la conformite vient de
# la fleche, pas d'un sommet ignore.
NB_SEGMENTS_FIN: int = 16
COURBE_FINE: list[list[float]] = _arc_de_cercle(NB_SEGMENTS_FIN, RAYON_REFERENCE)

# Cas reel du jeu Echantillon (cable idb70c029c), en coordonnees relatives au
# millimetre : deux micro-segments terminaux (8 cm et 11 cm), raccords du cable
# dans ses boites, encadrant une portion droite de 7,97 m. Aucune courbe n'est
# decrite ; E509 y voyait pourtant une fleche de 1,73 m, extrapolee depuis
# l'orientation du micro-segment de 8 cm.
TRACE_MICRO_SEGMENTS_TERMINAUX: list[list[float]] = [
    [0.0, 0.0],
    [0.0, -0.46],
    [-0.03, -0.53],
    [-7.54, -3.20],
    [-7.64, -3.24],
]

# Trace droit : aucun sommet a evaluer
TRACE_DROIT: list[list[float]] = [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0]]

# Courbe grossiere encadree de deux segments droits raccordes a 2 degres : sous
# le seuil d'angle, donc ignores. La portion fautive doit couvrir le seul arc.
TRACE_AVEC_COURBE_ENCADREE: list[list[float]] = _encadrer(COURBE_GROSSIERE)


def _arc_par_angles(angles_degres: list[float], rayon: float = RAYON_REFERENCE) -> list[list[float]]:
    """Points d'un cercle aux angles polaires demandes, en degres."""
    return [[rayon * math.cos(math.radians(a)), rayon * math.sin(math.radians(a))] for a in angles_degres]


# Un seul cercle de 50 m echantillonne inegalement : deux troncons grossiers
# (pas de 22,5 degres, fleche 96 cm) separes par un troncon fin (pas de 5 degres,
# fleche 4,8 cm). Deux portions fautives distinctes sont attendues, sans qu'un
# changement de direction artificiel ne vienne les creer.
TRACE_DEUX_TRONCONS_GROSSIERS: list[list[float]] = _arc_par_angles(
    [0.0, 22.5, 45.0, 67.5, 90.0] + [float(a) for a in range(95, 180, 5)] + [180.0, 202.5, 225.0, 247.5, 270.0]
)


def _feature_cable(
    identifiant: str,
    coordonnees: list[list[float]] | None = None,
    statut: str = STATUT_CONTROLE,
    geometrie: dict[str, Any] | None = None,
    proprietes_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Feature GeoJSON d'un cable electrique."""
    proprietes: dict[str, Any] = {"id": identifiant, "Statut": statut}
    if proprietes_extra:
        proprietes.update(proprietes_extra)
    return {
        "type": "Feature",
        "properties": proprietes,
        "geometry": geometrie or {"type": "LineString", "coordinates": coordonnees or COURBE_GROSSIERE},
    }


def _feature_aerien(cables_href: Any) -> dict[str, Any]:
    """Feature GeoJSON minimale d'un cheminement aerien referencant des cables."""
    return {
        "type": "Feature",
        "properties": {"cables_href": cables_href},
        "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0]]},
    }


def _ecrire_cables(repertoire: Any, features: list[dict[str, Any]]) -> None:
    """Ecrit le fichier source des cables electriques dans le repertoire."""
    ecrire_collection(str(repertoire / FICHIER_CABLE_ELECTRIQUE), features)


# --------------------------------------------------------------------------- #
# Cercle passant par trois points
# --------------------------------------------------------------------------- #


class TestRayonCercle3Points:
    """Tests du rayon du cercle circonscrit a trois points."""

    def test_rayon_exact_sur_arc_connu(self) -> None:
        """Trois points d'un cercle de 50 m doivent redonner un rayon de 50 m."""
        a, b, c = COURBE_GROSSIERE[0], COURBE_GROSSIERE[1], COURBE_GROSSIERE[2]
        assert round(rayon_cercle_3_points(a, b, c), 6) == RAYON_REFERENCE

    def test_rayon_independant_de_la_finesse(self) -> None:
        """Le rayon est intrinseque a la courbe : il ne depend pas du decoupage.

        C'est la propriete qui fonde le controle — la distance d'un sommet a la
        corde de ses voisins, elle, diminue quand on rapproche les sommets.
        """
        grossier = rayon_cercle_3_points(COURBE_GROSSIERE[0], COURBE_GROSSIERE[1], COURBE_GROSSIERE[2])
        fin = rayon_cercle_3_points(COURBE_FINE[0], COURBE_FINE[1], COURBE_FINE[2])
        assert round(grossier, 6) == round(fin, 6) == RAYON_REFERENCE

    def test_demi_cercle_unitaire(self) -> None:
        """Trois points du cercle unite : rayon 1."""
        assert round(rayon_cercle_3_points([1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]), 9) == 1.0

    def test_points_alignes_rayon_infini(self) -> None:
        """Une droite est un cercle de rayon infini, pas une erreur."""
        assert math.isinf(rayon_cercle_3_points([0.0, 0.0], [10.0, 0.0], [20.0, 0.0]))

    def test_points_confondus_rayon_infini(self) -> None:
        assert math.isinf(rayon_cercle_3_points([0.0, 0.0], [0.0, 0.0], [10.0, 0.0]))

    def test_voisins_confondus_rayon_infini(self) -> None:
        """Corde nulle : aucun cercle n'est defini."""
        assert math.isinf(rayon_cercle_3_points([0.0, 0.0], [5.0, 5.0], [0.0, 0.0]))

    def test_z_ignore(self) -> None:
        """Le rayon est mesure en planimetrie : le Z ne le modifie pas."""
        plan = rayon_cercle_3_points(COURBE_GROSSIERE[0], COURBE_GROSSIERE[1], COURBE_GROSSIERE[2])
        avec_z = rayon_cercle_3_points(
            [*COURBE_GROSSIERE[0], 10.0],
            [*COURBE_GROSSIERE[1], 40.0],
            [*COURBE_GROSSIERE[2], 90.0],
        )
        assert plan == avec_z


# --------------------------------------------------------------------------- #
# Relation rayon - fleche - corde
# --------------------------------------------------------------------------- #


class TestFlecheArc:
    """Tests de la fleche d'un arc a partir de son rayon et de sa corde."""

    def test_valeur_de_reference(self) -> None:
        """Arc de 50 m de rayon, corde de 10 m : fleche de 25,06 cm."""
        assert round(fleche_arc(50.0, 10.0), 6) == round(50.0 - math.sqrt(2500.0 - 25.0), 6)

    def test_corde_egale_au_diametre_donne_le_rayon(self) -> None:
        """Demi-cercle : la fleche vaut le rayon, c'est le maximum possible."""
        assert fleche_arc(10.0, 20.0) == 10.0

    def test_corde_superieure_au_diametre_bornee_au_rayon(self) -> None:
        """Cas impossible geometriquement : la fleche reste bornee, sans exception."""
        assert fleche_arc(10.0, 25.0) == 10.0

    def test_rayon_infini_fleche_nulle(self) -> None:
        """Une droite ne s'ecarte pas d'elle-meme."""
        assert fleche_arc(math.inf, 10.0) == 0.0

    def test_corde_nulle_fleche_nulle(self) -> None:
        assert fleche_arc(50.0, 0.0) == 0.0

    def test_relation_inverse_metabricoleur(self) -> None:
        """Verifie R = (c^2 + 4 f^2) / (8 f), forme inverse de la relation."""
        corde = 12.0
        fleche = fleche_arc(50.0, corde)
        assert round((corde * corde + 4.0 * fleche * fleche) / (8.0 * fleche), 6) == 50.0

    def test_stabilite_numerique_corde_petite_devant_rayon(self) -> None:
        """La forme directe R - racine(R^2 - c^2/4) perd ses decimales ici.

        Quand la corde est tres petite devant le rayon, les deux termes de la
        soustraction sont presque egaux : l'annulation catastrophique detruit
        les chiffres significatifs. La valeur exacte tend vers c^2 / 8R.
        """
        rayon, corde = 1.0e6, 1.0
        naif = rayon - math.sqrt(rayon * rayon - corde * corde / 4.0)
        # Valeur limite exacte quand c << R : la fleche tend vers c^2 / 8R.
        exact = corde * corde / (8.0 * rayon)
        erreur_stable = abs(fleche_arc(rayon, corde) - exact) / exact
        erreur_naive = abs(naif - exact) / exact
        # La forme retenue conserve une douzaine de chiffres significatifs ;
        # la forme directe en perd la moitie.
        assert erreur_stable < 1e-12
        assert erreur_naive > 1e-5

    def test_croissante_avec_la_corde(self) -> None:
        """Moins de sommets (cordes plus longues) => fleche plus grande."""
        fleches = [fleche_arc(50.0, corde) for corde in (2.0, 5.0, 10.0, 20.0)]
        assert fleches == sorted(fleches)

    def test_decroissante_avec_le_rayon(self) -> None:
        """A corde egale, une courbe plus ouverte s'ecarte moins de sa corde."""
        fleches = [fleche_arc(rayon, 10.0) for rayon in (10.0, 50.0, 200.0)]
        assert fleches == sorted(fleches, reverse=True)


# --------------------------------------------------------------------------- #
# Nettoyage du trace
# --------------------------------------------------------------------------- #


class TestNettoyerSommets:
    """Tests du nettoyage prealable du trace."""

    def test_trace_sain_inchange(self) -> None:
        trace = [[0.0, 0.0], [10.0, 5.0], [20.0, 0.0]]
        assert nettoyer_sommets(trace) == trace

    def test_doublon_consecutif_retire(self) -> None:
        assert nettoyer_sommets([[0.0, 0.0], [0.0, 0.0], [10.0, 5.0]]) == [[0.0, 0.0], [10.0, 5.0]]

    def test_sommet_colineaire_retire(self) -> None:
        assert nettoyer_sommets([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]]) == [[0.0, 0.0], [20.0, 0.0]]

    def test_sommet_hors_tolerance_conserve(self) -> None:
        """Un ecart superieur au millimetre porte une information geometrique reelle."""
        trace = [[0.0, 0.0], [10.0, 10.0 * TOLERANCE_COLINEARITE], [20.0, 0.0]]
        assert len(nettoyer_sommets(trace)) == 3

    def test_z_preserve(self) -> None:
        """Le nettoyage raisonne en XY mais ne tronque pas la troisieme composante."""
        assert nettoyer_sommets([[0.0, 0.0, 5.0], [10.0, 5.0, 7.0]])[1] == [10.0, 5.0, 7.0]

    def test_trace_trop_court_inchange(self) -> None:
        assert nettoyer_sommets([[0.0, 0.0], [10.0, 0.0]]) == [[0.0, 0.0], [10.0, 0.0]]

    def test_arc_de_reference_inchange(self) -> None:
        """Un arc reel ne perd aucun sommet au nettoyage."""
        assert nettoyer_sommets(COURBE_GROSSIERE) == COURBE_GROSSIERE


# --------------------------------------------------------------------------- #
# Mesure d'un sommet
# --------------------------------------------------------------------------- #


class TestMesurerSommet:
    """Tests de _mesurer_sommet sur trois sommets consecutifs."""

    def _sommets_avec_angle(self, angle_degres: float, longueur: float = 100.0) -> list[list[float]]:
        """Trois sommets decrivant un changement de direction de l'angle demande."""
        angle = math.radians(angle_degres)
        return [
            [0.0, 0.0],
            [longueur, 0.0],
            [longueur + longueur * math.cos(angle), longueur * math.sin(angle)],
        ]

    def test_sommets_alignes_ignores(self) -> None:
        assert _mesurer_sommet(1, [0.0, 0.0], [10.0, 0.0], [20.0, 0.0], SEUILS_DEFAUT) is None

    def test_sommets_dupliques_ignores(self) -> None:
        assert _mesurer_sommet(1, [0.0, 0.0], [0.0, 0.0], [10.0, 0.0], SEUILS_DEFAUT) is None

    def test_angle_sous_le_seuil_ignore(self) -> None:
        """Sous 3 degres, le trace est droit a la precision du leve.

        Les segments font ici 100 m : sans le filtre, la fleche depasserait
        largement 40 cm alors qu'il n'y a pas d'arc a controler.
        """
        precedent, sommet, suivant = self._sommets_avec_angle(2.9)
        assert _mesurer_sommet(1, precedent, sommet, suivant, SEUILS_DEFAUT) is None

    def test_angle_egal_au_seuil_mesure(self) -> None:
        """Le seuil est inclusif : 3 degres exactement est mesure."""
        precedent, sommet, suivant = self._sommets_avec_angle(SEUIL_ANGLE)
        mesure = _mesurer_sommet(1, precedent, sommet, suivant, SEUILS_DEFAUT)
        assert mesure is not None
        assert round(mesure.angle, 6) == SEUIL_ANGLE

    def test_angle_au_dessus_du_seuil_mesure(self) -> None:
        precedent, sommet, suivant = self._sommets_avec_angle(45.0)
        mesure = _mesurer_sommet(1, precedent, sommet, suivant, SEUILS_DEFAUT)
        assert mesure is not None
        assert round(mesure.angle, 6) == 45.0

    def test_indice_conserve(self) -> None:
        precedent, sommet, suivant = self._sommets_avec_angle(45.0)
        mesure = _mesurer_sommet(7, precedent, sommet, suivant, SEUILS_DEFAUT)
        assert mesure is not None
        assert mesure.indice == 7

    def test_sens_de_rotation_indifferent(self) -> None:
        """Gauche ou droite, seule l'amplitude de l'ecart compte."""
        gauche = _mesurer_sommet(1, [0.0, 0.0], [10.0, 0.0], [20.0, 5.0], SEUILS_DEFAUT)
        droite = _mesurer_sommet(1, [0.0, 0.0], [10.0, 0.0], [20.0, -5.0], SEUILS_DEFAUT)
        assert gauche is not None and droite is not None
        assert gauche.angle == droite.angle
        assert gauche.fleche_max == droite.fleche_max

    def test_fleche_est_celle_de_la_plus_longue_corde(self) -> None:
        """Les deux cordes adjacentes sont evaluees, la plus defavorable retenue.

        A rayon egal, la fleche croit avec la corde : la corde la plus longue
        impose donc sa valeur.
        """
        precedent, sommet, suivant = COURBE_GROSSIERE[0], COURBE_GROSSIERE[1], COURBE_GROSSIERE[2]
        mesure = _mesurer_sommet(1, precedent, sommet, suivant, SEUILS_DEFAUT)
        assert mesure is not None
        corde_courte = math.dist(COURBE_GROSSIERE[0], COURBE_GROSSIERE[1])
        assert round(mesure.fleche_max, 9) == round(fleche_arc(mesure.rayon, corde_courte), 9)

    def test_valeurs_conformes_a_la_theorie(self) -> None:
        """Rayon et fleche mesures doivent egaler les valeurs analytiques de l'arc."""
        precedent, sommet, suivant = COURBE_GROSSIERE[0], COURBE_GROSSIERE[1], COURBE_GROSSIERE[2]
        mesure = _mesurer_sommet(1, precedent, sommet, suivant, SEUILS_DEFAUT)
        assert mesure is not None
        assert round(mesure.rayon, 6) == RAYON_REFERENCE
        assert round(mesure.fleche_max, 6) == round(_fleche_attendue(RAYON_REFERENCE, 4), 6)


class TestMesurerSommets:
    """Tests du parcours des sommets intermediaires d'une partie."""

    def test_deux_sommets_aucune_mesure(self) -> None:
        assert mesurer_sommets([[0.0, 0.0], [10.0, 0.0]]) == []

    def test_trace_droit_aucune_mesure(self) -> None:
        assert mesurer_sommets(TRACE_DROIT) == []

    def test_une_mesure_par_sommet_intermediaire(self) -> None:
        mesures = mesurer_sommets(COURBE_GROSSIERE)
        assert len(mesures) == len(COURBE_GROSSIERE) - 2

    def test_indices_conserves(self) -> None:
        mesures = mesurer_sommets(COURBE_GROSSIERE)
        assert [m.indice for m in mesures] == list(range(1, len(COURBE_GROSSIERE) - 1))

    def test_arc_regulier_mesures_homogenes(self) -> None:
        """Sur un arc regulier, tous les sommets partagent rayon, angle et fleche."""
        mesures = mesurer_sommets(COURBE_GROSSIERE)
        assert {round(m.rayon, 6) for m in mesures} == {RAYON_REFERENCE}
        assert len({round(m.fleche_max, 9) for m in mesures}) == 1

    def test_seuil_d_angle_personnalise(self) -> None:
        """Un seuil eleve ecarte tous les sommets de l'arc."""
        assert mesurer_sommets(COURBE_GROSSIERE, SeuilsDiscretisation(angle=90.0)) == []


class TestSeuilsDefaut:
    """Les seuils par defaut refletent la regle metier : c'est le contrat du controle."""

    def test_valeurs_metier(self) -> None:
        assert (SEUIL_FLECHE_FORTE, SEUIL_FLECHE_NEGLIGEABLE) == (0.40, 0.10)
        assert (SEUIL_CORDE_COURTE, SEUIL_RAYON_ARC_SERRE, SEUIL_ANGLE) == (1.00, 15.0, 3.0)

    def test_seuils_defaut_alignes_sur_les_constantes(self) -> None:
        assert SEUILS_DEFAUT == SeuilsDiscretisation(
            angle=SEUIL_ANGLE,
            fleche_forte=SEUIL_FLECHE_FORTE,
            fleche_negligeable=SEUIL_FLECHE_NEGLIGEABLE,
            corde_courte=SEUIL_CORDE_COURTE,
            rayon_arc_serre=SEUIL_RAYON_ARC_SERRE,
        )


class TestClasserSommet:
    """Tests du classement d'un sommet par ses deux fleches, leurs cordes et son rayon.

    Les valeurs sont donnees directement : ce test verrouille la regle metier,
    independamment de la geometrie qui produit ces mesures. L'ordre des
    arguments est (fleche_max, fleche_min, corde_fleche_max, corde_fleche_min,
    rayon) ; `corde_fleche_max` est toujours la plus longue des deux cordes, la
    fleche croissant avec la corde a rayon fixe.
    """

    def test_les_deux_fleches_negligeables_conforme(self) -> None:
        assert classer_sommet(0.09, 0.02, 4.0, 3.0) is None

    def test_declencheur_a_les_deux_fleches_significatives(self) -> None:
        """Arc uniformement sous-decrit : les deux cordes ratent l'arc."""
        assert classer_sommet(0.16, 0.11, 1.2, 1.4) == TYPE_COURBE_MAL_DISCRETISEE

    def test_declencheur_a_au_seuil_exact(self) -> None:
        seuil = SEUIL_FLECHE_NEGLIGEABLE
        assert classer_sommet(seuil, seuil, 2.0, 3.0) == TYPE_COURBE_MAL_DISCRETISEE

    def test_declencheur_b_corde_isolee_sur_virage_serre(self) -> None:
        """Une seule fleche mais forte, sur un rayon serre : sommet manquant."""
        assert classer_sommet(0.85, 0.004, 1.5, 12.23) == TYPE_COURBE_MAL_DISCRETISEE

    def test_declencheur_b_ecarte_sur_courbe_ample(self) -> None:
        """Meme ecart isole, mais sur une courbe tres ample : conforme.

        Cas reel du jeu Echantillon2 : une corde de 11,9 m sur un rayon de 34 m
        s'ecarte de 53 cm, sans que le cable soit mal place.
        """
        assert classer_sommet(0.531, 0.0004, 2.0, 33.65) is None

    def test_corde_courte_toleree(self) -> None:
        """Un ecart isole porte par des cordes de moins d'un metre est tolere."""
        assert classer_sommet(0.50, 0.01, 0.8, 2.0) is None

    def test_corde_courte_non_toleree_si_les_deux_fleches_comptent(self) -> None:
        """La tolerance de corde courte ne couvre que le cas d'un ecart isole."""
        assert classer_sommet(0.50, 0.15, 0.8, 2.0) == TYPE_COURBE_MAL_DISCRETISEE

    def test_les_deux_fleches_bloquantes(self) -> None:
        """Cas extreme : les deux cordes ratent l'arc de plus de 40 cm."""
        assert classer_sommet(0.90, 0.45, 4.0, 6.0) == TYPE_COURBE_NON_DISCRETISEE

    def test_bloquant_ignore_le_garde_fou_de_rayon(self) -> None:
        """Une courbe ample n'attenue pas le cas extreme."""
        assert classer_sommet(0.90, 0.45, 18.0, 500.0) == TYPE_COURBE_NON_DISCRETISEE

    def test_seuils_personnalises(self) -> None:
        seuils = SeuilsDiscretisation(fleche_negligeable=0.30)
        assert classer_sommet(0.20, 0.15, 2.5, 4.0, seuils) is None


class TestClasserSommetEchantillonnageDissymetrique:
    """Le declencheur B exige deux cordes mesurables.

    Un sommet encadre par une micro-corde et une corde longue ne temoigne pas
    d'un manque de sommets : le rayon y est dicte par l'orientation du
    micro-segment, et la fleche attribuee a la longue corde est extrapolee
    depuis un troncon ou aucun sommet n'atteste de courbure. Les valeurs sont
    celles des cas reels du jeu Echantillon.
    """

    def test_micro_corde_entrante_ecartee(self) -> None:
        """Cable idb70c029c : cordes 0,08 m et 7,97 m, R = 5,46 m, fleche 1,73 m."""
        assert classer_sommet(1.726, 0.0, 0.076, 5.46) is None

    def test_micro_corde_sortante_ecartee(self) -> None:
        """Cable idc2545906 : segment terminal de 1 cm contre une corde de 1,76 m."""
        assert classer_sommet(0.621, 0.0, 0.010, 0.93) is None

    def test_corde_courte_juste_sous_le_seuil_ecartee(self) -> None:
        """Cable id50064671 : 0,53 m contre 8,28 m — le cas le moins dissymetrique."""
        assert classer_sommet(0.590, 0.002, 0.526, 14.84) is None

    def test_corde_au_seuil_exact_reste_signalee(self) -> None:
        """Le seuil est inclusif : une corde d'exactement 1 m reste mesurable."""
        assert classer_sommet(0.85, 0.004, SEUIL_CORDE_COURTE, 12.23) == TYPE_COURBE_MAL_DISCRETISEE

    def test_declencheur_a_insensible_a_la_dissymetrie(self) -> None:
        """La reserve ne s'applique qu'au declencheur B.

        Le declencheur A exige deux fleches significatives, qu'une micro-corde ne
        peut pas produire : la contrainte serait sans objet. La verifier protege
        contre une extension involontaire du garde-fou.
        """
        assert classer_sommet(0.50, 0.15, 0.05, 2.0) == TYPE_COURBE_MAL_DISCRETISEE

    def test_cas_extreme_insensible_a_la_dissymetrie(self) -> None:
        """Deux fleches au-dela de 40 cm restent non conformes, quelles que soient
        les cordes : l'arc n'est decrit d'aucun cote."""
        assert classer_sommet(0.90, 0.45, 0.05, 6.0) == TYPE_COURBE_NON_DISCRETISEE


class TestEchantillonnageDissymetriqueSurGeometrie:
    """Non-regression geometrique : les micro-segments terminaux ne sont plus signales.

    Le classement est deja verrouille par TestClasserSommetEchantillonnageDissymetrique ;
    ces tests verifient la chaine complete, du trace au verdict, sur la
    geometrie reelle qui produisait le faux positif.
    """

    def test_micro_segments_terminaux_conformes(self) -> None:
        """Cable idb70c029c du jeu Echantillon : droit sur 8 m, aucune anomalie."""
        geometrie = {"type": "LineString", "coordinates": TRACE_MICRO_SEGMENTS_TERMINAUX}
        assert analyser_geometrie(geometrie).portions == []

    def test_les_sommets_restent_evalues(self) -> None:
        """Le garde-fou classe le sommet, il ne l'exclut pas de la mesure.

        La couverture annoncee au rapport (`nombre_sommets_evalues`) ne doit pas
        baisser : un sommet mesure puis juge conforme reste un sommet controle.
        """
        geometrie = {"type": "LineString", "coordinates": TRACE_MICRO_SEGMENTS_TERMINAUX}
        assert analyser_geometrie(geometrie).nombre_sommets_evalues > 0

    def test_courbe_grossiere_toujours_signalee(self) -> None:
        """Le garde-fou n'ouvre pas d'angle mort sur une vraie courbe sous-decrite.

        COURBE_GROSSIERE est echantillonnee regulierement (cordes de 19,5 m) :
        aucune de ses cordes n'est courte, la reserve ne s'y applique pas.
        """
        geometrie = {"type": "LineString", "coordinates": COURBE_GROSSIERE}
        assert analyser_geometrie(geometrie).portions != []

    def test_micro_segment_greffe_sur_une_courbe_grossiere(self) -> None:
        """Un micro-segment n'exonere que son propre voisinage.

        Un sommet parasite est insere a 5 cm du premier sommet de la courbe
        grossiere : les sommets qu'il encadre echappent au declencheur B, mais
        le reste de l'arc — regulierement echantillonne — reste signale.
        """
        parasite = [
            COURBE_GROSSIERE[0],
            [COURBE_GROSSIERE[0][0], COURBE_GROSSIERE[0][1] + 0.05],
            *COURBE_GROSSIERE[1:],
        ]
        geometrie = {"type": "LineString", "coordinates": parasite}
        assert analyser_geometrie(geometrie).portions != []


class TestCompterAnomaliesParType:
    """Ventilation des anomalies par type pour le rapport JSON."""

    def test_aucune_anomalie(self) -> None:
        assert compter_anomalies_par_type([]) == {}

    def test_ventilation(self) -> None:
        anomalies = [
            {"type_anomalie": TYPE_COURBE_MAL_DISCRETISEE},
            {"type_anomalie": TYPE_COURBE_MAL_DISCRETISEE},
            {"type_anomalie": TYPE_COURBE_NON_DISCRETISEE},
        ]
        assert compter_anomalies_par_type(anomalies) == {
            TYPE_COURBE_MAL_DISCRETISEE: 2,
            TYPE_COURBE_NON_DISCRETISEE: 1,
        }

    def test_types_decrits_dans_le_profil(self) -> None:
        """Tout type produit doit avoir une description, sinon le fichier d'ecarts
        sortirait sans libelle exploitable."""
        assert set(DESCRIPTIONS_ANOMALIES) == {TYPE_COURBE_NON_DISCRETISEE, TYPE_COURBE_MAL_DISCRETISEE}


# --------------------------------------------------------------------------- #
# Regroupement en portions
# --------------------------------------------------------------------------- #


class TestGrouperSommetsConsecutifs:
    """Tests du regroupement des sommets non conformes en portions."""

    def _mesure(self, indice: int) -> MesureSommet:
        return MesureSommet(indice, 20.0, 5.0, 0.9, 0.0, 4.0, 3.5, TYPE_COURBE_MAL_DISCRETISEE)

    def test_aucune_mesure_aucun_groupe(self) -> None:
        assert list(_grouper_sommets_consecutifs([])) == []

    def test_sommet_isole_forme_un_groupe(self) -> None:
        """Un seul sommet trop ecarte suffit : c'est deja une portion a redensifier."""
        groupes = list(_grouper_sommets_consecutifs([self._mesure(3)]))
        assert [[m.indice for m in g] for g in groupes] == [[3]]

    def test_indices_consecutifs_regroupes(self) -> None:
        groupes = list(_grouper_sommets_consecutifs([self._mesure(1), self._mesure(2), self._mesure(3)]))
        assert [[m.indice for m in g] for g in groupes] == [[1, 2, 3]]

    def test_rupture_d_indice_scinde(self) -> None:
        """Un sommet conforme intercale ferme la portion et en ouvre une autre."""
        groupes = list(_grouper_sommets_consecutifs([self._mesure(1), self._mesure(2), self._mesure(5)]))
        assert [[m.indice for m in g] for g in groupes] == [[1, 2], [5]]

    def test_dernier_groupe_ferme(self) -> None:
        """Le dernier groupe est clos en fin de parcours, pas seulement a une rupture."""
        groupes = list(_grouper_sommets_consecutifs([self._mesure(4), self._mesure(7), self._mesure(8)]))
        assert [[m.indice for m in g] for g in groupes] == [[4], [7, 8]]


# --------------------------------------------------------------------------- #
# Analyse d'une geometrie
# --------------------------------------------------------------------------- #


class TestAnalyserGeometrie:
    """Tests de l'analyse complete d'une geometrie de cable."""

    def test_geometrie_absente(self) -> None:
        resultat = analyser_geometrie(None)
        assert resultat.portions == []
        assert resultat.nombre_sommets_evalues == 0

    def test_trace_droit_conforme(self) -> None:
        resultat = analyser_geometrie({"type": "LineString", "coordinates": TRACE_DROIT})
        assert resultat.portions == []
        assert resultat.nombre_sommets_evalues == 0

    def test_courbe_grossiere_non_conforme(self) -> None:
        """Arc de 50 m rendu par 4 cordes : fleche de 96 cm, bien au-dela de 40 cm."""
        resultat = analyser_geometrie({"type": "LineString", "coordinates": COURBE_GROSSIERE})
        assert len(resultat.portions) == 1
        portion = resultat.portions[0]
        assert portion.fleche_max >= SEUIL_FLECHE_FORTE
        assert round(portion.fleche_max, 6) == round(_fleche_attendue(RAYON_REFERENCE, 4), 6)
        assert round(portion.rayon_min, 6) == RAYON_REFERENCE
        assert portion.nombre_sommets_non_conformes == len(COURBE_GROSSIERE) - 2

    def test_courbe_fine_conforme(self) -> None:
        """Meme arc rendu par 8 cordes : fleche de 24 cm, sous le seuil."""
        resultat = analyser_geometrie({"type": "LineString", "coordinates": COURBE_FINE})
        assert resultat.portions == []
        # Tous les sommets ont ete evalues : la conformite vient de la fleche,
        # pas d'un sommet ecarte par le seuil d'angle.
        assert resultat.nombre_sommets_evalues == len(COURBE_FINE) - 2
        assert _fleche_attendue(RAYON_REFERENCE, NB_SEGMENTS_FIN) < SEUIL_FLECHE_NEGLIGEABLE

    def test_seuil_de_negligeabilite_inclusif(self) -> None:
        """Le seuil de negligeabilite est inclusif : une fleche pile au seuil compte.

        L'arc de reference est regulier, ses deux fleches sont donc egales : il
        depend du seul declencheur A (les deux fleches significatives).
        """
        # Un seul sommet intermediaire : la comparaison porte sur une mesure unique.
        trace = COURBE_GROSSIERE[0:3]
        geometrie = {"type": "LineString", "coordinates": trace}
        (mesure,) = mesurer_sommets(trace)
        # fleche_forte a l'infini : seul le declencheur A peut jouer.
        au_seuil = SeuilsDiscretisation(fleche_negligeable=mesure.fleche_min, fleche_forte=math.inf)
        au_dessus = SeuilsDiscretisation(
            fleche_negligeable=math.nextafter(mesure.fleche_min, math.inf),
            fleche_forte=math.inf,
        )
        assert analyser_geometrie(geometrie, au_seuil).portions != []
        assert analyser_geometrie(geometrie, au_dessus).portions == []

    def test_sommets_sous_le_seuil_d_angle_non_evalues(self) -> None:
        """Un trace tres legerement sinueux sur de longs segments est ignore.

        Sans le filtre a 3 degres, la seule longueur des segments suffirait a
        faire depasser 40 cm de fleche.
        """
        angle = math.radians(2.0)
        trace = [
            [0.0, 0.0],
            [200.0, 0.0],
            [200.0 + 200.0 * math.cos(angle), 200.0 * math.sin(angle)],
        ]
        resultat = analyser_geometrie({"type": "LineString", "coordinates": trace})
        assert resultat.nombre_sommets_evalues == 0
        assert resultat.portions == []

    def test_portion_bornee_par_les_sommets_encadrants(self) -> None:
        """La portion s'etend d'un sommet avant les sommets fautifs a un sommet apres."""
        geometrie = {"type": "LineString", "coordinates": TRACE_AVEC_COURBE_ENCADREE}
        portion = analyser_geometrie(geometrie).portions[0]
        assert portion.sommets == COURBE_GROSSIERE
        assert len(portion.sommets) < len(TRACE_AVEC_COURBE_ENCADREE)

    def test_portion_couvre_toute_la_courbe_isolee(self) -> None:
        """Une courbe occupant tout le trace donne une portion egale au trace."""
        portion = analyser_geometrie({"type": "LineString", "coordinates": COURBE_GROSSIERE}).portions[0]
        assert portion.sommets == COURBE_GROSSIERE

    def test_deux_courbes_fautives_deux_portions(self) -> None:
        """Un cable portant deux arcs mal discretises produit deux portions distinctes."""
        geometrie = {"type": "LineString", "coordinates": TRACE_DEUX_TRONCONS_GROSSIERS}
        portions = analyser_geometrie(geometrie).portions
        assert len(portions) == 2
        assert portions[0].sommets != portions[1].sommets
        # Le troncon fin intercale n'appartient a aucune des deux portions.
        assert len(portions[0].sommets) + len(portions[1].sommets) < len(TRACE_DEUX_TRONCONS_GROSSIERS)

    def test_z_conserve_dans_la_portion(self) -> None:
        """Le Z n'entre pas dans le calcul mais reste present dans la geometrie extraite."""
        avec_z = [[x, y, 100.0 + i] for i, (x, y) in enumerate(COURBE_GROSSIERE)]
        resultat_plan = analyser_geometrie({"type": "LineString", "coordinates": COURBE_GROSSIERE})
        resultat_z = analyser_geometrie({"type": "LineString", "coordinates": avec_z})
        assert resultat_plan.portions[0].fleche_max == resultat_z.portions[0].fleche_max
        assert len(resultat_z.portions[0].sommets[0]) == 3

    def test_multilinestring_parties_independantes(self) -> None:
        """Aucun arc fictif n'est reconstruit entre deux parties disjointes."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [TRACE_DROIT, COURBE_GROSSIERE],
        }
        resultat = analyser_geometrie(geometrie)
        assert len(resultat.portions) == 1
        assert resultat.portions[0].sommets == COURBE_GROSSIERE

    def test_seuils_personnalises(self) -> None:
        """Un seuil de fleche relache rend conforme une courbe grossiere."""
        geometrie = {"type": "LineString", "coordinates": COURBE_GROSSIERE}
        assert (
            analyser_geometrie(geometrie, SeuilsDiscretisation(fleche_forte=10.0, fleche_negligeable=10.0)).portions
            == []
        )

    def test_seuil_d_angle_relache_ecarte_toute_la_courbe(self) -> None:
        geometrie = {"type": "LineString", "coordinates": COURBE_GROSSIERE}
        resultat = analyser_geometrie(geometrie, SeuilsDiscretisation(angle=90.0))
        assert resultat.nombre_sommets_evalues == 0
        assert resultat.portions == []

    def test_arc_serre_uniformement_grossier_signale(self) -> None:
        """Declencheur A : un arc serre rendu par trop peu de cordes est signale.

        Demi-cercle de 2 m de rayon en 4 cordes : les deux fleches valent 15 cm,
        donc toutes deux au-dessus du seuil de negligeabilite. L'arc n'est pas
        assez decrit, meme si aucune corde n'atteint 40 cm a elle seule.
        """
        petit_arc = _arc_de_cercle(4, rayon=2.0, ouverture=180.0)
        resultat = analyser_geometrie({"type": "LineString", "coordinates": petit_arc})
        assert resultat.nombre_sommets_evalues == 3
        assert len(resultat.portions) == 1
        assert resultat.portions[0].type_anomalie == TYPE_COURBE_MAL_DISCRETISEE

    def test_arc_serre_bien_discretise_conforme(self) -> None:
        """Le meme demi-cercle finement decrit ne l'est plus."""
        petit_arc = _arc_de_cercle(20, rayon=2.0, ouverture=180.0)
        assert analyser_geometrie({"type": "LineString", "coordinates": petit_arc}).portions == []

    def test_coude_franc_signale(self) -> None:
        """Un angle droit est signale : aucun cable ne tourne a rayon nul.

        Consequence assumee de la regle : au-dela de 3 degres, tout sommet est
        traite comme un arc. Un coude a 90 degres entre segments de 10 m donne
        un rayon de 11,18 m et une fleche de 6,18 m.
        """
        coude = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]]
        resultat = analyser_geometrie({"type": "LineString", "coordinates": coude})
        assert len(resultat.portions) == 1
        assert resultat.portions[0].angle_max == 90.0


# --------------------------------------------------------------------------- #
# Detection des anomalies
# --------------------------------------------------------------------------- #


class TestDetecterAnomalies:
    """Tests du filtrage et de la generation des anomalies."""

    def test_statut_hors_perimetre_ignore(self) -> None:
        features = [_feature_cable("c1", statut="InService")]
        anomalies, nb_sommets = detecter_anomalies(features)
        assert anomalies == []
        assert nb_sommets == 0

    def test_une_anomalie_par_portion(self) -> None:
        features = [_feature_cable("c1"), _feature_cable("c2")]
        anomalies, _ = detecter_anomalies(features)
        assert [a["id_cable"] for a in anomalies] == ["c1", "c2"]

    def test_plusieurs_portions_pour_un_meme_cable(self) -> None:
        """Deux arcs fautifs sur un cable donnent deux anomalies portant son identifiant."""
        features = [_feature_cable("c1", coordonnees=TRACE_DEUX_TRONCONS_GROSSIERS)]
        anomalies, _ = detecter_anomalies(features)
        assert [a["id_cable"] for a in anomalies] == ["c1", "c1"]

    def test_details_anomalie(self) -> None:
        anomalies, _ = detecter_anomalies([_feature_cable("c1")])
        assert anomalies[0]["fleche_max"] >= SEUIL_FLECHE_FORTE
        assert anomalies[0]["rayon_min"] == round(RAYON_REFERENCE, 2)
        assert anomalies[0]["angle_max"] == 22.5
        assert anomalies[0]["nombre_sommets_non_conformes"] > 0

    def test_geometrie_limitee_a_la_portion(self) -> None:
        """L'anomalie ne porte que la portion fautive, pas le trace complet du cable."""
        anomalies, _ = detecter_anomalies([_feature_cable("c1", coordonnees=TRACE_AVEC_COURBE_ENCADREE)])
        geometrie = anomalies[0]["geometrie"]
        assert geometrie["type"] == "LineString"
        assert geometrie["coordinates"] == COURBE_GROSSIERE

    def test_cable_conforme_absent_des_anomalies(self) -> None:
        anomalies, nb_sommets = detecter_anomalies([_feature_cable("c1", coordonnees=COURBE_FINE)])
        assert anomalies == []
        assert nb_sommets == len(COURBE_FINE) - 2

    def test_cable_aerien_exclu(self) -> None:
        # Meme geometrie grossiere que le cas non conforme, mais portee aerienne
        anomalies, nb_sommets = detecter_anomalies([_feature_cable("c1")], {"c1"})
        assert anomalies == []
        assert nb_sommets == 0

    def test_cable_non_aerien_toujours_controle(self) -> None:
        anomalies, _ = detecter_anomalies([_feature_cable("c1")], {"autre"})
        assert len(anomalies) == 1

    def test_seuils_propages(self) -> None:
        """Les seuils passes a detecter_anomalies atteignent bien l'analyse."""
        anomalies, _ = detecter_anomalies(
            [_feature_cable("c1")], seuils=SeuilsDiscretisation(fleche_forte=10.0, fleche_negligeable=10.0)
        )
        assert anomalies == []

    def test_compter_cables_controles(self) -> None:
        features = [_feature_cable("c1"), _feature_cable("c2", statut="InService")]
        assert compter_cables_controles(features) == 1

    def test_compter_cables_controles_exclut_aeriens(self) -> None:
        features = [_feature_cable("c1"), _feature_cable("c2")]
        assert compter_cables_controles(features, {"c1"}) == 1


# --------------------------------------------------------------------------- #
# Sortie GeoJSON
# --------------------------------------------------------------------------- #


class TestConstruireGeojsonEcarts:
    """Tests de la construction du fichier d'ecarts."""

    def _anomalie(self) -> dict[str, Any]:
        return {
            "id_cable": "c1",
            "type_anomalie": TYPE_COURBE_MAL_DISCRETISEE,
            "fleche_max": 0.961,
            "rayon_min": 50.0,
            "angle_max": 22.5,
            "nombre_sommets_non_conformes": 3,
            "geometrie": {"type": "LineString", "coordinates": COURBE_GROSSIERE},
        }

    def test_sans_anomalie_collection_vide(self) -> None:
        resultat = construire_geojson_ecarts([])
        assert resultat["type"] == "FeatureCollection"
        assert resultat["features"] == []

    def test_proprietes_anomalie(self) -> None:
        proprietes = construire_geojson_ecarts([self._anomalie()])["features"][0]["properties"]
        assert proprietes["type_anomalie"] == TYPE_COURBE_MAL_DISCRETISEE
        assert proprietes["id_cable"] == "c1"
        assert proprietes["fleche_max_m"] == 0.961
        assert proprietes["rayon_min_m"] == 50.0
        assert proprietes["angle_max_deg"] == 22.5
        assert proprietes["seuil_fleche_forte_m"] == SEUIL_FLECHE_FORTE
        assert proprietes["seuil_angle_deg"] == SEUIL_ANGLE
        assert proprietes["nombre_sommets_non_conformes"] == 3
        assert proprietes["nombre_sommets_portion"] == len(COURBE_GROSSIERE)
        assert proprietes["priorite"] == PRIORITE_ANOMALIE

    def test_priorite_est_bloquante(self) -> None:
        """Contrat explicite : une courbe mal discretisee invalide le recolement."""
        assert PRIORITE_ANOMALIE == "bloquant"

    def test_priorite_identique_quel_que_soit_le_type(self) -> None:
        """Les deux types decrivent des defauts distincts, pas des gravites distinctes."""
        for type_anomalie in (TYPE_COURBE_NON_DISCRETISEE, TYPE_COURBE_MAL_DISCRETISEE):
            anomalie = {**self._anomalie(), "type_anomalie": type_anomalie}
            proprietes = construire_geojson_ecarts([anomalie])["features"][0]["properties"]
            assert proprietes["priorite"] == PRIORITE_ANOMALIE

    def test_geometrie_de_la_portion_conservee(self) -> None:
        resultat = construire_geojson_ecarts([self._anomalie()])
        assert resultat["features"][0]["geometry"]["coordinates"] == COURBE_GROSSIERE

    def test_crs_propage(self) -> None:
        crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}}
        assert construire_geojson_ecarts([], crs)["crs"] == crs

    def test_crs_absent_non_ajoute(self) -> None:
        assert "crs" not in construire_geojson_ecarts([])


# --------------------------------------------------------------------------- #
# Execution CLI
# --------------------------------------------------------------------------- #


class TestExecuterControleCli:
    """Tests de l'orchestration CLI du controle."""

    def test_repertoire_introuvable_retourne_erreur(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path / "absent"))
        assert resultat["succes"] is False
        assert "introuvable" in resultat["erreur"]

    def test_fichier_cable_absent_non_bloquant(self, tmp_path: Any) -> None:
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["fichier_cable_absent"] is True
        assert resultat["nombre_anomalies"] == 0

    def test_nominal_avec_anomalie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_anomalies"] == 1
        assert resultat["nombre_cables_controles"] == 1
        assert resultat["nombre_cables_non_conformes"] == 1
        assert resultat["priorite"] == PRIORITE_ANOMALIE

    def test_nominal_sans_anomalie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1", coordonnees=COURBE_FINE)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_sommets_evalues"] == len(COURBE_FINE) - 2

    def test_deux_portions_un_seul_cable_non_conforme(self, tmp_path: Any) -> None:
        """Les anomalies se comptent par portion, les cables par identifiant distinct."""
        _ecrire_cables(tmp_path, [_feature_cable("c1", coordonnees=TRACE_DEUX_TRONCONS_GROSSIERS)])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 2
        assert resultat["nombre_cables_non_conformes"] == 1

    def test_fichier_ecarts_cree(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert os.path.isfile(resultat["sortie"])
        assert os.path.basename(resultat["sortie"]) == FICHIER_SORTIE

    def test_geometries_ecrites_limitees_aux_portions(self, tmp_path: Any) -> None:
        """Le fichier d'ecarts ne contient que les portions fautives, pas les traces entiers."""
        _ecrire_cables(tmp_path, [_feature_cable("c1", coordonnees=TRACE_AVEC_COURBE_ENCADREE)])
        resultat = executer_controle_cli(str(tmp_path))
        with open(resultat["sortie"], encoding="utf-8") as flux:
            ecarts = json.load(flux)
        assert len(ecarts["features"]) == 1
        assert ecarts["features"][0]["geometry"]["coordinates"] == COURBE_GROSSIERE

    def test_sortie_dans_repertoire_dedie(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        destination = tmp_path / "sortie"
        executer_controle_cli(str(tmp_path), str(destination))
        assert os.path.isfile(str(destination / FICHIER_SORTIE))

    def test_exclusion_aerienne_integree(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        ecrire_collection(str(tmp_path / FICHIER_AERIEN), [_feature_aerien("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["nombre_anomalies"] == 0
        assert resultat["nombre_cables_controles"] == 0
        assert resultat["nombre_cables_aeriens_exclus"] == 1

    def test_fichier_aerien_absent_non_bloquant(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        assert resultat["succes"] is True
        assert resultat["nombre_cables_aeriens_exclus"] == 0
        assert resultat["nombre_anomalies"] == 1

    def test_rapport_contient_champs_obligatoires(self, tmp_path: Any) -> None:
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        resultat = executer_controle_cli(str(tmp_path))
        for champ in (
            "succes",
            "priorite",
            "anomalies_par_type",
            "nombre_anomalies",
            "nombre_cables_controles",
            "nombre_cables_aeriens_exclus",
            "nombre_cables_non_conformes",
            "nombre_sommets_evalues",
            "seuil_fleche_forte_m",
            "seuil_fleche_negligeable_m",
            "seuil_rayon_arc_serre_m",
            "seuil_angle_deg",
            "fichier_cable_absent",
            "sortie",
        ):
            assert champ in resultat, f"Champ manquant : {champ}"

    def test_comportement_identique_v10_v11(self, tmp_path: Any) -> None:
        # La V1.1 ajoute des champs sans impact sur le perimetre du controle
        repertoire_v11 = tmp_path / "v11"
        repertoire_v11.mkdir()
        _ecrire_cables(tmp_path, [_feature_cable("c1")])
        _ecrire_cables(repertoire_v11, [_feature_cable("c1", proprietes_extra={"Commentaire": "V1.1"})])
        resultat_v10 = executer_controle_cli(str(tmp_path))
        resultat_v11 = executer_controle_cli(str(repertoire_v11))
        assert resultat_v10["nombre_anomalies"] == resultat_v11["nombre_anomalies"] == 1
