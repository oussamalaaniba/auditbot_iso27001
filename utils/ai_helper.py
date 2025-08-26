from typing import List, Dict, Any, Tuple
import os, io, math, json, hashlib
from pathlib import Path
import fitz  # PyMuPDF
import docx
import numpy as np
from openai import OpenAI

EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")
CHAT_MODEL  = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _read_pdf_bytes(b: bytes) -> List[Tuple[str, int, str]]:
    """Retourne [(doc_name, page_no, text)] pour un PDF."""
    out = []
    with fitz.open(stream=b, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            txt = page.get_text("text")
            if txt and txt.strip():
                out.append(("document.pdf", i, txt))
    return out

def _read_docx_bytes(b: bytes) -> List[Tuple[str, int, str]]:
    """DOCX -> [(doc_name, 1, text_chunk)] (pas de pagination fine)"""
    f = io.BytesIO(b)
    d = docx.Document(f)
    paras = []
    for p in d.paragraphs:
        t = p.text.strip()
        if t:
            paras.append(t)
    text = "\n".join(paras)
    # on simule des "pages" par découpage
    chunks = []
    step = 1800  # ~1200-1500 tokens char proxy, ajuste si besoin
    for idx in range(0, len(text), step):
        chunks.append(("document.docx", 1 + idx // step, text[idx:idx+step]))
    return chunks

def _read_txt_bytes(b: bytes) -> List[Tuple[str, int, str]]:
    t = b.decode("utf-8", errors="ignore")
    chunks = []
    step = 1800
    for idx in range(0, len(t), step):
        chunks.append(("document.txt", 1 + idx // step, t[idx:idx+step]))
    return chunks

def _chunk_sources(uploaded_files: List[Any]) -> List[Dict[str, Any]]:
    """uploaded_files = st.file_uploader(..., accept_multiple_files=True)"""
    all_chunks = []
    for f in uploaded_files:
        name = f.name
        b = f.getvalue()
        if name.lower().endswith(".pdf"):
            parts = _read_pdf_bytes(b)
        elif name.lower().endswith(".docx"):
            parts = _read_docx_bytes(b)
        elif name.lower().endswith(".txt"):
            parts = _read_txt_bytes(b)
        else:
            # ignore autres formats ici
            continue
        for (doc_name, page_no, text) in parts:
            all_chunks.append({
                "doc": name or doc_name,
                "page": page_no,
                "text": text
            })
    return all_chunks

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if not np.any(a) or not np.any(b):
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def build_vector_index(uploaded_files: List[Any]) -> Dict[str, Any]:
    """
    Construit un index local: { 'chunks': [...], 'embeddings': np.array, 'meta': [...] }
    À stocker dans st.session_state pour réutiliser.
    """
    client = OpenAI()
    chunks = _chunk_sources(uploaded_files)
    if not chunks:
        return {"chunks": [], "embeddings": np.zeros((0, 3072)), "meta": []}

    # Embeddings
    texts = [c["text"][:8000] for c in chunks]  # guardrail
    embs = []
    # batch simple
    for i in range(0, len(texts), 100):
        batch = texts[i:i+100]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        for d in resp.data:
            embs.append(np.array(d.embedding, dtype=np.float32))
    E = np.vstack(embs)
    return {
        "chunks": chunks,
        "embeddings": E,
        "meta": [{"doc": c["doc"], "page": c["page"]} for c in chunks]
    }

def retrieve_topk(index: Dict[str, Any], query: str, k: int = 6) -> List[Dict[str, Any]]:
    if not index or len(index.get("chunks", [])) == 0:
        return []
    client = OpenAI()
    q_emb = client.embeddings.create(model=EMBED_MODEL, input=[query]).data[0].embedding
    q = np.array(q_emb, dtype=np.float32)
    sims = [(_cosine_sim(q, e), j) for j, e in enumerate(index["embeddings"])]
    sims.sort(reverse=True)
    out = []
    for _, j in sims[:k]:
        c = index["chunks"][j]
        out.append({
            "doc": c["doc"],
            "page": c["page"],
            "text": c["text"]
        })
    return out

def propose_anssi_answer(requirement: str, question: str, index: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retourne: { 'status': str, 'justification': str, 'citations': [ {'doc':..., 'page':...} ] }
    """
    top = retrieve_topk(index, requirement + " " + question, k=6)
    context = "\n\n".join([f"[{t['doc']} – p.{t['page']}] {t['text'][:1000]}" for t in top])

    system = (
        "Tu es un consultant cybersécurité senior spécialisé en conformité ANSSI.\n"
        "À partir du contexte documentaire fourni, évalue la conformité à l’exigence donnée.\n"
        "Choisis EXACTEMENT UN statut dans {Conforme, Partiellement conforme, Non conforme, Non applicable}.\n"
        "Donne une justification courte et professionnelle (3-6 lignes) s’appuyant sur les passages cités.\n"
        "Inclue des citations sous forme (doc, page) pertinentes."
    )

    user = (
        f"EXIGENCE: {requirement}\n"
        f"QUESTION: {question}\n\n"
        f"CONTEXTE:\n{context}\n\n"
        "Réponds en JSON compact avec les clés: status, justification, citations (liste d’objets {doc,page})."
    )

    client = OpenAI()
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role":"system", "content":system}, {"role":"user","content":user}],
        temperature=0.2
    )
    content = resp.choices[0].message.content.strip()
    # tentative de parse
    try:
        data = json.loads(content)
        # garde-fous
        status = str(data.get("status", "")).strip()
        if status not in {"Conforme", "Partiellement conforme", "Non conforme", "Non applicable"}:
            status = "Partiellement conforme" if status else "Non évalué"
        justif = str(data.get("justification", "")).strip()
        cits = data.get("citations", [])
        if not isinstance(cits, list):
            cits = []
        # filtre doc/page
        citations = []
        for c in cits:
            d = str(c.get("doc", "")).strip()
            p = int(c.get("page", 0)) if str(c.get("page","")).isdigit() else None
            if d and p:
                citations.append({"doc": d, "page": p})
        return {"status": status, "justification": justif, "citations": citations}
    except Exception:
        # fallback simple
        return {"status": "Non évalué", "justification": content[:800], "citations": []}
