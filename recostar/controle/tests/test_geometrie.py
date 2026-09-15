"""
Tests des utilitaires geometriques communs (utils_geometrie_commun.py).

Couvre la correction des altitudes manquantes, mutualisee entre le calcul des
longueurs de cables (traitement/calcul_longueurs) et les controles E-5100, E-4200
et E-4201.
La convention verifiee ici est celle du format RecoStaR : une altitude absente
est ecrite 0.0 dans la posList, elle ne designe pas le niveau de la mer.
"""

from pathlib import Path

import pytest

from recostar.controle.fonctions_communes.geometrie import (
    TOLERANCE_SUPERPOSITION,
    TOLERANCE_Z,
    corriger_z_nuls,
    est_z_nul,
    extraire_parties_lineaires,
    recoller_parties_lineaires,
)

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent


class TestUniciteDuModuleCommun:
    """Le module commun doit rester l'unique implementation, sans module-relais.

    Les familles ont longtemps porte un `utils_geometrie.py` qui se contentait de
    reexporter ce module : un detour impose par les imports a plat, ou tous les
    relais partageaient le meme nom et se masquaient dans sys.modules. Depuis le
    passage en paquets, chaque famille importe directement
    `recostar.controle.fonctions_communes.geometrie`.

    Ce garde interdit la reapparition d'un tel relais : il reintroduirait une
    seconde adresse pour la meme logique, donc un risque de divergence.
    """

    def test_aucun_module_relais_dans_les_familles(self) -> None:
        relais = sorted(_RACINE_CONTROLE.glob("*/utils_geometrie.py"))
        assert relais == [], f"module-relais a supprimer : {[str(c) for c in relais]}"

    def test_module_commun_importable_a_son_adresse_canonique(self) -> None:
        """L'adresse unique du module doit rester resolvable par les familles."""
        from importlib import import_module

        assert import_module("recostar.controle.fonctions_communes.geometrie") is not None


class TestExtrairePartiesLineaires:
    """Decomposition brute d'une geometrie lineaire, sans recollement."""

    def test_linestring(self) -> None:
        coords = [[0.0, 0.0], [1.0, 1.0]]
        assert extraire_parties_lineaires({"type": "LineString", "coordinates": coords}) == [coords]

    def test_multilinestring_parties_conservees(self) -> None:
        parties = [[[0.0, 0.0], [1.0, 0.0]], [[5.0, 0.0], [6.0, 0.0]]]
        assert extraire_parties_lineaires({"type": "MultiLineString", "coordinates": parties}) == parties

    def test_geometrie_absente_ou_non_lineaire(self) -> None:
        assert extraire_parties_lineaires(None) == []
        assert extraire_parties_lineaires({"type": "Point", "coordinates": [0.0, 0.0]}) == []
        assert extraire_parties_lineaires({"type": "LineString", "coordinates": []}) == []


