# --- Imports ---
import os
from pathlib import Path
from io import BytesIO
import io
from typing import Optional, Dict, List, Tuple

import streamlit as st
import pandas as pd
import plotly.express as px
import fitz  # PyMuPDF
import docx
import json
from dotenv import load_dotenv
from openai import OpenAI
import base64
import hashlib
import re

# ISO 27001 (existant)
from core.questions import ISO_QUESTIONS_INTERNE, ISO_QUESTIONS_MANAGEMENT
from core.analysis import (
    analyse_responses,
    save_gap_analysis,
    generate_action_plan_from_ai,
    save_action_plan_to_excel
)
from core.report import generate_audit_report

# ANSSI (nouveau)
from core.anssi_hygiene import ANSSI_SECTIONS, flatten_measures, STATUSES, SCORE_MAP

# (Optionnel) RAG utils si présents
try:
    from utils.ai_helper import build_vector_index, propose_anssi_answer  # RAG avancé
    RAG_AVAILABLE = True
except Exception:
    RAG_AVAILABLE = False

# --- Config & constantes ---
st.set_page_config(page_title="Audit Assistant (ISO 27001 • ANSSI)", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Fond d'écran (optionnel) ---
def add_bg_from_local(image_file: str):
    try:
        with open(image_file, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        st.markdown(
            f"""
            <style>
            .stApp {{
                background-image: url("data:image/png;base64,{encoded}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )
    except Exception:
        pass

if (BASE_DIR / "bg.png").exists():
    add_bg_from_local(str(BASE_DIR / "bg.png"))

# --- Helpers Clé OpenAI (robuste .env -> st.secrets) ---
def get_openai_api_key() -> Optional[str]:
    try: load_dotenv()
    except Exception: pass
    key = os.getenv("OPENAI_API_KEY")
    if key: return key
    try: return st.secrets["OPENAI_API_KEY"]
    except Exception: return None

def get_openai_client() -> Optional[OpenAI]:
    key = get_openai_api_key()
    if not key: return None
    try: return OpenAI(api_key=key)
    except Exception: return None

# =========================================================
#   Uploader GLOBAL (persistant + réutilisable partout)
# =========================================================
def _init_uploaded_docs_state():
    st.session_state.setdefault("uploaded_docs", [])  # [{name, bytes, size, sha1}]

def _file_sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def _extract_text_from_pdf_bytes(b: bytes) -> str:
    try:
        pdf = fitz.open(stream=b, filetype="pdf")
        return "\n".join([p.get_text("text") for p in pdf])
    except Exception:
        return ""

def _extract_text_from_docx_bytes(b: bytes) -> str:
    try:
        d = docx.Document(io.BytesIO(b))
        return "\n".join(p.text for p in d.paragraphs if p.text)
    except Exception:
        return ""

def render_global_uploader():
    """Affiche un uploader réutilisable sur toutes les pages/onglets.
    Les fichiers sont mémorisés et réutilisables pour l'IA/RAG."""
    _init_uploaded_docs_state()
    with st.expander("📎 Documents d'appui (uploader global) — visibles partout", expanded=True):
        new_files = st.file_uploader(
            "Ajouter des documents (PDF/DOCX/TXT/PNG/JPG) pour enrichir l'analyse (RAG)",
            type=["pdf", "docx", "txt", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="global_uploader",
            help="Les documents ajoutés ici restent disponibles sur toutes les pages."
        )
        if new_files:
            added = 0
            for f in new_files:
                data = f.read()
                sig = _file_sha1(data)
                if not any(item.get("sha1") == sig for item in st.session_state["uploaded_docs"]):
                    st.session_state["uploaded_docs"].append({
                        "name": f.name,
                        "bytes": data,
                        "size": len(data),
                        "sha1": sig,
                    })
                    added += 1
            if added:
                st.success(f"{added} document(s) ajouté(s).")

        if st.session_state["uploaded_docs"]:
            st.caption("Documents mémorisés :")
            for i, item in enumerate(st.session_state["uploaded_docs"], start=1):
                col1, col2, col3 = st.columns([6, 2, 2])
                with col1:
                    st.write(f"{i}. **{item['name']}** — {round(item['size']/1024, 1)} KB")
                with col2:
                    st.download_button(
                        "Télécharger",
                        data=item["bytes"],
                        file_name=item["name"],
                        key=f"dl_{item['sha1']}"
                    )
                with col3:
                    if st.button("Retirer", key=f"rm_{item['sha1']}"):
                        st.session_state["uploaded_docs"] = [
                            x for x in st.session_state["uploaded_docs"] if x["sha1"] != item["sha1"]
                        ]
                        st.rerun()

def get_uploaded_docs_bytes() -> List[Tuple[str, bytes]]:
    _init_uploaded_docs_state()
    return [(x["name"], x["bytes"]) for x in st.session_state["uploaded_docs"]]

def get_uploaded_docs_text(truncate: int = 16000) -> str:
    """Concatène le texte des documents uploadés (PDF/DOCX/TXT)."""
    _init_uploaded_docs_state()
    texts: List[str] = []
    for item in st.session_state["uploaded_docs"]:
        name = item["name"].lower()
        b = item["bytes"]
        if name.endswith(".pdf"):
            texts.append(_extract_text_from_pdf_bytes(b))
        elif name.endswith(".docx"):
            texts.append(_extract_text_from_docx_bytes(b))
        elif name.endswith(".txt"):
            try:
                texts.append(b.decode("utf-8", errors="ignore"))
            except Exception:
                pass
    return ("\n\n".join(texts))[:truncate]

# =========================================================
#   Nettoyage sorties IA (pas de JSON affiché)
# =========================================================
def ensure_plain_text(s: str) -> str:
    """Supprime fences ```...``` et convertit un éventuel JSON simple en texte clair FR."""
    if not isinstance(s, str):
        return str(s)
    s2 = re.sub(r"```(?:json|JSON)?\s*", "", s)
    s2 = s2.replace("```", "").strip()
    # tenter JSON -> texte
    try:
        obj = json.loads(s2)
        parts: List[str] = []
        if isinstance(obj, dict):
            if "status" in obj: parts.append(f"**Statut** : {obj['status']}")
            if "justification" in obj and obj.get("justification"):
                parts.append(f"**Justification** : {obj['justification']}")
            if "recommandations" in obj and isinstance(obj["recommandations"], list):
                parts.append("**Recommandations :**\n- " + "\n- ".join(map(str, obj["recommandations"])))
            if "actions_top3" in obj and isinstance(obj["actions_top3"], list):
                parts.append("**Actions prioritaires :**\n- " + "\n- ".join(map(str, obj["actions_top3"])))
            if not parts:
                for k, v in obj.items():
                    if isinstance(v, list):
                        parts.append(f"{k} :\n- " + "\n- ".join(map(str, v)))
                    else:
                        parts.append(f"{k} : {v}")
            return "\n\n".join(parts)
        if isinstance(obj, list):
            lines: List[str] = []
            for it in obj:
                if isinstance(it, dict):
                    line = ", ".join([f"{k}={v}" for k, v in it.items()])
                    lines.append(f"- {line}")
                else:
                    lines.append(f"- {it}")
            return "\n".join(lines)
    except Exception:
        pass
    return s2

def parse_status_from_text(txt: str) -> Optional[str]:
    """Détecte un statut dans un texte libre si présent (Conforme/Partiellement conforme/Non conforme/Pas réponse)."""
    t = txt.lower()
    for s in STATUSES:
        if s.lower() in t:
            return s
    # formats 'statut: conforme'
    m = re.search(r"statut\s*[:\-]\s*(conforme|partiellement conforme|non conforme|pas réponse)", t)
    if m:
        val = m.group(1).strip()
        # normaliser casse
        for s in STATUSES:
            if s.lower() == val:
                return s
    return None

# =========================================================
#   Générateur de questions avancées (ANSSI)
# =========================================================
def _mk_bullets(items: List[str]) -> str:
    return "\n".join([f"- {it}" for it in items])

def _to_question_fr(exigence: str, theme: Optional[str] = None) -> str:
    """Transforme une exigence ANSSI en question pro et actionnable, avec mini-checklist."""
    if not exigence:
        return ""
    txt = exigence.strip()
    low = txt.lower()

    def block(title: str, bullets: List[str]) -> str:
        return f"**{title}**\n\nPoints attendus :\n{_mk_bullets(bullets)}"

    if any(k in low for k in ["sauvegard", "backup", "restaur"]):
        return block(
            "Comment l’organisation assure les sauvegardes et la restauration ?",
            [
                "Périmètre couvert (serveurs, postes, bases, SaaS/Cloud).",
                "Fréquence, rétention, hors-site/offline/immutables (3-2-1).",
                "Chiffrement des sauvegardes et gestion des clés.",
                "Tests de restauration (RPO/RTO), preuves et taux de succès.",
                "Supervision des échecs/écarts et plan PRA/PCA."
            ]
        )
    if any(k in low for k in ["journalis", "log", "siem", "collecte", "traces"]):
        return block(
            "Comment la journalisation et la détection d’incidents sont réalisées ?",
            [
                "Sources collectées (Systèmes, Réseau, Cloud, SaaS, EDR).",
                "Normalisation, horodatage (NTP), intégrité et rétention.",
                "SIEM/SOAR : cas d’usage, corrélation, priorisation.",
                "Alerting, triage, MTTD/MTTR, escalade et couverture 24/7.",
                "Preuves : tableaux de bord, rapports, incidents traités."
            ]
        )
    if any(k in low for k in ["surveill", "monitor", "supervis"]):
        return block(
            "Comment l’organisation supervise ses actifs et services critiques ?",
            [
                "Portée (on-prem, Cloud, réseaux, applicatifs).",
                "Seuils d’alerte, notifications, gestion des faux positifs.",
                "Runbooks / procédures d’exploitation et d’escalade.",
                "Criticité métier, priorisation des actions.",
                "Preuves : SLO/SLA, rapports d’astreinte."
            ]
        )
    if any(k in low for k in ["authentifi", "mfa", "sso", "idm", "idp", "identit"]):
        return block(
            "Comment l’authentification et la gestion des identités sont mises en œuvre ?",
            [
                "SSO/IdP, MFA (périmètre, exceptions, BYOD).",
                "Comptes à privilèges (PAM/JIT/JEA), séparation des tâches.",
                "Joiner/Mover/Leaver et recertification périodique.",
                "Stockage, logs IAM et accès tiers.",
                "Preuves : politiques, preuves MFA, campagnes de revue d’accès."
            ]
        )
    if any(k in low for k in ["autoriser", "habilit", "accès", "rbac", "abac", "droits"]):
        return block(
            "Comment les autorisations et les habilitations sont gouvernées ?",
            [
                "Modèle RBAC/ABAC, rôles standard et sensibles.",
                "Demandes/approbations tracées (tickets, workflows).",
                "Revues d’accès périodiques et preuves.",
                "Accès tiers et comptes techniques.",
                "Preuves : matrices d’habilitation, PV de recertification."
            ]
        )
    if any(k in low for k in ["chiffr", "tls", "https", "kms", "hsm", "clé", "certificat"]):
        return block(
            "Quels mécanismes de chiffrement et de gestion de clés sont en place ?",
            [
                "Données en transit et au repos (algorithmes/tailles).",
                "KMS/HSM : génération, rotation, révocation, séparation des rôles.",
                "Cycle de vie des certificats (inventaire, alerte expirations).",
                "Conformité (RGPD, ANSSI, secteur).",
                "Preuves : inventaires, politiques cryptographiques."
            ]
        )
    if any(k in low for k in ["mise à jour", "mettre à jour", "patch", "correctif", "vulnér", "vulner"]):
        return block(
            "Comment la gestion des vulnérabilités et des correctifs est organisée ?",
            [
                "Inventaire des actifs et classification (criticité).",
                "SLA d’application des patchs (CVSS).",
                "Outillage (WSUS/Intune/Ansible), maintenance windows.",
                "Scans réguliers, exemptions documentées.",
                "Preuves : rapports de scan, tableaux de bord."
            ]
        )
    if any(k in low for k in ["durciss", "edr", "xdr", "antivirus", "pare-feu", "firewall", "waf", "endpoint"]):
        return block(
            "Quels contrôles de protection et de durcissement sont déployés ?",
            [
                "Standards de durcissement (CIS/ANSSI).",
                "EDR/XDR : couverture, politiques, réponses auto.",
                "Protection email/web (anti-phishing, DMARC/DKIM/SPF).",
                "Pare-feu/WAF/NAC, revues et exceptions.",
                "Preuves : rapports de conformité, inventaires."
            ]
        )
    if any(k in low for k in ["segmen", "dmz", "vlan", "microsegment"]):
        return block(
            "Comment la segmentation réseau et la maîtrise des flux sont assurées ?",
            [
                "Zonage (utilisateurs, serveurs, admin, DMZ).",
                "Est-Ouest vs Nord-Sud, règles minimales nécessaires.",
                "Cartographie des flux (CMDB, scanners).",
                "NAC/802.1X, revues régulières.",
                "Preuves : diagrammes, exports de règles."
            ]
        )
    if any(k in low for k in ["documenter", "formaliser", "politique", "procédure"]):
        return block(
            "La gouvernance (politiques & procédures) couvre-t-elle l’exigence ?",
            [
                "Portée, responsabilités (RACI), sponsors.",
                "Versioning, validation, diffusion, contrôle d’application.",
                "Indicateurs de conformité et revues périodiques.",
                "Alignement référentiel/loi, dérogations.",
                "Preuves : documents approuvés, registre de dérogations."
            ]
        )
    if any(k in low for k in ["inventaire", "cmdb", "actif", "patrimoine"]):
        return block(
            "Comment les actifs sont inventoriés et tenus à jour ?",
            [
                "CMDB : couverture, champs (owner, criticité, data).",
                "Découverte auto vs déclaration manuelle.",
                "Cycle de vie (acquisition → retrait), EOL/EOS.",
                "Traçabilité des changements (ITSM), audits.",
                "Preuves : exports CMDB, rapports d’écarts."
            ]
        )
    return block(
        f"Comment l’organisation adresse l’exigence suivante : « {txt} » ?",
        [
            "Gouvernance (rôles, politiques, décision).",
            "Processus (SLA, approbations, exceptions).",
            "Contrôles techniques (outils, paramètres).",
            "Indicateurs (KPI/KRI), supervision et alerting.",
            "Preuves disponibles (docs, journaux, tickets)."
        ]
    )

# =========================================================
#                     ROUTER + HOME
# =========================================================
if "route" not in st.session_state:
    st.session_state["route"] = "home"

def go(route: str):
    st.session_state["route"] = route

def render_home():
    st.title("🧭 Audit Assistant")
    st.caption("Centralisez vos audits, comparez vos pratiques, générez plans d’actions et rapports.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("ISO/IEC 27001")
        st.write("- Questionnaires (interne / pré-certif)\n- Gap Analysis + priorités\n- Rapport prêt à partager")
        st.button("▶️ Entrer dans ISO 27001", key="home_go_iso", use_container_width=True, on_click=lambda: go("iso27001"))
    with col2:
        st.subheader("ANSSI – Guide d’hygiène")
        st.write("- Auto-évaluation par thèmes/mesures\n- Score de maturité & quick-wins\n- Export CSV")
        st.button("▶️ Entrer dans ANSSI Hygiène", key="home_go_anssi", use_container_width=True, on_click=lambda: go("anssi_hygiene"))

# =========================================================
#                      ANSSI PAGE
# =========================================================
def render_anssi_hygiene():
    st.title("🛡️ ANSSI – Guide d’hygiène")
    st.caption("Parcours : 1) Intro  •  2) Questionnaire  •  3) Revue  •  4) Résultats")

    # Uploader global visible partout (exigence utilisateur)
    render_global_uploader()

    # --- State init ---
    st.session_state.setdefault("anssi_stage", "intro")       # intro | questions | review | results
    st.session_state.setdefault("anssi_org", {})              # contexte entreprise
    st.session_state.setdefault("anssi_status", {})           # {id_mesure: statut}
    st.session_state.setdefault("anssi_justifs", {})          # {id_mesure: justification}
    st.session_state.setdefault("anssi_index", None)          # RAG index si dispo

    measures = flatten_measures()
    total = len(measures)

    def compute_progress():
        status_map = st.session_state["anssi_status"]
        answered = sum(1 for m in measures if status_map.get(m["id"]) in ("Conforme","Partiellement conforme","Non conforme"))
        pct_answers = int(round(100 * answered / total)) if total else 0
        return pct_answers, answered

    def _index_docs():
        bins = get_uploaded_docs_bytes()
        if not bins:
            st.warning("Aucun document chargé dans l’uploader global.")
            return
        if not RAG_AVAILABLE:
            st.info("Indexation avancée indisponible (module RAG non importé).")
            return

        class _UploadedLike:
            def __init__(self, name, data):
                self.name = name
                self._data = data
            def getvalue(self):
                return self._data

        files_like = [_UploadedLike(name, b) for name, b in bins]
        with st.spinner("Indexation et embeddings…"):
            st.session_state["anssi_index"] = build_vector_index(files_like)
        st.success("Index construit ✔️")

    stage = st.session_state["anssi_stage"]

    # ---------- 1) INTRO ----------
    if stage == "intro":
        st.subheader("1) Informations de contexte")
        c1, c2 = st.columns(2)
        secteur = c1.text_input("Secteur d’activité", st.session_state["anssi_org"].get("secteur",""), key="anssi_org_secteur")
        nb_emp   = c2.number_input("Nombre d’employés", min_value=1, value=int(st.session_state["anssi_org"].get("nb_emp", 100)), key="anssi_org_nbemp")
        ca       = c1.text_input("Chiffre d’affaires (ex: 120 M€)", st.session_state["anssi_org"].get("ca",""), key="anssi_org_ca")
        pays     = c2.text_input("Filiales / Pays (ex: FR, LU, DE)", st.session_state["anssi_org"].get("pays",""), key="anssi_org_pays")
        st.info("Les documents déposés via l’uploader global seront utilisés par l’IA (RAG/texte).")

        colA, colB, colC = st.columns([1,1,1])
        if colA.button("💾 Enregistrer & continuer", key="anssi_intro_save"):
            st.session_state["anssi_org"] = {"secteur": secteur, "nb_emp": nb_emp, "ca": ca, "pays": pays}
            st.session_state["anssi_stage"] = "questions"
            st.rerun()
        if colB.button("🧭 Retour à l’accueil", key="anssi_intro_home"):
            go("home")
        colC.button("🧱 Indexer les documents (IA avancée)", key="anssi_index_btn_intro", on_click=_index_docs)
        return

    # ---------- IA: Préremplissage global ----------
    def _anssi_autofill_from_global():
        client = get_openai_client()
        if client is None:
            st.warning("ℹ️ Pas de clé OpenAI — préremplissage IA désactivé.")
            return

        org = st.session_state.get("anssi_org", {})

        # Si index RAG dispo + construit -> par mesure (qualité max)
        if RAG_AVAILABLE and st.session_state.get("anssi_index") and st.session_state["anssi_index"].get("chunks"):
            with st.spinner("Analyse IA (RAG) par mesure…"):
                for m in measures:
                    mid = m["id"]
                    requirement = m["title"]
                    question_md = _to_question_fr(requirement, m.get("theme"))
                    try:
                        res = propose_anssi_answer(requirement, question_md, st.session_state["anssi_index"])
                        status = res.get("status", "Pas réponse")
                        if status not in STATUSES:
                            status = "Pas réponse"
                        justif = ensure_plain_text(res.get("justification", ""))
                        cits = res.get("citations", [])
                        if cits:
                            justif = justif + "\n\n" + "Citations: " + "; ".join([f"{c['doc']} p.{c['page']}" for c in cits if isinstance(c, dict) and c.get('doc') and c.get('page')])
                        st.session_state["anssi_status"][mid] = status
                        st.session_state["anssi_justifs"][mid] = justif
                    except Exception:
                        st.session_state["anssi_status"][mid] = st.session_state["anssi_status"].get(mid, "Pas réponse")
                st.success("✅ Préremplissage IA (RAG) terminé.")
            return

        # Sinon: fallback via texte concaténé des uploads (interne; ok JSON car non affiché)
        text = get_uploaded_docs_text()
        if not text:
            st.warning("ℹ️ Aucun document global chargé. Ajoute des fichiers dans l’uploader global.")
            return

        measures_brief = [{"id": m["id"], "title": m["title"], "theme": m["theme"]} for m in measures]

        system_msg = (
            "Tu es un consultant cybersécurité senior. "
            "À partir du contexte d’entreprise et des extraits fournis, "
            "évalue chaque mesure ANSSI et propose un statut conservateur. "
            "Si l'information est insuffisante, réponds 'Pas réponse'. "
            "Réponds STRICTEMENT en JSON (liste d’objets) : "
            "[{\"id\":\"...\",\"status\":\"Conforme|Partiellement conforme|Non conforme|Pas réponse\",\"justification\":\"...\",\"actions_top3\":[\"...\",\"...\",\"...\"]}]"
        )

        user_msg = f"""
Contexte organisation:
- Secteur: {org.get('secteur') or 'Inconnu'}
- Nb employés: {org.get('nb_emp') or 'Inconnu'}
- CA: {org.get('ca') or 'Inconnu'}
- Pays/Filiales: {org.get('pays') or 'Inconnu'}

Référentiel: ANSSI Guide d'hygiène (10 thèmes, ~42 mesures).
Mesures à évaluer (id/title/theme):
{json.dumps(measures_brief, ensure_ascii=False)}

Extraits de documents globaux (tronqués):
{text}

Consignes:
- Donne un statut par mesure parmi: Conforme | Partiellement conforme | Non conforme | Pas réponse
- Justifie brièvement (2-4 lignes) + 3 actions prioritaires.
- Si incertain: 'Pas réponse'.
Renvoie uniquement du JSON valide.
"""

        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg}],
                temperature=0.2,
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
        except Exception as e:
            st.error(f"Erreur IA: {e}")
            return

        for item in data:
            mid = item.get("id")
            status = item.get("status", "Pas réponse")
            justif = item.get("justification", "")
            if not mid:
                continue
            if status not in STATUSES:
                status = "Pas réponse"
            st.session_state["anssi_status"][mid] = status
            st.session_state["anssi_justifs"][mid] = ensure_plain_text(justif)

        st.success("✅ Préremplissage IA terminé (fallback texte concaténé).")

    # ---------- 2) QUESTIONNAIRE ----------
    if stage == "questions":
        pct_answers, answered = compute_progress()
        st.subheader("2) Questionnaire par thématiques")
        st.write(f"Avancement questionnaire : **{pct_answers}%** — ({answered}/{total})")
        st.progress(pct_answers)

        # Actions IA utiles directement ici
        cA, cB, cC = st.columns([1,1,1])
        cA.button("🧠 Préremplir automatiquement (docs globaux)", key="anssi_autofill_btn", on_click=_anssi_autofill_from_global)
        cB.button("🧱 (Re)Indexer documents (IA avancée)", key="anssi_index_btn_q", on_click=_index_docs)
        cC.button("🏠 Accueil", key="anssi_questions_home_btn", on_click=lambda: go("home"))

        theme = st.sidebar.radio("Thèmes", list(ANSSI_SECTIONS.keys()), key="anssi_theme_radio")
        st.subheader(theme)

        # Système de réponse IA en TEXTE CLAIR pour le bouton par mesure
        SYSTEM_FRENCH_PLAIN = (
            "Tu es un auditeur cybersécurité/continuité. "
            "Réponds en français, en texte clair (phrases ou puces). "
            "N'utilise aucun JSON, aucun code fence. "
            "Commence par une ligne 'Statut: ...' avec l'une des valeurs: "
            "Conforme, Partiellement conforme, Non conforme, Pas réponse. "
            "Puis donne une justification concise (3–6 lignes) et 2–4 actions concrètes."
        )

        for m in ANSSI_SECTIONS[theme]:
            mid = m["id"]
            requirement = m["title"]
            question_md = _to_question_fr(requirement, m.get("theme"))

            st.markdown(f"### {mid}")
            st.markdown(question_md)
            with st.expander("Voir l’exigence ANSSI (texte brut)"):
                st.write(requirement)

            # Statut (sélecteur); clé stable par mesure
            current = st.session_state["anssi_status"].get(mid, "Pas réponse")
            new_status = st.selectbox(
                "Statut",
                STATUSES,
                index=STATUSES.index(current) if current in STATUSES else STATUSES.index("Pas réponse"),
                key=f"status_{mid}"
            )
            st.session_state["anssi_status"][mid] = new_status

            # Zone texte consultant (réponse détaillée)
            cur_just = st.session_state["anssi_justifs"].get(mid, "")
            new_just = st.text_area(
                "Réponse détaillée (consultant) – Justification & éléments de preuve",
                value=cur_just,
                key=f"justif_{mid}",
                height=160,
                placeholder="Rédige une justification professionnelle, avec références internes (politiques, journaux, tickets, preuves de tests, etc.)."
            )
            st.session_state["anssi_justifs"][mid] = new_just

            # IA par mesure (texte clair)
            cols = st.columns([1,1])
            if cols[0].button("💡 Proposer avec l’IA", key=f"ai_{mid}"):
                client = get_openai_client()
                if client is None:
                    st.warning("Clé OpenAI manquante.")
                else:
                    try:
                        if RAG_AVAILABLE and st.session_state.get("anssi_index") and st.session_state["anssi_index"].get("chunks"):
                            # Utiliser la fonction RAG existante puis formater en texte clair
                            res = propose_anssi_answer(requirement, question_md, st.session_state["anssi_index"])
                            # Mettre à jour statut si cohérent
                            status = res.get("status")
                            if status in STATUSES:
                                st.session_state["anssi_status"][mid] = status
                            # Justification -> texte clair
                            justif = ensure_plain_text(res.get("justification", ""))
                            cits = res.get("citations", [])
                            if cits:
                                justif += "\n\nCitations: " + "; ".join([f"{c['doc']} p.{c['page']}" for c in cits if isinstance(c, dict) and c.get('doc') and c.get('page')])
                            st.session_state["anssi_justifs"][mid] = justif
                        else:
                            # Fallback: prompt texte clair (sans JSON)
                            context_text = get_uploaded_docs_text(truncate=8000)
                            user_prompt = (
                                f"EXIGENCE: {requirement}\n\nQUESTION:\n{question_md}\n\n"
                                f"CONTEXTE (extraits des documents, éventuellement vide):\n{context_text}\n\n"
                                "Donne uniquement du texte clair. Pas de JSON, pas de balises."
                            )
                            resp = client.chat.completions.create(
                                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                messages=[
                                    {"role":"system","content": SYSTEM_FRENCH_PLAIN},
                                    {"role":"user","content": user_prompt}
                                ],
                                temperature=0.2
                            )
                            content = ensure_plain_text((resp.choices[0].message.content or "").strip())
                            # Essayer d'extraire un statut depuis le texte
                            detected = parse_status_from_text(content) or "Pas réponse"
                            if detected in STATUSES:
                                st.session_state["anssi_status"][mid] = detected
                            st.session_state["anssi_justifs"][mid] = content
                        st.success("Proposition IA appliquée ✔️")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur IA: {e}")

            cols[1].markdown("&nbsp;")
            st.divider()

        c1, c2, c3 = st.columns([1,1,1])
        c1.button("⬅️ Retour à l’accueil", key="anssi_questions_home", on_click=lambda: go("home"))
        c2.button("🔄 Recalculer l’avancement", key="anssi_questions_recalc", on_click=st.rerun)
        if c3.button("➡️ Terminer le questionnaire", key="anssi_questions_next_review"):
            st.session_state["anssi_stage"] = "review"
            st.rerun()
        return

    # ---------- 2.5) REVIEW ----------
    if stage == "review":
        st.subheader("✔️ Revue avant analyse")
        pct_answers, answered = compute_progress()
        st.write(f"Avancement réponses (hors 'Pas réponse') : **{pct_answers}%** — ({answered}/{total})")
        st.progress(pct_answers)

        missing = [m for m in measures if st.session_state["anssi_status"].get(m["id"], "Pas réponse") == "Pas réponse"]
        if missing:
            st.warning(f"Mesures sans réponse : {len(missing)}")
            with st.expander("Voir les mesures sans réponse"):
                for m in missing:
                    st.write(f"- {m['id']} — {m['title']} ({m['theme']})")
        else:
            st.success("Toutes les mesures ont un statut (y compris 'Pas réponse').")

        c1, c2, c3 = st.columns([1,1,1])
        c1.button("⬅️ Retour au questionnaire", key="anssi_review_back_to_questions", on_click=lambda: st.session_state.update({"anssi_stage":"questions"}) or st.rerun())
        c2.button("🏠 Accueil", key="anssi_review_home", on_click=lambda: go("home"))
        if c3.button("✅ Valider & commencer l’analyse (globale)", key="anssi_review_start"):
            st.session_state["anssi_stage"] = "results"
            st.rerun()
        return

    # ---------- 3) RÉSULTATS ----------
    if stage == "results":
        st.subheader("3) Résultats (tableau)")
        rows = []
        for m in measures:
            mid = m["id"]
            requirement = m["title"]
            rows.append({
                "Thème": m["theme"],
                "ID": mid,
                "Mesure (exigence)": requirement,
                "Question": _to_question_fr(requirement, m.get("theme")),
                "Statut": st.session_state["anssi_status"].get(mid, "Pas réponse"),
                "Justification": st.session_state["anssi_justifs"].get(mid, "")
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export CSV", data=csv, file_name="anssi_resultats.csv", mime="text/csv", key="anssi_results_export")
        st.button("↩️ Revenir au questionnaire", key="anssi_results_back_to_questions", on_click=lambda: st.session_state.update({"anssi_stage":"questions"}) or st.rerun())
        st.button("⬅️ Retour à l’accueil", key="anssi_results_home", on_click=lambda: go("home"))
        return

# =========================================================
#            ISO 27001 (page & IA préremplissage)
# =========================================================
def _ai_prefill_iso_by_domain(documents_text: str, iso_questions: Dict[str, List[Dict]]) -> Dict[str, Dict[str, str]]:
    client = get_openai_client()
    if client is None:
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for domain, qs in iso_questions.items():
        q_list = []
        for q in qs:
            clause = q.get("clause", "")
            qtxt = q["question"]
            q_list.append({"clause": clause, "question": qtxt})
        ctx = documents_text[:16000]
        system = (
            "Tu es auditeur ISO/IEC 27001. "
            "Sur la base du contexte fourni, propose une réponse courte (2-4 lignes) et factuelle pour chaque question. "
            "N'invente pas si l'info n'existe pas; mets 'Information insuffisante'. "
            "Renvoie STRICTEMENT du JSON: {\"answers\": [{\"question\": \"...\", \"answer\": \"...\"}, ...]}"
        )
        user = f"DOMAINE: {domain}\nQUESTIONS: {json.dumps(q_list, ensure_ascii=False)}\n\nCONTEXTE:\n{ctx}"
        try:
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.2
            )
            content = (resp.choices[0].message.content or "").strip()
            data = json.loads(content)
            answers = data.get("answers", [])
        except Exception:
            answers = []
        out[domain] = {}
        for a in answers:
            qtxt = a.get("question", "")
            ans  = a.get("answer", "")
            if qtxt:
                out[domain][qtxt] = ans
    return out

def render_iso27001():
    st.title("🔍 Audit ISO 27001")

    # Uploader global utilisable aussi côté ISO (facultatif mais utile)
    render_global_uploader()

    mode = st.radio(
        "🎯 Objectif d'audit",
        ["Audit interne", "Audit officiel / Pré-certification"],
        horizontal=True,
        index=0 if st.session_state.get("audit_mode", "interne") == "interne" else 1,
        key="audit_mode_choice",
    )
    st.session_state.audit_mode = "interne" if mode == "Audit interne" else "officiel"
    audit_mode = st.session_state.audit_mode

    ISO_QUESTIONS = ISO_QUESTIONS_INTERNE if audit_mode == "interne" else {**ISO_QUESTIONS_MANAGEMENT, **ISO_QUESTIONS_INTERNE}

    client_name_input = st.text_input(
        "🏢 Nom du client pour cet audit",
        placeholder="Exemple : D&A, CACEIS, Banque XYZ...",
        key="client_name",
    ).strip()

    if client_name_input:
        st.success(f"Client sélectionné : **{client_name_input}**")
    else:
        st.info("➡️ Indiquez le nom du client pour activer l’import des documents.")
        st.button("⬅️ Retour à l’accueil", key="iso_back_home", on_click=lambda: go("home"))
        st.stop()

    def extract_text_from_pdf(file):
        text = ""
        pdf = fitz.open(stream=file.read(), filetype="pdf")
        for page in pdf:
            text += page.get_text()
        return text

    def extract_text_from_docx(file):
        d = docx.Document(file)
        return "\n".join(p.text for p in d.paragraphs)

    def detect_client_name_with_ai(text):
        preview_text = text[:1500]
        prompt = f"""
Tu es un expert en audit ISO 27001.
Voici un extrait du début d'un document d'audit :
---
{preview_text}
---
À partir de cet extrait, identifie uniquement le NOM de l'organisation ou du client.
IMPORTANT :
- Ne donne pas d'explication.
- Ne réponds que par le nom détecté.
- Si tu n'es pas sûr, réponds exactement "Inconnu".
"""
        client = get_openai_client()
        if client is None:
            return "Inconnu"
        try:
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            return (response.choices[0].message.content or "").strip()
        except Exception:
            return "Inconnu"

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

    st.subheader("📂 Importer documents du client (spécifique à ISO)")
    st.markdown(
        "Analysez vos documents (**politiques, procédures, rapports**) pour pré-remplir le questionnaire, "
        "générez une **Gap Analysis** et un **rapport Word** prêt à partager."
    )

    with st.expander("📎 Exemples de documents à tester (téléchargeables)"):
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "⬇️ Télécharger un exemple TXT",
                data=make_example_txt(),
                file_name="exemple_client.txt",
                mime="text/plain",
                use_container_width=True,
                key="iso_example_txt"
            )
        with col_b:
            st.download_button(
                "⬇️ Télécharger un exemple DOCX",
                data=make_example_docx(),
                file_name="exemple_procedure.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="iso_example_docx"
            )

    uploaded_files = st.file_uploader(
        "Formats acceptés : PDF, DOCX, TXT — limite 200 Mo par fichier.",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="iso_uploader"
    )

    # On combine textes des uploads ISO + uploader global
    documents_text = get_uploaded_docs_text()
    detected_client_names = set()

    # Ajoute le texte des fichiers uploadés ici (spécifique ISO)
    if uploaded_files:
        for file in uploaded_files:
            if file.name.lower().endswith(".pdf"):
                text = extract_text_from_pdf(file)
            elif file.name.lower().endswith(".docx"):
                text = extract_text_from_docx(file)
            elif file.name.lower().endswith(".txt"):
                text = file.read().decode("utf-8", errors="ignore")
            else:
                text = ""
            documents_text += "\n" + text

            detected_name = detect_client_name_with_ai(text)
            if detected_name and detected_name != "Inconnu":
                detected_client_names.add(detected_name)

        if len(detected_client_names) > 1:
            st.error(
                f"⚠️ Plusieurs clients détectés dans les documents : "
                f"{', '.join(detected_client_names)}"
            )
            st.stop()

        mismatch = detected_client_names and not any(
            client_name_input.lower() in name.lower() for name in detected_client_names
        )
        if mismatch:
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
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="iso_example_correct_docx"
            )
            st.stop()

    responses = {}
    if documents_text.strip():
        client = get_openai_client()
        if client is None:
            st.warning("ℹ️ Aucune clé OpenAI détectée — l’analyse IA des documents est désactivée.")
        else:
            st.info("📡 Analyse IA en cours...")
            responses = _ai_prefill_iso_by_domain(documents_text, ISO_QUESTIONS)
            st.success("✅ Questionnaire pré-rempli par l'IA.")

    if responses:
        gap_analysis = analyse_responses(responses, nom_client=client_name_input)
        save_gap_analysis(gap_analysis, nom_client=client_name_input)

        df_gap = pd.DataFrame(gap_analysis)

        if not df_gap.empty:
            st.subheader("📊 Gap Analysis (vue interactive)")
            domaines = ["Tous"] + sorted(df_gap["Domaine ISO 27001"].unique())
            priorites = ["Toutes"] + sorted(df_gap["Priorité"].unique())

            col1, col2 = st.columns(2)
            with col1:
                filtre_domaine = st.selectbox("📌 Filtrer par domaine", domaines, key="iso_filter_domain")
            with col2:
                filtre_priorite = st.selectbox("⚡ Filtrer par priorité", priorites, key="iso_filter_priority")

            df_filtre = df_gap.copy()
            if filtre_domaine != "Tous":
                df_filtre = df_filtre[df_filtre["Domaine ISO 27001"] == filtre_domaine]
            if filtre_priorite != "Toutes":
                df_filtre = df_filtre[df_filtre["Priorité"] == filtre_priorite]

            st.dataframe(df_filtre, use_container_width=True)

            export_gap = OUTPUT_DIR / "gap_analysis_ui.xlsx"
            df_filtre.to_excel(export_gap, index=False)
            st.download_button(
                "📥 Télécharger Gap Analysis (Excel)",
                data=open(export_gap, "rb").read(),
                file_name="gap_analysis.xlsx",
                key="iso_export_gap"
            )

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

    # Formulaire interactif final
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

                key_suffix = f"{domain}_{clause}_{hash(question_text)}"

                if isinstance(answer_data, dict):
                    reponse_simple = answer_data.get("Réponse", "")
                    new_answer = st.text_area(
                        question_display,
                        value=reponse_simple,
                        key=f"ta_{key_suffix}"
                    )
                    final_responses[domain][question_text] = {**answer_data, "Réponse": new_answer}
                else:
                    new_answer = st.text_area(
                        question_display,
                        value=answer_data,
                        key=f"tb_{key_suffix}"
                    )
                    final_responses[domain][question_text] = new_answer

        submitted = st.form_submit_button("📥 Générer l'analyse et le rapport", key="iso_submit")

    if submitted:
        gap_analysis = analyse_responses(final_responses, nom_client=client_name_input)
        save_gap_analysis(gap_analysis, nom_client=client_name_input)

        report_path = generate_audit_report()

        st.success("✅ Rapport généré avec succès !")
        st.download_button(
            "📄 Télécharger rapport Word",
            data=open(report_path, "rb").read(),
            file_name=Path(report_path).name,
            key="iso_download_report"
        )
        st.download_button(
            "📊 Télécharger Gap Analysis",
            data=open(OUTPUT_DIR / "gap_analysis.xlsx", "rb").read(),
            file_name="gap_analysis.xlsx",
            key="iso_download_gap"
        )

        action_client = get_openai_client()
        if action_client is None:
            st.warning("ℹ️ Pas de clé OpenAI — génération automatique du plan d’actions désactivée.")
        else:
            action_plan = generate_action_plan_from_ai(gap_analysis, nom_client=client_name_input)
            save_action_plan_to_excel(action_plan)

            st.subheader("📅 Plan d’actions recommandé")
            df_plan = pd.DataFrame(action_plan)
            if not df_plan.empty:
                st.dataframe(df_plan, use_container_width=True)
                st.download_button(
                    "📥 Télécharger le plan d’actions (Excel)",
                    data=open(OUTPUT_DIR / "action_plan.xlsx", "rb").read(),
                    file_name="plan_actions.xlsx",
                    key="iso_download_plan"
                )
            else:
                st.info("✅ Aucun plan d’action nécessaire, tout est conforme.")

    st.divider()
    st.button("⬅️ Retour à l’accueil", key="iso_home", on_click=lambda: go("home"))

# =========================================================
#                       DISPATCH
# =========================================================
page = st.session_state.get("route", "home")

if page == "home":
    render_home()
elif page == "anssi_hygiene":
    render_anssi_hygiene()
elif page == "iso27001":
    render_iso27001()
else:
    st.session_state["route"] = "home"
    render_home()
