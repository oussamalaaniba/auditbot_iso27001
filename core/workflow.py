# core/workflow.py
from core.questions import ISO_QUESTIONS
import pandas as pd

def run_questionnaire():
    """
    Lance le questionnaire ISO 27001 et enregistre les réponses.
    """
    print("\n===== AuditBot ISO 27001 - Questionnaire =====\n")
    responses = {}

    # Parcours de chaque domaine ISO 27001
    for domain, questions in ISO_QUESTIONS.items():
        print(f"\n--- {domain} ---")
        responses[domain] = {}

        for question in questions:
            answer = input(f"{question} \nRéponse : ")
            responses[domain][question] = answer

    return responses


def save_responses_to_excel(responses, filename="data/output/audit_responses.xlsx"):
    """
    Sauvegarde les réponses du questionnaire dans un fichier Excel.
    """
    # Transforme le dictionnaire en liste pour Excel
    data = []
    for domain, questions in responses.items():
        for question, answer in questions.items():
            data.append({
                "Domaine ISO 27001": domain,
                "Question": question,
                "Réponse": answer
            })

    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"\n✅ Réponses sauvegardées dans : {filename}")

