# core/analysis.py
import pandas as pd
import os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta

# Charger la clé API
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyse_responses(responses, nom_client=""):
    """
    Transforme les réponses en Gap Analysis enrichie (avec nom du client).
    """
    gap_analysis = []

    for domain, questions in responses.items():
        for question, answer_data in questions.items():

            if isinstance(answer_data, dict):
                answer = answer_data.get("Réponse", "")
                status = answer_data.get("Statut", "")
                reco = answer_data.get("Recommandation", "")
                priority = answer_data.get("Priorité", "")
                due_date = answer_data.get("Échéance", "")
            else:
                # Ancien mode (sans IA)
                answer = str(answer_data)
                status = ""
                reco = ""
                priority = ""
                due_date = ""

            # Fallback si IA n'a rien mis
            if not reco:
                reco = f"Compléter et formaliser les mesures existantes pour le domaine '{domain}'."
            if not priority:
                priority = "Moyenne"
            if not due_date:
                due_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

            gap_analysis.append({
                "Nom du client": nom_client,
                "Domaine ISO 27001": domain,
                "Question": question,
                "Réponse": answer,
                "Statut": status,
                "Recommandation": reco,
                "Priorité": priority,
                "Échéance": due_date
            })

    return gap_analysis


def evaluate_answer(answer, question="", domain=""):
    """
    Évalue la conformité de la réponse via l'IA selon ISO 27001.
    """
    if not answer or str(answer).strip() == "":
        return "❌ Non conforme"  # Fallback si vide

    prompt = f"""
    Tu es un auditeur ISO 27001 expérimenté.
    La question d'audit était : "{question}"
    Domaine ISO : {domain}
    Réponse fournie : "{answer}"

    Évalue la conformité selon ISO 27001 :
    - ✅ Conforme : si la réponse démontre clairement que les exigences sont respectées
    - ⚠️ Partiellement conforme : si la réponse montre un début de mise en œuvre mais incomplet
    - ❌ Non conforme : si la réponse est insuffisante ou hors sujet

    Retourne uniquement le statut : ✅ Conforme, ⚠️ Partiellement conforme ou ❌ Non conforme.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        status = response.choices[0].message.content.strip()
        if status not in ["✅ Conforme", "⚠️ Partiellement conforme", "❌ Non conforme"]:
            return "⚠️ Partiellement conforme"  # Sécurité
        return status
    except Exception as e:
        print(f"Erreur IA évaluation : {e}")
        return "⚠️ Partiellement conforme"  # Fallback


def generate_recommendation(status, domain):
    """
    Génère une recommandation en fonction du statut.
    """
    if status == "❌ Non conforme":
        return f"Mettre en place des mesures conformes au domaine '{domain}'."
    elif status == "⚠️ Partiellement conforme":
        return f"Compléter et formaliser les mesures existantes pour le domaine '{domain}'."
    else:
        return "Maintenir les bonnes pratiques en place."


def save_gap_analysis(gap_analysis, filename="data/output/gap_analysis.xlsx", nom_client=""):
    """
    Sauvegarde la Gap Analysis dans un fichier Excel (avec nom client).
    """
    df = pd.DataFrame(gap_analysis)
    if nom_client and "Nom du client" not in df.columns:
        df["Nom du client"] = nom_client
    df.to_excel(filename, index=False)
    print(f"\n📊 Gap Analysis sauvegardée dans : {filename}")


def generate_action_plan_from_ai(gap_analysis, default_responsable="RSSI", nom_client=""):
    """
    Transforme la Gap Analysis IA en plan d’actions avec nom client.
    """
    action_plan = []
    for entry in gap_analysis:
        if entry["Statut"] == "✅ Conforme":
            continue  # Pas d’action pour conforme

        action_plan.append({
            "Nom du client": nom_client,
            "Domaine": entry["Domaine ISO 27001"],
            "Écart constaté": entry["Question"],
            "Action recommandée": entry["Recommandation"],
            "Responsable": default_responsable,
            "Priorité": entry.get("Priorité", ""),
            "Échéance": entry.get("Échéance", "")
        })

    return action_plan


def save_action_plan_to_excel(action_plan, filename="data/output/action_plan.xlsx"):
    """
    Sauvegarde le plan d’actions dans un fichier Excel.
    """
    if not action_plan:
        print("✅ Aucun plan d’action à enregistrer (tout est conforme).")
        return
    
    df = pd.DataFrame(action_plan)
    df.to_excel(filename, index=False)
    print(f"📅 Plan d’actions sauvegardé dans : {filename}")
