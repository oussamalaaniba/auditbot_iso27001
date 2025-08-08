import os
import json
from dotenv import load_dotenv
from openai import OpenAI

# Charger la clé API depuis .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyse_documents_with_ai(documents_text, questions_dict, debug=False):
    """
    Utilise l'IA pour analyser les documents et fournir :
    - Réponse
    - Statut ISO 27001
    - Recommandation contextualisée
    - Priorité
    - Échéance
    - Question complémentaire
    """

    # Sécurité : vérifier que les documents ne sont pas vides
    if not documents_text.strip():
        print("❌ Aucun texte exploitable trouvé dans les documents.")
        return {}

    # Création du prompt
    prompt = f"""
Tu es un consultant cybersécurité expert ISO 27001 et ISO 27002.

Voici les documents du client :
{documents_text[:12000]}

Pour chaque question fournie ci-dessous :
1. Réponds uniquement selon les documents (sinon mets "Non trouvé").
2. Indique le statut : ✅ Conforme / ⚠️ Partiellement conforme / ❌ Non conforme.
3. Donne une justification basée sur les preuves.
4. Propose une recommandation claire et actionnable.
5. Donne une priorité : Haute / Moyenne / Basse.
6. Donne une échéance réaliste (JJ/MM/AAAA).
7. Ajoute éventuellement une question complémentaire.

⚠️ Règles importantes :
- Réponds **uniquement** en JSON valide
- Aucun texte avant ou après le JSON
- Tous les champs doivent être présents

Questions :
{questions_dict}

Format JSON attendu :
{{
  "Nom du domaine": {{
    "Texte exact de la question": {{
      "Réponse": "...",
      "Statut": "...",
      "Justification": "...",
      "Recommandation": "...",
      "Priorité": "...",
      "Échéance": "...",
      "Question complémentaire": "..."
    }}
  }}
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        raw_response = response.choices[0].message.content.strip()

        # Mode debug : afficher la réponse brute
        if debug:
            print("=== RAW AI RESPONSE ===")
            print(raw_response)

        # Parsing JSON sécurisé
        try:
            ai_result = json.loads(raw_response)
            return ai_result
        except json.JSONDecodeError as e:
            print("❌ Erreur parsing JSON IA :", e)
            if debug:
                print("Réponse brute pour analyse :")
                print(raw_response)
            return {}

    except Exception as e:
        print(f"❌ Erreur lors de l'appel à l'IA : {e}")
        return {}

