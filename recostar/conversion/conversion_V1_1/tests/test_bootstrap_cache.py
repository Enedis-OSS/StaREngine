"""Tests de la politique de sécurité de bootstrap_cache.

On ne teste pas le téléchargement réseau lui-même mais le *garde* qui décide
quelles URL atteignent urllib (whitelist schéma + domaine, CWE-939). Le réseau
est neutralisé en remplaçant `_telecharger`, ce qui permet de vérifier la vraie
fonction `bootstrap()` — et non une copie de sa condition — sans accès externe.

bootstrap_cache.py vit dans le sous-dossier `xsd/`, hors du chemin injecté par
le conftest ; on le charge donc explicitement par son chemin de fichier.
"""

import importlib.util
from pathlib import Path
from urllib.parse import urlparse

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "xsd" / "bootstrap_cache.py"
_spec = importlib.util.spec_from_file_location("bootstrap_cache", _MODULE_PATH)
bootstrap_cache = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(bootstrap_cache)


class TestWhitelistConstantes:
    """La politique déclarée doit rester explicite et minimale."""

    def test_seul_https_est_autorise(self):
        assert bootstrap_cache.SCHEMAS_AUTORISES == frozenset({"https"})

    def test_domaines_autorises_attendus(self):
        assert bootstrap_cache.DOMAINES_AUTORISES == frozenset({"schemas.opengis.net", "www.w3.org"})

    def test_entry_points_en_https(self):
        assert bootstrap_cache.ENTRY_POINTS  # non vide
        assert all(url.startswith("https://") for url in bootstrap_cache.ENTRY_POINTS)


@pytest.fixture
def urls_atteintes(monkeypatch):
    """Neutralise le réseau : capture les URL réellement passées à urlopen.

    `_telecharger` est le seul point où bootstrap() touche le réseau ; en le
    remplaçant, tout ce qui y parvient a franchi le garde. Retourne b"" pour ne
    déclencher aucune dépendance supplémentaire par défaut.
    """
    appelees: list[str] = []

    def faux_telecharger(url, destination):
        appelees.append(url)
        return b""

    monkeypatch.setattr(bootstrap_cache, "_telecharger", faux_telecharger)
    return appelees


class TestGardeSchemaEtDomaine:
    """Un point d'entrée n'atteint le réseau que si schéma ET domaine sont OK."""

    @pytest.mark.parametrize(
        "url, doit_passer",
        [
            ("https://schemas.opengis.net/gml/3.2.1/gml.xsd", True),
            ("https://www.w3.org/2001/xml.xsd", True),
            ("http://schemas.opengis.net/gml/3.2.1/gml.xsd", False),  # clair refusé
            ("ftp://schemas.opengis.net/a.xsd", False),  # schéma exotique
            ("file:///etc/passwd", False),  # lecture locale (CWE-939)
            ("https://evil.com/x.xsd", False),  # hors domaine
        ],
    )
    def test_seules_urls_conformes_atteignent_le_reseau(self, url, doit_passer, urls_atteintes, monkeypatch, tmp_path):
        monkeypatch.setattr(bootstrap_cache, "ENTRY_POINTS", (url,))
        bootstrap_cache.bootstrap(tmp_path)
        assert (url in urls_atteintes) is doit_passer


class TestReferencesMalveillantes:
    """Les schemaLocation/href extraits d'un XSD téléchargé sont aussi filtrés."""

    def test_refs_hors_politique_jamais_telechargees(self, monkeypatch, tmp_path):
        appelees: list[str] = []
        # XSD piégé : seul ok.xsd est conforme, les autres doivent être écartés.
        # Les refs doivent finir en .xsd pour être extraites par le pattern.
        contenu_piege = (
            b"<schema "
            b'schemaLocation="file:///etc/evil.xsd" '
            b'schemaLocation="ftp://schemas.opengis.net/a.xsd" '
            b'schemaLocation="http://schemas.opengis.net/b.xsd" '
            b'href="https://evil.com/c.xsd" '
            b'href="https://schemas.opengis.net/ok.xsd"/>'
        )
        etat = {"premier_appel": True}

        def faux_telecharger(url, destination):
            appelees.append(url)
            if etat["premier_appel"]:
                etat["premier_appel"] = False
                return contenu_piege
            return b""

        monkeypatch.setattr(bootstrap_cache, "_telecharger", faux_telecharger)
        monkeypatch.setattr(
            bootstrap_cache,
            "ENTRY_POINTS",
            ("https://schemas.opengis.net/racine.xsd",),
        )

        bootstrap_cache.bootstrap(tmp_path)

        # Invariant : toute URL atteinte respecte la politique.
        for url in appelees:
            parsed = urlparse(url)
            assert parsed.scheme == "https"
            assert parsed.netloc in bootstrap_cache.DOMAINES_AUTORISES

        # La référence légitime est suivie…
        assert "https://schemas.opengis.net/ok.xsd" in appelees
        # …et aucun des pièges ne l'est.
        assert "file:///etc/evil.xsd" not in appelees
        assert "ftp://schemas.opengis.net/a.xsd" not in appelees
        assert "http://schemas.opengis.net/b.xsd" not in appelees
        assert "https://evil.com/c.xsd" not in appelees
