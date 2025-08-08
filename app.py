# --- Imports ---
import os
from pathlib import Path
from io import BytesIO

import streamlit as st
import pandas as pd
import plotly.express as px
import fitz
import docx
from dotenv import load_dotenv
from openai import OpenAI

from core.questions import ISO_QUESTIONS_INTERNE, ISO_QUESTIONS_MANAGEMENT
from core.analysis import (
    analyse_responses,
    save_gap_analysis,
    generate_action_plan_from_ai,
    save_action_plan_to_excel
)
from core.report import generate_audit_report
from utils.ai_helper import analyse_documents_with_ai

# --- Config & constantes ---
st.set_page_config(page_title="AuditBot ISO 27001 - IA", layout="wide")

# Base project dir + dossiers de sortie robustes
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Initialisation IA (Cloud -> Local) ---
load_dotenv()  # pour exécution locale
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("🚨 Clé API OpenAI manquante. Ajoutez-la dans Settings → Secrets.")
    st.stop()
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Message d'accueil ---
st.markdown(
    "### 👋 Bienvenue sur **AuditBot ISO 27001**\n"
    "Analysez vos documents (politiques, procédures, rapports) pour pré-remplir le questionnaire, "
    "générez une **Gap Analysis** et un **rapport Word** prêt à partager."
)
st.caption(
    "Astuce : commencez par choisir l’objectif, entrez le nom du client, "
    "puis importez 1 à 3 documents (PDF/DOCX/TXT)."
)

# --- Sélection du mode d'audit ---
st.title("🔍 Audit ISO 27001")

if "audit_mode" not in st.session_state:
    st.session_state.audit_mode = None

col1, col2 = st.columns(2)
with col1:
    if st.button("🎯 Objectif : Audit interne"):
        st.session_state.audit_mode = "interne"
with col2:
    if st.button("🏆 Objectif : Audit officiel / Pré-certification"):
        st.session_state.audit_mode = "officiel"

audit_mode = st.session_state.audit_mode

if audit_mode == "interne":
    ISO_QUESTIONS = ISO_QUESTIONS_INTERNE
elif audit_mode == "officiel":
    ISO_QUESTIONS = {**ISO_QUESTIONS_MANAGEMENT, **ISO_QUESTIONS_INTERNE}
else:
    st.warning("👆 Sélectionnez un objectif pour commencer l'audit.")
    st.stop()

# --- Nom du client ---
client_name_input = st.text_input(
    "🏢 Nom du client pour cet audit",
    placeholder="Exemple : D&A, CACEIS, Banque XYZ..."
).strip()

if client_name_input:
    st.success(
        f"Client sélectionné : **{client_name_input}** "
        "(appuyez sur Enter pour valider si le champ reste rouge)"
    )
else:
    st.warning("Veuillez indiquer le nom du client avant d'importer les documents.")
    st.stop()

# --- Fonctions extraction texte ---
def extract_text_from_pdf(file):
    text = ""
    pdf = fitz.open(stream=file.read(), filetype="pdf")
    for page in pdf:
        text += page.get_text()
    return text

def extract_text_from_docx(file):
    d = docx.Document(file)
    return "\n".join(p.text for p in d.paragraphs)

