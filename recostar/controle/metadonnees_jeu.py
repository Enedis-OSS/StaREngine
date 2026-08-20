"""
Lecture des metadonnees du jeu de donnees GeoJSON (_metadata.json).

Le fichier est produit par la conversion GML vers GeoJSON et porte l'en-tete du
recolement RecoStaR : date de creation, logiciel de saisie, producteur,
responsable et systeme de projection. Le rapport de controle les restitue pour
que le lecteur sache sur quel recolement porte le controle, et non seulement sur
quel repertoire.

Module tolerant : un fichier absent, illisible ou incomplet ne doit jamais
empecher la production du rapport. Un champ manquant est rendu par une valeur de
repli explicite plutot que par une ligne absente, afin que le lecteur distingue
« information non fournie » de « information non demandee ».

Module pur hormis la lecture du fichier : entierement testable.
"""

import json
from datetime import date
from pathlib import Path

# Nom du fichier de metadonnees du jeu de donnees, produit par la conversion.
# Meme convention que le controle E300, qui y lit la projection attendue.
FICHIER_METADATA: str = "_metadata.json"

# Cle du bloc portant l'en-tete du recolement dans _metadata.json.
BLOC_METADATA: str = "Metadata"

# Valeur affichee lorsqu'un champ est absent ou vide.
VALEUR_ABSENTE: str = "non renseigné"

# Champ du fichier -> libelle affiche, dans l'ordre d'affichage. Table
# declarative : ajouter une metadonnee au rapport se fait ici seulement.
#
# « Date de création » est explicitement rattachee au fichier RecoStaR : le
# bandeau du rapport affiche par ailleurs sa propre date de generation, et les
# deux ne doivent pas pouvoir etre confondues par le lecteur.
CHAMPS_AFFICHES: tuple[tuple[str, str], ...] = (
    ("Datecreation", "Date de création du fichier RecoStaR"),
    ("Logiciel", "Logiciel"),
    ("Producteur", "Producteur"),
    ("Responsable", "Responsable"),
    ("SRS", "SRS"),
)

# Champs dont la valeur est une date ISO a mettre au format francais.
CHAMPS_DATE: frozenset[str] = frozenset({"Datecreation"})

# Libelles des informations issues de la ligne de commande, et non du fichier de
# metadonnees. Contrairement aux champs ci-dessus, elles ne sont affichees que
# lorsqu'elles sont connues : leur absence est un mode d'execution legitime
# (controle d'un repertoire GeoJSON sans GML, pipeline lance sans numero
# d'affaire) et non une metadonnee manquante a signaler.
LIBELLE_FICHIER_GML: str = "Fichier GML contrôlé"
LIBELLE_NUMERO_AFFAIRE: str = "Numéro d'affaire"


def lire_metadonnees(repertoire: Path) -> dict[str, str]:
    """Lit le bloc Metadata de _metadata.json et retourne ses champs en chaines.

    Retourne un dictionnaire vide si le fichier est absent, illisible, mal forme
    ou depourvu du bloc Metadata : l'absence de metadonnees n'est pas une erreur
    de controle, elle est simplement signalee dans le rapport.
    """
    chemin = repertoire / FICHIER_METADATA
    if not chemin.is_file():
        return {}

    try:
        with open(chemin, encoding="utf-8") as fichier:
            contenu = json.load(fichier)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}

    if not isinstance(contenu, dict):
        return {}
    bloc = contenu.get(BLOC_METADATA)
    if not isinstance(bloc, dict):
        return {}
    return {str(cle): str(valeur) for cle, valeur in bloc.items() if valeur is not None}


def formater_date(valeur: str) -> str:
    """Convertit une date ISO (AAAA-MM-JJ) au format francais JJ/MM/AAAA.

    Retourne la valeur inchangee si elle n'est pas une date ISO valide : mieux
    vaut restituer la donnee brute du fichier qu'en masquer le format inattendu.
    """
    try:
        return date.fromisoformat(valeur).strftime("%d/%m/%Y")
    except ValueError:
        return valeur


def _valeur_affichable(champ: str, metadonnees: dict[str, str]) -> str:
    """Valeur d'un champ de metadonnees, prete a l'affichage."""
    valeur = metadonnees.get(champ, "").strip()
    if not valeur:
        return VALEUR_ABSENTE
    if champ in CHAMPS_DATE:
        return formater_date(valeur)
    return valeur


def champs_affichables(
    metadonnees: dict[str, str],
    chemin_gml: Path | None = None,
    numero_affaire: str | None = None,
) -> list[tuple[str, str]]:
    """Construit les couples (libelle, valeur) a afficher dans le rapport.

    Deux natures d'information, deux traitements de l'absence :
      - les champs de _metadata.json (CHAMPS_AFFICHES) sont toujours restitues,
        un champ manquant valant VALEUR_ABSENTE : le fichier est cense les
        porter, leur absence est une anomalie a montrer ;
      - le fichier GML et le numero d'affaire viennent de la ligne de commande et
        ne sont affiches que s'ils sont fournis : leur absence correspond a un
        mode d'execution legitime, l'annoncer serait un faux signal.

    Les deux informations de contexte sont placees en tete : elles designent ce
    qui a ete controle, les metadonnees decrivent ensuite le recolement.
    """
    lignes: list[tuple[str, str]] = []
    if chemin_gml is not None:
        lignes.append((LIBELLE_FICHIER_GML, Path(chemin_gml).name))
    if numero_affaire:
        lignes.append((LIBELLE_NUMERO_AFFAIRE, numero_affaire.strip()))
    lignes.extend((libelle, _valeur_affichable(champ, metadonnees)) for champ, libelle in CHAMPS_AFFICHES)
    return lignes
