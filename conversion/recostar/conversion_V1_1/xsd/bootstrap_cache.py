#!/usr/bin/env python3
"""
Bootstrap du cache local des XSD externes référencés par SchemaStarElecRecoStar.xsd.

Suit récursivement les attributs schemaLocation depuis les deux points d'entrée
(GML 3.2.1 et GML 3.3/exr), reproduit la structure d'URL en arborescence
de répertoires (host/path) pour permettre une résolution triviale par
_ResolveurXsdLocal de controle_e112.py.

Utilisation (à exécuter une seule fois, depuis une machine avec accès réseau) :
    python bootstrap_cache.py [chemin_cache]

Par défaut, le cache est créé dans ./cache à côté de ce script.
"""

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Points d'entrée : les deux xs:import déclarés dans SchemaStarElecRecoStar.xsd.
ENTRY_POINTS: tuple[str, ...] = (
    "http://schemas.opengis.net/gml/3.2.1/gml.xsd",
    "http://schemas.opengis.net/gml/3.3/extdEncRule.xsd",
)

# Restriction : on ne télécharge que depuis ces domaines, évite tout
# téléchargement parasite si un XSD référençait un site tiers.
DOMAINES_AUTORISES: frozenset[str] = frozenset(
    {
        "schemas.opengis.net",
        "www.w3.org",
    }
)

# Découverte des dépendances : XSD utilisent à la fois schemaLocation
# (xs:import/xs:include) et href (xlink).
_PATTERN_REFERENCES = re.compile(r'(?:schemaLocation|href)="([^"]+\.xsd)"')


def _telecharger(url: str, destination: Path) -> bytes | None:
    """Télécharge l'URL dans destination, retourne le contenu ou None si échec."""
    requete = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        contenu = urllib.request.urlopen(requete, timeout=30).read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"ECHEC {url}: {exc}", file=sys.stderr)
        return None
    destination.write_bytes(contenu)
    return contenu


def _ajouter_dependances(
    contenu: bytes, url_courante: str, file_attente: list[str]
) -> None:
    """Extrait les schemaLocation du contenu et les empile dans la file."""
    texte = contenu.decode("utf-8", errors="ignore")
    for ref in _PATTERN_REFERENCES.findall(texte):
        file_attente.append(urljoin(url_courante, ref))


def bootstrap(cache_dir: Path) -> tuple[int, int]:
    """Télécharge récursivement les XSD vers cache_dir.

    Retourne (nb_succes, nb_echecs).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    visites: set[str] = set()
    file_attente: list[str] = list(ENTRY_POINTS)
    nb_ok = 0
    nb_ko = 0

    while file_attente:
        url = file_attente.pop()
        if url in visites:
            continue
        visites.add(url)
        parsed = urlparse(url)
        if parsed.netloc not in DOMAINES_AUTORISES:
            continue
        chemin_local = cache_dir / parsed.netloc / parsed.path.lstrip("/")
        chemin_local.parent.mkdir(parents=True, exist_ok=True)
        contenu = _telecharger(url, chemin_local)
        if contenu is None:
            nb_ko += 1
            continue
        nb_ok += 1
        _ajouter_dependances(contenu, url, file_attente)

    return nb_ok, nb_ko


def main() -> None:
    """Point d'entrée CLI."""
    cache = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent / "cache"
    )
    print(f"Cache cible : {cache}")
    nb_ok, nb_ko = bootstrap(cache)
    print(f"Telecharges : {nb_ok}  Echecs : {nb_ko}")
    if nb_ko > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
