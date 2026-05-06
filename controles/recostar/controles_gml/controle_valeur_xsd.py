"""
Controle de conformite des valeurs aux listes autorisees du modele RecoStaR.

Pour chaque fichier GeoJSON RPD_*.geojson produit par la conversion GML,
verifie que les champs dont le domaine de valeurs est defini dans
`referentiels/recostar/recostar_referentiels_V1_1.json` ne contiennent
que des valeurs autorisees.

Ce controle est bloquant : toute valeur non conforme doit etre corrigee
avant l'export.

Usage CLI :
    python controle_valeur_xsd.py --repertoire <chemin> [--sortie <chemin>]

Sorties :
- rapport_controle_valeur_xsd.json (synthese globale)
- ecarts_valeur_xsd_<nom_fichier>.geojson (un fichier par GeoJSON d'entree
  presentant des ecarts, avec CRS propage).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Prefixe des fichiers GeoJSON a controler
PREFIXE_FICHIER: str = "RPD_"
SUFFIXE_FICHIER: str = ".geojson"

# Fichiers de sortie
FICHIER_RAPPORT_JSON: str = "rapport_controle_valeur_xsd.json"
PREFIXE_ECARTS_GEOJSON: str = "ecarts_valeur_xsd_"
FICHIER_ECARTS_AGREGE: str = "ecarts_valeur_xsd.geojson"

# Chemin par defaut du referentiel de valeurs (relatif a la racine du depot)
CHEMIN_REFERENTIEL_DEFAUT: str = os.path.join(
    "referentiels", "recostar", "recostar_referentiels_V1_1.json"
)

# Mapping statique des champs soumis a une liste de valeurs autorisees.
# Cle externe : nom du fichier GeoJSON (sans extension).
# Cle interne : nom du champ dans les proprietes GeoJSON.
# Valeur : nom du type de reference dans le JSON des referentiels.
# Les champs suffixes par "_href" portent bien une valeur de code (cf. conversion).
MAPPING_CHAMPS_TYPES: dict[str, dict[str, str]] = {
    "RPD_CableElectrique_Reco": {
        "DomaineTension": "DomaineTensionValue",
        "Isolant": "IsolantValueReco",
        "Materiau": "CableMaterialTypeValue",
        "HierarchieBT": "HierarchieBTValue",
        "Statut": "ConditionOfFacilityValueReco",
        "FonctionCable_href": "FonctionCableElectriqueValue",
    },
    "RPD_CableTerre_Reco": {
        "Materiau": "CableMaterialTypeValue",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_CableTelecommunication_Reco": {
        "Fonction": "FonctionTelecomValue",
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_Jonction_Reco": {
        "DomaineTension": "DomaineTensionValue",
        "TypeJonction": "TypeJonctionValueReco",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_Coffret_Reco": {
        "TypeCoffret_href": "TypeCoffretValue",
        "FonctionCoffret_href": "FonctionCoffretValue",
        "ImplantationArmoire_href": "ImplantationArmoireValue",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_Support_Reco": {
        "NatureSupport_href": "NatureSupportValue",
        "Matiere_href": "MatiereValue",
        "Classe_href": "ClasseSupportValue",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_PosteElectrique_Reco": {
        "Categorie_href": "CategoriesPosteValue",
        "TypePoste_href": "TypePosteValue",
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_Terre_Reco": {
        "NatureTerre_href": "NatureTerreValue",
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_Fourreau_Reco": {
        "Materiau": "ProtectionMaterialTypeValueReco",
        "EtatCoupeType": "EtatCoupeTypeValueReco",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_PleineTerre_Reco": {
        "EtatCoupeType": "EtatCoupeTypeValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_ProtectionMecanique_Reco": {
        "Materiau": "ProtectionMaterialTypeValueReco",
        "EtatCoupeType": "EtatCoupeTypeValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_Aerien_Reco": {
        "ModePose": "ModePoseValue",
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_PointDeComptage_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
        "PrecisionXY": "ClassePrecisionReseauValue",
        "PrecisionZ": "ClassePrecisionReseauValue",
    },
    "RPD_BatimentTechnique_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_EnceinteCloturee_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_CoupeCircuitAFusibles_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_JeuBarres_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_SupportModules_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
    "RPD_OuvrageCollectifBranchement_Reco": {
        "Statut": "ConditionOfFacilityValueReco",
    },
}


def lister_fichiers_rpd(repertoire: str) -> list[str]:
    """Liste les fichiers GeoJSON prefixes par RPD_ dans le repertoire.

    Retourne les noms de fichiers tries par ordre alphabetique.
    """
    if not os.path.isdir(repertoire):
        return []
    return sorted(
        nom
        for nom in os.listdir(repertoire)
        if nom.startswith(PREFIXE_FICHIER) and nom.endswith(SUFFIXE_FICHIER)
    )


def lire_geojson(chemin: str) -> dict[str, Any] | None:
    """Lit un fichier GeoJSON et retourne son contenu. Retourne None si absent."""
    if not os.path.isfile(chemin):
        return None
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def charger_referentiel(chemin: str) -> dict[str, Any]:
    """Charge le fichier JSON des referentiels de valeurs."""
    with open(chemin, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def _indexer_valeurs_autorisees(referentiel: dict[str, Any]) -> dict[str, set[str]]:
    """Construit un index `nom_type -> set des valeurs autorisees`.

    L'utilisation d'un set garantit une verification d'appartenance en O(1)
    pendant le parcours des features.
    """
    index: dict[str, set[str]] = {}
    for objet in referentiel.get("objets", {}).values():
        for nom_type, info in objet.get("types", {}).items():
            valeurs_autorisees = {
                entree["valeur"]
                for entree in info.get("valeurs", [])
                if isinstance(entree, dict) and "valeur" in entree
            }
            if valeurs_autorisees:
                index[nom_type] = valeurs_autorisees
    return index


def _nom_sans_extension(nom_fichier: str) -> str:
    """Retourne le nom du fichier sans l'extension .geojson."""
    if nom_fichier.endswith(SUFFIXE_FICHIER):
        return nom_fichier[: -len(SUFFIXE_FICHIER)]
    return nom_fichier


