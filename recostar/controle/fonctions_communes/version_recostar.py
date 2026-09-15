"""
Detection de la version RecoStaR d'un jeu de GeoJSON.

Le format RecoStaR existe en deux versions dont les controles n'attendent pas
les memes attributs. La version n'est pas declaree dans les GeoJSON produits par
la conversion : elle se deduit du contenu. Le champ `TypeLeve` des points leves,
present en V1.0 et retire en V1.1, suffit a trancher.

Elle ne releve d'aucun controle en particulier : c'est une propriete du jeu de
donnees, lue avant meme de savoir quelle regle lui appliquer.

Deux points d'entree, selon que le controle lit deja les points leves ou non :

- `resoudre_version` prend les entites en main propre — le controle les a deja
  chargees, inutile de relire le fichier ;
- `determiner_version_depuis_repertoire` lit le fichier de detection lui-meme,
  pour les controles dont les points leves ne sont pas une source (E-5201, E-9200).

Le pendant pour la structuration GML est `xsd_structuration.detection_version`,
qui lit la version dans l'en-tete du GML : elle y est declaree, la deduire
serait inutile.
"""

import os
import sys
from typing import Any

from recostar.controle.fonctions_communes.geojson import lire_geojson
from recostar.controle.fonctions_communes.modele_recostar import CHAMP_TYPE_LEVE, FICHIER_POINT_LEVE

# Version appliquee lorsque la detection n'aboutit pas. La V1.1 est la version
# courante : un jeu non identifiable est plus probablement recent qu'ancien.
VERSION_DEFAUT: str = "1.1"

# Versions du format prises en charge par les controles GeoJSON. Meme convention
# que xsd_structuration.versions, qui les declare pour le GML.
VERSIONS_SUPPORTEES: tuple[str, ...] = ("1.0", "1.1")

# Valeur de l'option --version demandant la detection automatique.
JETON_AUTO: str = "auto"

# Couche interrogee pour deduire la version. Les points leves portent le champ
# discriminant ; c'est la seule couche dont l'absence du champ soit concluante.
FICHIER_DETECTION_VERSION: str = FICHIER_POINT_LEVE


def detecter_version_depuis_features(features: list[dict[str, Any]]) -> str | None:
    """Deduit la version RecoStaR depuis les proprietes des entites.

    Une seule entite portant `TypeLeve` suffit a conclure a la V1.0, le champ
    ayant ete retire en V1.1. L'absence du champ n'est en revanche pas
    concluante — une collection vide ne dit rien —, d'ou le retour None laissant
    l'appelant decider du repli.
    """
    for feature in features:
        props = feature.get("properties") or {}
        if CHAMP_TYPE_LEVE in props:
            return "1.0"
    return None


def resoudre_version(version_demandee: str, features: list[dict[str, Any]]) -> str:
    """Resout la version effective a appliquer, depuis des entites deja chargees.

    En mode auto, deduit la version des proprietes GeoJSON et se replie sur
    VERSION_DEFAUT si la detection echoue. En mode explicite, applique la
    version demandee sans rien deduire.
    """
    if version_demandee != JETON_AUTO:
        return version_demandee

    version_detectee = detecter_version_depuis_features(features)
    if version_detectee is None:
        print(
            f"Version non detectee dans les features : repli sur {VERSION_DEFAUT}.",
            file=sys.stderr,
        )
        return VERSION_DEFAUT
    return version_detectee


def determiner_version_depuis_repertoire(repertoire: str, version_demandee: str) -> str:
    """Resout la version RecoStaR en lisant la couche de detection du repertoire.

    Destine aux controles dont les points leves ne sont pas une source (E-5201,
    E-9200). En mode explicite, la version demandee est appliquee telle quelle
    sans lecture disque. En mode auto, la couche de detection n'etant pas une
    source de ces controles, son absence n'est pas bloquante : elle entraine le
    repli sur VERSION_DEFAUT.
    """
    if version_demandee != JETON_AUTO:
        return version_demandee
    collection = lire_geojson(os.path.join(repertoire, FICHIER_DETECTION_VERSION))
    features = collection.get("features", []) if collection is not None else []
    return resoudre_version(version_demandee, features)
