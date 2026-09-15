"""
Tests des relations vers les cables (fonctions_communes/references_cables.py).

Ces fonctions etaient portees par E-5201, E-5100, `utils_cable` et
`utils_cheminement`. L'enjeu principal est `extraire_ids_cables_href` : trois
implementations divergentes y sont fondues, et les cas ci-dessous verifient que
la version retenue satisfait les conventions des trois domaines d'origine — la
virgule des jonctions et cheminements, l'espace des couches aeriennes.
"""

import json
from pathlib import Path
from typing import Any

from recostar.controle.fonctions_communes.modele_recostar import (
    FICHIER_AERIEN,
    FICHIER_CABLE_ELECTRIQUE,
    FICHIER_CABLE_TELECOM,
    FICHIER_CABLE_TERRE,
    FICHIERS_CABLES_PAR_VERSION,
    STATUT_MISE_EN_SERVICE,
)
from recostar.controle.fonctions_communes.references_cables import (
    charger_ids_cables_aeriens,
    collecter_ids_cables_aeriens,
    extraire_ids_cables_href,
    filtrer_cables_a_controler,
    resoudre_fichiers_cables,
)


def _feature_aerien(identifiant: str, cables_href: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"id": identifiant, "cables_href": cables_href},
        "geometry": None,
    }


def _feature_cable(identifiant: str, statut: str | None) -> dict[str, Any]:
    proprietes: dict[str, Any] = {"id": identifiant}
    if statut is not None:
        proprietes["Statut"] = statut
    return {"type": "Feature", "properties": proprietes, "geometry": None}


class TestExtraireIdsCablesHref:
    """Extraction des identifiants, tous separateurs confondus."""

    def test_chaine_unique(self) -> None:
        assert extraire_ids_cables_href("id-cable-1") == ["id-cable-1"]

    def test_separateur_virgule(self) -> None:
        """Convention des jonctions et cheminements (serialisation GML)."""
        assert extraire_ids_cables_href("id-1,id-2,id-3") == ["id-1", "id-2", "id-3"]

    def test_separateur_virgule_et_espace(self) -> None:
        assert extraire_ids_cables_href("id-1, id-2") == ["id-1", "id-2"]

    def test_separateur_espace(self) -> None:
        """Convention des couches aeriennes."""
        assert extraire_ids_cables_href("id-1 id-2") == ["id-1", "id-2"]

    def test_liste(self) -> None:
        assert extraire_ids_cables_href(["id-1", "id-2"]) == ["id-1", "id-2"]

    def test_liste_avec_valeur_nulle(self) -> None:
        assert extraire_ids_cables_href(["id-1", None, "id-2"]) == ["id-1", "id-2"]

    def test_valeur_absente(self) -> None:
        assert extraire_ids_cables_href(None) == []

    def test_chaine_vide(self) -> None:
        assert extraire_ids_cables_href("") == []

    def test_type_inattendu(self) -> None:
        """Une valeur d'un autre type ne doit pas interrompre le controle."""
        assert extraire_ids_cables_href(42) == []

    def test_identifiants_uuid_avec_chevrons(self) -> None:
        """Forme reelle des identifiants RecoStaR : ni virgule ni espace interne."""
        assert extraire_ids_cables_href("id<uuid1>,id<uuid2>") == ["id<uuid1>", "id<uuid2>"]


class TestCollecterIdsCablesAeriens:
    """Rassemblement des identifiants portes par les entites aeriennes."""

    def test_reference_simple(self) -> None:
        assert collecter_ids_cables_aeriens([_feature_aerien("a1", "cable-1")]) == {"cable-1"}

    def test_reference_liste(self) -> None:
        features = [_feature_aerien("a1", ["cable-1", "cable-2"])]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_references_multiples_dans_une_chaine(self) -> None:
        features = [_feature_aerien("a1", "cable-1 cable-2")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_entites_multiples_cumulees(self) -> None:
        features = [_feature_aerien("a1", "cable-1"), _feature_aerien("a2", "cable-2")]
        assert collecter_ids_cables_aeriens(features) == {"cable-1", "cable-2"}

    def test_aucune_reference(self) -> None:
        assert collecter_ids_cables_aeriens([]) == set()


class TestChargerIdsCablesAeriens:
    """Lecture de la couche aerienne depuis le repertoire controle."""

    def test_couche_absente_n_exclut_rien(self, tmp_path: Path) -> None:
        """Sans couche aerienne, aucun cable n'est exclu du controle."""
        assert charger_ids_cables_aeriens(str(tmp_path)) == set()

    def test_identifiants_charges(self, tmp_path: Path) -> None:
        collection = {"type": "FeatureCollection", "features": [_feature_aerien("a1", "cable-1,cable-2")]}
        (tmp_path / FICHIER_AERIEN).write_text(json.dumps(collection), encoding="utf-8")
        assert charger_ids_cables_aeriens(str(tmp_path)) == {"cable-1", "cable-2"}


class TestResoudreFichiersCables:
    """Selection des couches de cables selon la version du jeu."""

    def test_version_1_0_sans_telecom(self) -> None:
        """La couche de telecommunication n'existe pas en V1.0."""
        fichiers = resoudre_fichiers_cables("1.0")
        assert set(fichiers) == {FICHIER_CABLE_ELECTRIQUE, FICHIER_CABLE_TERRE}
        assert FICHIER_CABLE_TELECOM not in fichiers

    def test_version_1_1_avec_telecom(self) -> None:
        fichiers = resoudre_fichiers_cables("1.1")
        assert FICHIER_CABLE_TELECOM in fichiers
        assert set(fichiers) == set(FICHIERS_CABLES_PAR_VERSION["1.1"])

    def test_version_inconnue_repli_sur_le_jeu_le_plus_complet(self) -> None:
        """Chercher une couche absente coute moins qu'en ignorer une presente."""
        assert resoudre_fichiers_cables("inconnue") == FICHIERS_CABLES_PAR_VERSION["1.1"]


class TestFiltrerCablesAControler:
    """Restriction au perimetre du recolement."""

    def test_conserve_les_ouvrages_en_mise_en_service(self) -> None:
        features = [
            _feature_cable("c1", STATUT_MISE_EN_SERVICE),
            _feature_cable("c2", "Functional"),
            _feature_cable("c3", "Projected"),
        ]
        assert [f["properties"]["id"] for f in filtrer_cables_a_controler(features)] == ["c1"]

    def test_statut_absent_ecarte(self) -> None:
        assert filtrer_cables_a_controler([_feature_cable("c1", None)]) == []

    def test_collection_vide(self) -> None:
        assert filtrer_cables_a_controler([]) == []