def _detecter_ecarts_feature(
    feature: dict[str, Any],
    champs_a_controler: dict[str, str],
    index_valeurs: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Retourne les ecarts detectes sur une feature.

    Chaque ecart precise le champ, le type attendu et la valeur non conforme.
    Les valeurs vides (None ou chaine vide) sont ignorees : la presence
    obligatoire des champs releve d'un autre controle.
    """
    ecarts: list[dict[str, Any]] = []
    proprietes = feature.get("properties", {})
    for nom_champ, nom_type in champs_a_controler.items():
        valeur = proprietes.get(nom_champ)
        if valeur in (None, ""):
            continue
        valeurs_autorisees = index_valeurs.get(nom_type)
        if valeurs_autorisees is None:
            continue
        if str(valeur) in valeurs_autorisees:
            continue
        ecarts.append(
            {
                "champ": nom_champ,
                "type_reference": nom_type,
                "valeur": valeur,
            }
        )
    return ecarts


def _construire_feature_ecart(
    feature_source: dict[str, Any],
    nom_fichier: str,
    ecarts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construit la feature GeoJSON decrivant une entite en ecart.

    La geometrie d'origine est conservee pour l'affichage cartographique.
    """
    proprietes_source = feature_source.get("properties", {})
    identifiant = proprietes_source.get("id") or feature_source.get("id")
    detail_ecarts = [
        f"{ecart['champ']}={ecart['valeur']!r} (attendu : {ecart['type_reference']})"
        for ecart in ecarts
    ]
    return {
        "type": "Feature",
        "properties": {
            "id_entite": identifiant,
            "fichier_source": nom_fichier,
            "type_anomalie": "valeur_non_conforme_xsd",
            "priorite": "bloquant",
            "nombre_ecarts": len(ecarts),
            "ecarts": ecarts,
            "message": " ; ".join(detail_ecarts),
        },
        "geometry": feature_source.get("geometry"),
    }


def controler_fichier(
    nom_fichier: str,
    collection: dict[str, Any],
    index_valeurs: dict[str, set[str]],
) -> dict[str, Any]:
    """Controle un fichier GeoJSON et retourne un resume + les features en ecart.

    Retourne un dictionnaire contenant :
    - `features_ecarts` : liste des features a ecrire dans le GeoJSON de sortie
    - `anomalies` : liste condensee des ecarts (pour le rapport JSON)
    - `nombre_features` : nombre total de features analysees
    - `crs` : CRS du fichier source (pour propagation)
    """
    nom_base = _nom_sans_extension(nom_fichier)
    champs_a_controler = MAPPING_CHAMPS_TYPES.get(nom_base, {})
    features_source = collection.get("features", [])
    crs = collection.get("crs")

    features_ecarts: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    if not champs_a_controler:
        return {
            "features_ecarts": features_ecarts,
            "anomalies": anomalies,
            "nombre_features": len(features_source),
            "crs": crs,
        }

    for feature in features_source:
        ecarts = _detecter_ecarts_feature(feature, champs_a_controler, index_valeurs)
        if not ecarts:
            continue
        feature_ecart = _construire_feature_ecart(feature, nom_fichier, ecarts)
        features_ecarts.append(feature_ecart)
        anomalies.append(
            {
                "fichier": nom_fichier,
                "id_entite": feature_ecart["properties"]["id_entite"],
                "ecarts": ecarts,
            }
        )

    return {
        "features_ecarts": features_ecarts,
        "anomalies": anomalies,
        "nombre_features": len(features_source),
        "crs": crs,
    }


def construire_geojson_ecarts(
    features: list[dict[str, Any]],
    crs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Construit un FeatureCollection incluant le CRS pour l'affichage QGIS."""
    resultat: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if crs is not None:
        resultat["crs"] = crs
    return resultat


def construire_rapport_json(
    resultats_par_fichier: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Construit le rapport JSON synthetique agrege sur tous les fichiers."""
    total_features = sum(
        info["nombre_features"] for info in resultats_par_fichier.values()
    )
    anomalies_globales: list[dict[str, Any]] = []
    for info in resultats_par_fichier.values():
        anomalies_globales.extend(info["anomalies"])

    detail_fichiers = [
        {
            "fichier": nom,
            "nombre_features": info["nombre_features"],
            "nombre_ecarts": len(info["anomalies"]),
        }
        for nom, info in sorted(resultats_par_fichier.items())
    ]

    return {
        "controle": "valeur_xsd",
        "bloquant": len(anomalies_globales) > 0,
        "nombre_fichiers_analyses": len(resultats_par_fichier),
        "nombre_features_total": total_features,
        "nombre_anomalies": len(anomalies_globales),
        "fichiers": detail_fichiers,
        "anomalies": anomalies_globales,
    }


def _ecrire_json(donnees: dict[str, Any], chemin: str) -> None:
    """Ecrit un dictionnaire au format JSON dans un fichier."""
    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)


def _ecrire_ecarts_par_fichier(
    resultats_par_fichier: dict[str, dict[str, Any]],
    dossier_sortie: str,
) -> list[str]:
    """Ecrit un GeoJSON d'ecarts par fichier presentant des anomalies.

    Retourne la liste des chemins effectivement ecrits.
    """
    chemins_ecrits: list[str] = []
    for nom_fichier, info in resultats_par_fichier.items():
        features = info["features_ecarts"]
        if not features:
            continue
        nom_sortie = (
            PREFIXE_ECARTS_GEOJSON + _nom_sans_extension(nom_fichier) + SUFFIXE_FICHIER
        )
        chemin = os.path.join(dossier_sortie, nom_sortie)
        geojson = construire_geojson_ecarts(features, info["crs"])
        _ecrire_json(geojson, chemin)
        chemins_ecrits.append(chemin)
    return chemins_ecrits


def _resoudre_chemin_referentiel(chemin_explicite: str | None) -> str:
    """Resout le chemin du referentiel : argument explicite ou par defaut.

    Le chemin par defaut pointe vers `referentiels/recostar/...` en remontant
    depuis l'emplacement du script (trois niveaux au-dessus).
    """
    if chemin_explicite is not None:
        return chemin_explicite
    racine = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(racine, CHEMIN_REFERENTIEL_DEFAUT)


def executer_controle_cli(
    repertoire: str,
    sortie: str | None = None,
    chemin_referentiel: str | None = None,
) -> dict[str, Any]:
    """Execute le controle des valeurs XSD en mode CLI.

    Parcourt les fichiers RPD_*.geojson, verifie la conformite des valeurs
    et genere les fichiers de sortie (rapport JSON + GeoJSON par fichier).
    """
    if not os.path.isdir(repertoire):
        return {"succes": False, "erreur": f"Repertoire introuvable : {repertoire}"}

    chemin_ref = _resoudre_chemin_referentiel(chemin_referentiel)
    if not os.path.isfile(chemin_ref):
        return {"succes": False, "erreur": f"Referentiel introuvable : {chemin_ref}"}

    fichiers = lister_fichiers_rpd(repertoire)
    if not fichiers:
        return {"succes": False, "erreur": "Aucun fichier RPD_*.geojson trouve"}

    referentiel = charger_referentiel(chemin_ref)
    index_valeurs = _indexer_valeurs_autorisees(referentiel)

    resultats_par_fichier: dict[str, dict[str, Any]] = {}
    for nom_fichier in fichiers:
        collection = lire_geojson(os.path.join(repertoire, nom_fichier))
        if collection is None:
            continue
        resultats_par_fichier[nom_fichier] = controler_fichier(
            nom_fichier, collection, index_valeurs
        )

    dossier_sortie = sortie if sortie is not None else repertoire
    os.makedirs(dossier_sortie, exist_ok=True)

    rapport = construire_rapport_json(resultats_par_fichier)
    chemin_rapport = os.path.join(dossier_sortie, FICHIER_RAPPORT_JSON)
    _ecrire_json(rapport, chemin_rapport)

    chemins_ecarts = _ecrire_ecarts_par_fichier(resultats_par_fichier, dossier_sortie)

    # Ecriture du fichier agrege pour le rapport PDF
    toutes_features: list[dict[str, Any]] = []
    crs_agrege: dict[str, Any] | None = None
    for info in resultats_par_fichier.values():
        toutes_features.extend(info["features_ecarts"])
        if crs_agrege is None and info["crs"] is not None:
            crs_agrege = info["crs"]
    geojson_agrege = construire_geojson_ecarts(toutes_features, crs_agrege)
    chemin_agrege = os.path.join(dossier_sortie, FICHIER_ECARTS_AGREGE)
    _ecrire_json(geojson_agrege, chemin_agrege)

    return {
        "succes": True,
        "rapport": chemin_rapport,
        "ecarts": chemins_ecarts,
        "ecarts_agrege": chemin_agrege,
        "nombre_anomalies": rapport["nombre_anomalies"],
    }


def main() -> None:
    """Point d'entree CLI du controle de conformite des valeurs XSD."""
    parseur = argparse.ArgumentParser(
        description=(
            "Controle de conformite des valeurs aux listes autorisees "
            "du modele RecoStaR (Enumerations et CodeLists)."
        )
    )
    parseur.add_argument(
        "--repertoire",
        required=True,
        help="Repertoire contenant les fichiers RPD_*.geojson a controler",
    )
    parseur.add_argument(
        "--sortie",
        default=None,
        help="Repertoire de sortie (defaut : meme repertoire que l'entree)",
    )
    parseur.add_argument(
        "--referentiel",
        default=None,
        help=(
            "Chemin du JSON des referentiels (defaut : "
            "referentiels/recostar/recostar_referentiels_V1_1.json)"
        ),
    )
    arguments = parseur.parse_args()

    resultat = executer_controle_cli(
        arguments.repertoire, arguments.sortie, arguments.referentiel
    )
    json.dump(resultat, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
