"""
Modeles de numero de dossier RecoStaR, et resolution de la direction regionale.

Deux controles y puisent :

    E-0005   le numero de dossier ne correspond a aucun modele attendu
    E-0006   il correspond a un modele, mais ne renvoie a aucune DR connue

Les six modeles
---------------
Le numero identifie l'affaire, et pour trois d'entre eux la direction regionale
qui la porte. Tous se terminent par un indice de version — `-1`, `-12`, `-003` —
qui distingue les depots successifs d'un meme dossier.

    type1   DA21/256553-1              prefixe de dossier, lettre + 2 chiffres
    type2   A743/256553-1              prefixe de dossier des DR outre-mer
    type3   RAC-CVL-25-007998-1        trigramme RACING de la DR
    type4   RAC-25-ABC123456789-1      identifiant RACING opaque, sans DR
    type5   12345678-1                 numero interne, sans DR
    type6   OSR20250114-1              dossier OSR, sans DR

Les trois premiers portent une reference resolvable dans `reference_dr.json` ;
les trois derniers n'en portent aucune, et sont donc **hors du perimetre
d'E-0006** : leur conformite au modele est tout ce qu'on peut en dire. C'est ce
que `champ_reference` exprime, et non un oubli.

Pourquoi ces modeles ne remplacent pas `extraire_prefixe`
---------------------------------------------------------
`emprise_dr.extraire_prefixe` est deliberement plus permissif : il resout un
numero approchant pour que les controles d'emprise (E-5106, E-3304) restent
utilisables sur une livraison dont le numero n'est pas encore normalise. Durcir
cette fonction ferait echouer ces controles la ou ils rendent aujourd'hui un
resultat. La conformite au modele est un constat distinct, c'est E-0005 qui le
porte.

Les types 5 et 6 recouvrent exactement les numeros qu'`affaire_exclue_du_controle`
ecarte des controles d'emprise : un numero interne ou OSR est bien forme, mais ne
designe aucune DR.
"""

import re
from dataclasses import dataclass

# Champs de `reference_dr.json` par lesquels un numero resout une DR.
CHAMP_REF_DOSSIER: str = "ref_dossier"
CHAMP_TRIGRAMME: str = "trigramme_racing"


@dataclass(frozen=True, slots=True)
class ModeleNumero:
    """Un modele de numero de dossier, et ce qu'il permet de resoudre.

    - `nom` : identifiant du modele, reporte a l'ecart pour que l'operateur
      sache lequel a ete reconnu ;
    - `motif` : l'expression reguliere, ancree aux deux bouts ;
    - `champ_reference` : champ de `reference_dr.json` interroge avec le groupe
      `reference` du motif ; None quand le modele n'en porte pas.
    """

    nom: str
    motif: re.Pattern[str]
    champ_reference: str | None


# Les six modeles, dans l'ordre ou ils sont essayes. Ils sont disjoints : l'ordre
# ne change aucun verdict, il fixe seulement le nom rendu.
MODELES: tuple[ModeleNumero, ...] = (
    ModeleNumero("type1", re.compile(r"^(?P<reference>(?:D|A)[A-Z]{1}\d{2})/\d{6}-\d{1,3}$"), CHAMP_REF_DOSSIER),
    ModeleNumero("type2", re.compile(r"^(?P<reference>(?:D|A)74(?:3|4|5|6|7))/\d{6}-\d{1,3}$"), CHAMP_REF_DOSSIER),
    ModeleNumero("type3", re.compile(r"^RAC-(?P<reference>[A-Z]{3})-\d{2}-\d{6}-\d{1,3}$"), CHAMP_TRIGRAMME),
    ModeleNumero("type4", re.compile(r"^RAC-\d{2}-(?:[A-Z]|\d){9,12}-\d{1,3}$"), None),
    ModeleNumero("type5", re.compile(r"^\d+-\d{1,3}$"), None),
    ModeleNumero("type6", re.compile(r"^OSR\d{8}-\d{1,3}$"), None),
)

# Liste des modeles, pour les messages d'anomalie et l'aide CLI.
NOMS_MODELES: tuple[str, ...] = tuple(modele.nom for modele in MODELES)


@dataclass(frozen=True, slots=True)
class NumeroReconnu:
    """Numero conforme a un modele, et la reference DR qu'il porte le cas echeant."""

    modele: ModeleNumero
    reference: str | None


def reconnaitre(numero: str) -> NumeroReconnu | None:
    """Retourne le modele auquel le numero repond, ou None s'il n'en suit aucun.

    La comparaison porte sur le numero debarrasse de ses espaces de bord, seule
    tolerance admise : les modeles sont ancres, et une casse differente designe
    un autre dossier.
    """
    valeur = numero.strip()
    for modele in MODELES:
        correspondance = modele.motif.match(valeur)
        if correspondance is None:
            continue
        # `reference` n'existe que sur les trois modeles qui en portent une ;
        # `groupdict` evite un IndexError sur les trois autres.
        return NumeroReconnu(modele, correspondance.groupdict().get("reference"))
    return None


def references_connues(references: list[dict[str, object]], champ: str) -> frozenset[str]:
    """Indexe en majuscules les valeurs d'un champ de `reference_dr.json`.

    Un frozenset : l'appartenance est testee une fois par livraison, mais la
    table compte une soixantaine d'entrees et l'index se construit une seule
    fois. La normalisation en majuscules suit `construire_index`, dont les cles
    sont deja insensibles a la casse.
    """
    return frozenset(str(entree[champ]).upper() for entree in references if entree.get(champ))
