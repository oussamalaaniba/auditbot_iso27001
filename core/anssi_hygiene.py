# core/anssi_hygiene.py
from typing import Dict, List

ANSSI_SECTIONS: Dict[str, List[dict]] = {
    "I – Sensibiliser et former": [
        {"id": "I-1", "title": "Former les équipes opérationnelles"},
        {"id": "I-2", "title": "Sensibiliser les utilisateurs"},
        {"id": "I-3", "title": "Maîtriser les risques de l’infogérance"},
    ],
    "II – Connaître le SI": [
        {"id": "II-4", "title": "Identifier données/serveurs sensibles & schéma réseau"},
        {"id": "II-5", "title": "Inventaire des comptes privilégiés"},
        {"id": "II-6", "title": "Procédures arrivée/départ/changement"},
        {"id": "II-7", "title": "Autoriser la connexion aux seuls équipements maîtrisés"},
    ],
    "III – Authentifier & contrôler les accès": [
        {"id": "III-8", "title": "Comptes nominatifs & séparation des rôles"},
        {"id": "III-9", "title": "Droits sur les ressources sensibles"},
        {"id": "III-10", "title": "Règles de mots de passe"},
        {"id": "III-11", "title": "Protéger les mots de passe stockés"},
        {"id": "III-12", "title": "Changer les identifiants par défaut"},
        {"id": "III-13", "title": "Authentification forte"},
    ],
    "IV – Sécuriser les postes": [
        {"id": "IV-14", "title": "Niveau de sécurité minimal du parc"},
        {"id": "IV-15", "title": "Se protéger des supports amovibles"},
        {"id": "IV-16", "title": "Gestion centralisée des politiques de sécurité"},
        {"id": "IV-17", "title": "Activer/configurer le pare-feu local"},
        {"id": "IV-18", "title": "Chiffrer les données sensibles transmises"},
    ],
    "V – Sécuriser le réseau": [
        {"id": "V-19", "title": "Segmenter & cloisonner le réseau"},
        {"id": "V-20", "title": "Sécurité du Wi-Fi & séparation des usages"},
        {"id": "V-21", "title": "Protocoles réseau sécurisés"},
        {"id": "V-22", "title": "Passerelle d’accès sécurisé à Internet"},
        {"id": "V-23", "title": "Cloisonner les services exposés Internet"},
        {"id": "V-24", "title": "Protéger la messagerie professionnelle"},
        {"id": "V-25", "title": "Sécuriser les interconnexions partenaires"},
        {"id": "V-26", "title": "Contrôler l’accès aux salles serveurs/locaux techniques"},
    ],
    "VI – Sécuriser l’administration": [
        {"id": "VI-27", "title": "Interdire Internet sur postes/serveurs d’admin"},
        {"id": "VI-28", "title": "Réseau d’administration dédié/cloisonné"},
        {"id": "VI-29", "title": "Limiter les droits d’admin sur postes"},
    ],
    "VII – Gérer le nomadisme": [
        {"id": "VII-30", "title": "Sécurisation physique des terminaux nomades"},
        {"id": "VII-31", "title": "Chiffrer les données sensibles (matériel perdable)"},
        {"id": "VII-32", "title": "Sécuriser la connexion réseau en mobilité"},
        {"id": "VII-33", "title": "Politiques dédiées aux terminaux mobiles"},
    ],
    "VIII – Maintenir le SI à jour": [
        {"id": "VIII-34", "title": "Politique de mise à jour"},
        {"id": "VIII-35", "title": "Anticiper fin de support & limiter adhérences"},
    ],
    "IX – Superviser, auditer, réagir": [
        {"id": "IX-36", "title": "Activer/configurer les journaux"},
        {"id": "IX-37", "title": "Politique de sauvegarde"},
        {"id": "IX-38", "title": "Audits réguliers & actions correctives"},
    ],
    "X – Pour aller plus loin": [
        {"id": "X-39", "title": "Gestion des vulnérabilités avancée (option)"},
        {"id": "X-40", "title": "Durcissement renforcé (option)"},
        {"id": "X-41", "title": "Tests d’intrusion réguliers (option)"},
        {"id": "X-42", "title": "Plans d’amélioration continue (option)"},
    ],
}

