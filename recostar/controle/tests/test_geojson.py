"""
Tests du module commun utils_geojson_commun.

Couvre la ventilation des anomalies par type, mutualisee par les controles a
sortie GeoJSON, et l'unicite de ce module : aucune famille ne doit en porter
de copie ni de relais.
"""

from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.geojson import compter_anomalies_par_type

# Racine du paquet de controle (repertoire parent de tests/).
_RACINE_CONTROLE = Path(__file__).resolve().parent.parent


def _anomalie(type_anomalie: str) -> dict[str, Any]:
    return {"type_anomalie": type_anomalie, "id_entite": "e1"}


class TestCompterAnomaliesParType:
    """Ventilation des anomalies par type pour le rapport JSON."""

    def test_liste_vide(self) -> None:
        assert compter_anomalies_par_type([]) == {}

    def test_type_unique(self) -> None:
        assert compter_anomalies_par_type([_anomalie("a")]) == {"a": 1}

    def test_occurrences_cumulees(self) -> None:
        anomalies = [_anomalie("a"), _anomalie("a"), _anomalie("b")]
        assert compter_anomalies_par_type(anomalies) == {"a": 2, "b": 1}

    def test_dictionnaire_simple_retourne(self) -> None:
        """Le rapport est serialise en JSON : un Counter ne doit pas fuir."""
        resultat = compter_anomalies_par_type([_anomalie("a")])
        assert type(resultat) is dict

    def test_type_absent_leve(self) -> None:
        """Une anomalie sans type_anomalie est un defaut de programmation.

        Le masquer produirait une ventilation silencieusement fausse.
        """
        try:
            compter_anomalies_par_type([{"id_entite": "e1"}])
        except KeyError:
            return
        raise AssertionError("une anomalie sans type_anomalie doit lever")


class TestUniciteDuModuleCommun:
    """Le module commun doit rester l'unique implementation, sans module-relais.

    Les familles ont longtemps porte un `utils_geojson.py` qui se contentait de
    reexporter ce module : un detour impose par les imports a plat, ou tous les
    relais partageaient le meme nom et se masquaient dans sys.modules. Depuis le
    passage en paquets, chaque famille importe directement
    `recostar.controle.fonctions_communes.geojson`.

    Ce garde interdit la reapparition d'un tel relais : il reintroduirait une
    seconde adresse pour la meme logique, donc un risque de divergence.
    """

    def test_aucun_module_relais_dans_les_familles(self) -> None:
        relais = sorted(_RACINE_CONTROLE.glob("*/utils_geojson.py"))
        assert relais == [], f"module-relais a supprimer : {[str(c) for c in relais]}"

    def test_module_commun_importable_a_son_adresse_canonique(self) -> None:
        """L'adresse unique du module doit rester resolvable par les familles."""
        from importlib import import_module

        assert import_module("recostar.controle.fonctions_communes.geojson") is not None