# --- Détection nom client via IA optimisée ---
def detect_client_name_with_ai(text):
    """
    Utilise l'IA pour identifier l'organisation ou le client mentionné dans le document.
    Analyse uniquement les premières lignes pour éviter les faux positifs et réduire le coût.
    """
    preview_text = text[:1500]  # Limite à 1500 caractères

    prompt = f"""
Tu es un expert en audit ISO 27001.
Voici un extrait du début d'un document d'audit :
---
{preview_text}
---
À partir de cet extrait, identifie uniquement le NOM de l'organisation ou du client
auquel appartient ce document.

IMPORTANT :
- Ne donne pas d'explication.
- Ne réponds que par le nom détecté.
- Si tu n'es pas sûr ou que le nom n'apparaît pas clairement, réponds exactement "Inconnu".
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"Erreur détection IA : {e}")
        return "Inconnu"

# --- Exemples : fichiers téléchargeables pour test ---
def make_example_txt():
    content = (
        "Client: ACME BANK\n"
        "Document: ISMS Policy v1.2\n"
        "Scope: HQ + DataCenter\n"
        "Summary: High-level information security policy aligned to ISO/IEC 27001.\n"
    )
    return content.encode("utf-8")

def make_example_docx():
    d = docx.Document()
    d.add_heading("Access Control Procedure", level=1)
    d.add_paragraph("Client: ACME BANK")
    d.add_paragraph("Purpose: Define access control rules aligned with ISO/IEC 27001 A.9.")
    d.add_paragraph("Scope: Corporate systems, VDI, privileged accounts, third parties.")
    bio = BytesIO()
    d.save(bio)
    bio.seek(0)
    return bio.getvalue()

def make_correct_example_docx(client_name: str):
    d = docx.Document()
    d.add_heading("Exemple - Procédure Sécurité", level=1)
    d.add_paragraph(f"Client: {client_name}")
    d.add_paragraph("Document type: Politique de sécurité de l'information.")
    d.add_paragraph("Aligné avec ISO/IEC 27001 (contrôles A.5 à A.18).")
    bio = BytesIO()
    d.save(bio)
    bio.seek(0)
    return bio.getvalue()

# --- Upload documents ---
st.subheader("📂 Importer documents du client")
with st.expander("📎 Exemples de documents à tester (téléchargeables)"):
    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "⬇️ Télécharger un exemple TXT",
            data=make_example_txt(),
            file_name="exemple_client.txt",
            mime="text/plain",
            use_container_width=True
        )
    with col_b:
        st.download_button(
            "⬇️ Télécharger un exemple DOCX",
            data=make_example_docx(),
            file_name="exemple_procedure.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
st.caption("Formats acceptés : PDF, DOCX, TXT — limite 200 Mo par fichier.")

uploaded_files = st.file_uploader(
    "Importer vos documents",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)

documents_text = ""
detected_client_names = set()

if uploaded_files:
    for file in uploaded_files:
        # Extraction texte
        if file.name.lower().endswith(".pdf"):
            text = extract_text_from_pdf(file)
        elif file.name.lower().endswith(".docx"):
            text = extract_text_from_docx(file)
        elif file.name.lower().endswith(".txt"):
            text = file.read().decode("utf-8", errors="ignore")
        else:
            text = ""

        documents_text += text + "\n"

        # Détection IA du nom client
        detected_name = detect_client_name_with_ai(text)
        if detected_name and detected_name != "Inconnu":
            detected_client_names.add(detected_name)

    # Vérification multi-clients
    if len(detected_client_names) > 1:
        st.error(
            f"⚠️ Plusieurs clients détectés dans les documents : "
            f"{', '.join(detected_client_names)}"
        )
        st.stop()

    # Vérification cohérence avec saisie (blocage strict + suggestion d'exemple)
    if detected_client_names and not any(
        client_name_input.lower() in name.lower() for name in detected_client_names
    ):
        st.error(
            "🚨 Incohérence détectée : "
            f"documents analysés pour {', '.join(detected_client_names)}, "
            f"≠ nom saisi '{client_name_input}'.\n"
            "Veuillez corriger le nom ou importer les bons documents."
        )
        st.download_button(
            f"⬇️ Télécharger un exemple DOCX pour {client_name_input}",
            data=make_correct_example_docx(client_name_input),
            file_name=f"exemple_{client_name_input.replace(' ', '_')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        st.stop()

# --- Analyse IA des réponses audit ---
responses = {}
if documents_text:
    st.info("📡 Analyse IA en cours...")
    responses = analyse_documents_with_ai(documents_text, ISO_QUESTIONS, debug=True)
    st.success("✅ Questionnaire pré-rempli par l'IA.")

# --- Gap Analysis & Filtres ---
if responses:
    gap_analysis = analyse_responses(responses, nom_client=client_name_input)
    save_gap_analysis(gap_analysis, nom_client=client_name_input)

    df_gap = pd.DataFrame(gap_analysis)

    if not df_gap.empty:
        st.subheader("📊 Gap Analysis (vue interactive)")

        # Filtres
        domaines = ["Tous"] + sorted(df_gap["Domaine ISO 27001"].unique())
        priorites = ["Toutes"] + sorted(df_gap["Priorité"].unique())

        col1, col2 = st.columns(2)
        with col1:
            filtre_domaine = st.selectbox("📌 Filtrer par domaine", domaines)
        with col2:
            filtre_priorite = st.selectbox("⚡ Filtrer par priorité", priorites)

        df_filtre = df_gap.copy()
        if filtre_domaine != "Tous":
            df_filtre = df_filtre[df_filtre["Domaine ISO 27001"] == filtre_domaine]
        if filtre_priorite != "Toutes":
            df_filtre = df_filtre[df_filtre["Priorité"] == filtre_priorite]

        st.dataframe(df_filtre, use_container_width=True)

        # Export Excel filtré
        export_gap = OUTPUT_DIR / "gap_analysis_ui.xlsx"
        df_filtre.to_excel(export_gap, index=False)
        st.download_button(
            "📥 Télécharger Gap Analysis (Excel)",
            data=open(export_gap, "rb").read(),
            file_name="gap_analysis.xlsx"
        )

        # Graphique vert/rouge
        if not df_filtre.empty:
            statut_counts = df_filtre["Statut"].value_counts().reset_index()
            statut_counts.columns = ["Statut", "Nombre"]

            color_map = {
                "Conforme": "#2ecc71",
                "✅ Conforme": "#2ecc71",
                "Non conforme": "#e74c3c",
                "❌ Non conforme": "#e74c3c"
            }

            fig = px.pie(
                statut_counts,
                values="Nombre",
                names="Statut",
                title="Répartition par statut de conformité (selon filtre)",
                color="Statut",
                color_discrete_map=color_map
            )
            st.plotly_chart(fig, use_container_width=True)

# --- Formulaire interactif ---
with st.form("audit_form"):
    final_responses = {}
    for domain, questions in ISO_QUESTIONS.items():
        st.subheader(f"📌 {domain}")
        final_responses[domain] = {}
        for q in questions:
            clause = q.get("clause", "")
            question_text = q["question"]
            question_display = f"{clause} – {question_text}" if clause else question_text
            answer_data = responses.get(domain, {}).get(question_text, "")

            if isinstance(answer_data, dict):
                reponse_simple = answer_data.get("Réponse", "")
                new_answer = st.text_area(
                    question_display,
                    value=reponse_simple,
                    key=f"{domain}_{clause}_{question_text}"
                )
                final_responses[domain][question_text] = {**answer_data, "Réponse": new_answer}
            else:
                new_answer = st.text_area(
                    question_display,
                    value=answer_data,
                    key=f"{domain}_{clause}_{question_text}"
                )
                final_responses[domain][question_text] = new_answer

    submitted = st.form_submit_button("📥 Générer l'analyse et le rapport")

# --- Génération rapport & plan d'action ---
if submitted:
    # Sauvegarde des réponses finales
    gap_analysis = analyse_responses(final_responses, nom_client=client_name_input)
    save_gap_analysis(gap_analysis, nom_client=client_name_input)

    # Génération rapport directement depuis l'Excel existant
    report_path = generate_audit_report()

    st.success("✅ Rapport généré avec succès !")
    st.download_button(
        "📄 Télécharger rapport Word",
        data=open(report_path, "rb").read(),
        file_name=Path(report_path).name
    )
    st.download_button(
        "📊 Télécharger Gap Analysis",
        data=open(OUTPUT_DIR / "gap_analysis.xlsx", "rb").read(),
        file_name="gap_analysis.xlsx"
    )

    # Plan d’actions IA
    action_plan = generate_action_plan_from_ai(gap_analysis, nom_client=client_name_input)
    save_action_plan_to_excel(action_plan)

    st.subheader("📅 Plan d’actions recommandé")
    df_plan = pd.DataFrame(action_plan)
    if not df_plan.empty:
        st.dataframe(df_plan, use_container_width=True)
        st.download_button(
            "📥 Télécharger le plan d’actions (Excel)",
            data=open(OUTPUT_DIR / "action_plan.xlsx", "rb").read(),
            file_name="plan_actions.xlsx"
        )
    else:
        st.info("✅ Aucun plan d’action nécessaire, tout est conforme.")