STATUSES = ["Conforme", "Partiellement conforme", "Non conforme", "Pas réponse"]

SCORE_MAP = {
    "Conforme": 2,
    "Partiellement conforme": 1,
    "Non conforme": 0,
    "Pas réponse": None,
}

def flatten_measures():
    rows = []
    for theme, measures in ANSSI_SECTIONS.items():
        for m in measures:
            rows.append({"theme": theme, "id": m["id"], "title": m["title"]})
    return rows

# --- Helpers: transformer une exigence en question FR lisible ---

import re

QUESTION_PREFIX = "L’organisation a-t-elle"
# Tu peux adapter la liste selon tes formulations courantes
_LEMMES_INFINITIF = [
    "mettre en place", "documenter", "définir", "formaliser", "implémenter", "appliquer",
    "assurer", "contrôler", "surveiller", "journaliser", "protéger", "limiter", "séparer",
    "chiffrer", "authentifier", "autoriser", "sauvegarder", "tester", "mettre à jour",
    "maintenir", "recenser"
]

def requirement_to_question_fr(req: str) -> str:
    """Transforme une exigence ANSSI en question claire (français)."""
    if not req:
        return ""
    text = req.strip()

    # Si l'exigence commence par un verbe à l'infinitif (« Mettre en place ... »)
    m = re.match(r"^\s*([A-Za-zÉÈÊÂÎÔÛÀÇéèêâîôûàç'\- ]+?)(?:\s+de|\s+des|\s+du|\s+la|\s+les|\s+l’|:|\s|$)", text, re.IGNORECASE)
    if m:
        debut = m.group(1).lower()
        # normalise quelques variantes
        debut = debut.replace("mettez", "mettre").replace("mise en place", "mettre en place")
        for lemme in _LEMMES_INFINITIF:
            if debut.startswith(lemme):
                # ex: "Mettre en place une politique de mot de passe" ->
                # "L’organisation a-t-elle mis en place une politique de mot de passe ?"
                reste = text[len(m.group(1)):].strip(" :")
                # accord du verbe au passé composé pour une question « état » (déjà en place)
                if lemme.startswith("mettre"):
                    verbe = "mis en place"
                elif lemme.endswith("er"):
                    verbe = lemme[:-2] + "é"
                else:
                    verbe = lemme  # fallback
                return f"{QUESTION_PREFIX} {verbe} {reste} ?".replace("  ", " ")

    # Si l’exigence est déclarative (« Des sauvegardes régulières sont effectuées »)
    # => question de conformité directe
    return f"Cette exigence est-elle respectée : « {text} » ?"


def build_anssi_questions(sections):
    """
    À partir de ANSSI_SECTIONS (tel que déjà défini chez toi), renvoie une liste plate :
    [ { 'theme_id', 'theme', 'req_id', 'requirement', 'question' }, ... ]
    Compatible avec ta fonction flatten_measures si tu l’as déjà.
    """
    items = []
    # Essaie d'utiliser flatten_measures si elle existe
    try:
        measures = flatten_measures(sections)
    except Exception:
        # sinon, on parcourt naïvement
        measures = []
        for s in sections:
            theme = s.get("title") or s.get("name") or s.get("theme") or ""
            theme_id = s.get("id") or s.get("key") or theme
            for m in s.get("measures", []):
                measures.append({
                    "theme_id": theme_id,
                    "theme": theme,
                    "req_id": m.get("id") or m.get("ref") or "",
                    "requirement": m.get("text") or m.get("requirement") or ""
                })

    for m in measures:
        q = requirement_to_question_fr(m.get("requirement", ""))
        items.append({
            "theme_id": m.get("theme_id", ""),
            "theme": m.get("theme", ""),
            "req_id": m.get("req_id", ""),
            "requirement": m.get("requirement", ""),
            "question": q
        })
    return items