class TestRecollerPartiesLineaires:
    """Recollement des troncons en polylignes continues maximales."""

    def test_linestring_inchange(self) -> None:
        coords = [[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]
        assert recoller_parties_lineaires({"type": "LineString", "coordinates": coords}) == [coords]

    def test_troncons_contigus_recolles(self) -> None:
        """Deux troncons partageant un bout donnent une seule polyligne."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        # Le noeud partage n'est pas duplique : 3 sommets et non 4.
        assert [sommet[:2] for sommet in polyligne] == [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]

    def test_troncons_desordonnes_et_inverses(self) -> None:
        """Les parties RecoStaR ne sont ni ordonnees ni orientees : les deux sont corrigees."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[2.0, 0.0], [1.0, 0.0]], [[0.0, 0.0], [1.0, 0.0]]],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        assert len(polyligne) == 3
        assert {tuple(sommet[:2]) for sommet in polyligne} == {(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)}

    def test_z_preserve(self) -> None:
        """Le recollement ne doit pas degrader la geometrie en 2D."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0, 10.0], [1.0, 0.0, 11.0]],
                [[1.0, 0.0, 11.0], [2.0, 0.0, 12.0]],
            ],
        }
        (polyligne,) = recoller_parties_lineaires(geometrie)
        assert [sommet[2] for sommet in polyligne] == [10.0, 11.0, 12.0]

    def test_troncons_disjoints_restent_separes(self) -> None:
        """Rien n'est invente entre deux troncons qui ne se touchent pas."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[50.0, 0.0], [51.0, 0.0]]],
        }
        assert len(recoller_parties_lineaires(geometrie)) == 2

    def test_recollement_partiel(self) -> None:
        """Deux troncons contigus et un isole donnent deux polylignes."""
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [
                [[0.0, 0.0], [1.0, 0.0]],
                [[1.0, 0.0], [2.0, 0.0]],
                [[50.0, 0.0], [51.0, 0.0]],
            ],
        }
        assert sorted(len(p) for p in recoller_parties_lineaires(geometrie)) == [2, 3]

    def test_partie_degeneree_ne_leve_pas(self) -> None:
        """Un troncon d'un seul sommet ne decrit aucune ligne : pas de recollement force."""
        geometrie = {"type": "MultiLineString", "coordinates": [[[0.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]]}
        assert recoller_parties_lineaires(geometrie) == [[[0.0, 0.0]], [[1.0, 0.0], [2.0, 0.0]]]

    def test_geometrie_absente_ou_non_lineaire(self) -> None:
        assert recoller_parties_lineaires(None) == []
        assert recoller_parties_lineaires({"type": "Point", "coordinates": [0.0, 0.0]}) == []

    def test_sommets_de_raccord_deviennent_intermediaires(self) -> None:
        """Interet du recollement : les bouts de troncon deviennent evaluables.

        Sans recollement, le sommet partage est un bout de partie dans les deux
        troncons — donc jamais un sommet intermediaire, donc jamais evalue par un
        controle qui raisonne sur des triplets consecutifs.
        """
        geometrie = {
            "type": "MultiLineString",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0]], [[1.0, 0.0], [2.0, 1.0]]],
        }
        intermediaires_sans = sum(max(len(p) - 2, 0) for p in extraire_parties_lineaires(geometrie))
        intermediaires_avec = sum(max(len(p) - 2, 0) for p in recoller_parties_lineaires(geometrie))
        assert intermediaires_sans == 0
        assert intermediaires_avec == 1


class TestToleranceSuperposition:
    """La tolerance planimetrique est partagee par E-9201 et E-6211.

    Elle est calee sur l'arrondi millimetrique de la posList GML : la modifier
    change simultanement le verdict des deux controles, d'ou ce garde-fou.
    """

    def test_vaut_un_millimetre(self) -> None:
        assert TOLERANCE_SUPERPOSITION == 0.001

    def test_plus_stricte_que_l_adjacence_metier_de_e0404(self) -> None:
        # E-6205 tolere 1 cm pour arbitrer une adjacence entre cheminements ;
        # ici on ne compense qu'un artefact numerique, bien plus petit.
        assert TOLERANCE_SUPERPOSITION < 0.01

    def test_plus_large_que_la_tolerance_altimetrique(self) -> None:
        # TOLERANCE_Z compare un flottant a zero ; les deux ne sont pas
        # interchangeables et ne doivent pas converger par megarde.
        assert TOLERANCE_SUPERPOSITION > TOLERANCE_Z


class TestEstZNul:
    """Detection d'une altitude non renseignee."""

    def test_zero_exact(self) -> None:
        assert est_z_nul(0.0)

    def test_altitude_ngf_valide(self) -> None:
        assert not est_z_nul(310.92)

    def test_altitude_negative_valide(self) -> None:
        """Une altitude sous le niveau de la mer reste une altitude renseignee."""
        assert not est_z_nul(-4.5)

    def test_sous_la_tolerance_considere_nul(self) -> None:
        """Le Z est un flottant issu du parsing GML : la comparaison est tolerante."""
        assert est_z_nul(TOLERANCE_Z / 10)

    def test_au_dessus_de_la_tolerance_considere_valide(self) -> None:
        assert not est_z_nul(TOLERANCE_Z * 10)


