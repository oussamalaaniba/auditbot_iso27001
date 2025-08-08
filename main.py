from core.workflow import run_questionnaire, save_responses_to_excel
from core.analysis import analyse_responses, save_gap_analysis
from core.report import generate_audit_report

if __name__ == "__main__":
    # Étape 1 : Poser les questions et sauvegarder les réponses
    responses = run_questionnaire()
    save_responses_to_excel(responses)

    # Étape 2 : Analyser les réponses et générer la Gap Analysis
    gap_analysis = analyse_responses(responses)
    save_gap_analysis(gap_analysis)

    # Étape 3 : Générer le rapport
    generate_audit_report()