class TestCorrigerZNuls:
    """Propagation des altitudes valides vers les sommets a Z nul."""

    def test_aucun_z_nul(self) -> None:
        """Aucun Z a corriger : les valeurs restent identiques."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 30.0]]
        assert corriger_z_nuls(coords) == [10.0, 20.0, 30.0]

    def test_z_nul_debut(self) -> None:
        """Z=0.0 en debut : corrige par le premier Z valide suivant (passe arriere)."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0], [2.0, 2.0, 20.0]]
        assert corriger_z_nuls(coords) == [15.0, 15.0, 20.0]

    def test_z_nul_fin(self) -> None:
        """Z=0.0 en fin : corrige par le dernier Z valide precedent (passe avant)."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 20.0], [2.0, 2.0, 0.0]]
        assert corriger_z_nuls(coords) == [10.0, 20.0, 20.0]

    def test_z_nul_milieu(self) -> None:
        """Z=0.0 au milieu : corrige par propagation avant (Z precedent)."""
        coords = [[0.0, 0.0, 10.0], [1.0, 1.0, 0.0], [2.0, 2.0, 30.0]]
        assert corriger_z_nuls(coords) == [10.0, 10.0, 30.0]

    def test_tous_z_nuls(self) -> None:
        """Tous les Z a 0.0 : aucun Z valide, tout reste a 0.0."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
        assert corriger_z_nuls(coords) == [0.0, 0.0]

    def test_plusieurs_z_nuls_consecutifs(self) -> None:
        """Plusieurs Z=0.0 consecutifs : propages par le Z precedent valide."""
        coords = [
            [0.0, 0.0, 10.0],
            [1.0, 1.0, 0.0],
            [2.0, 2.0, 0.0],
            [3.0, 3.0, 25.0],
        ]
        assert corriger_z_nuls(coords) == [10.0, 10.0, 10.0, 25.0]

    def test_sans_composante_z(self) -> None:
        """Coordonnees 2D sans Z : traitees comme Z=0.0."""
        coords = [[0.0, 0.0], [1.0, 1.0, 10.0]]
        assert corriger_z_nuls(coords) == [10.0, 10.0]

    def test_polyligne_vide(self) -> None:
        assert corriger_z_nuls([]) == []

    def test_sommet_unique_a_z_nul(self) -> None:
        """Aucun voisin pour propager : la valeur reste a 0.0."""
        assert corriger_z_nuls([[0.0, 0.0, 0.0]]) == [0.0]

    def test_altitude_negative_propagee(self) -> None:
        """Une altitude negative est valide et sert donc de source de propagation."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, -4.5]]
        assert corriger_z_nuls(coords) == [-4.5, -4.5]

    def test_coordonnees_non_modifiees(self) -> None:
        """La fonction ne retourne que les Z : la polyligne source reste intacte."""
        coords = [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0]]
        corriger_z_nuls(coords)
        assert coords == [[0.0, 0.0, 0.0], [1.0, 1.0, 15.0]]

    def test_cas_reel_extremite_non_levee(self) -> None:
        """Cas rencontre en production : extremite accrochee, altitude jamais saisie.

        Le premier sommet est un point calcule par le logiciel de saisie (Z=0),
        les suivants sont leves autour de 310,9 m NGF. Sans correction, le premier
        segment mesure l'altitude du terrain au lieu de sa longueur reelle.
        """
        coords = [
            [850054.073151229, 6799803.32580639, 0.0],
            [850053.6, 6799802.91, 310.92],
            [850053.524504169, 6799802.59986505, 310.9],
        ]
        z = corriger_z_nuls(coords)
        assert z[0] == pytest.approx(310.92)
        assert z[1] == pytest.approx(310.92)
        assert z[2] == pytest.approx(310.9)
