\
import os
import re
import json
import time
import argparse
from typing import List, Dict, Any, Tuple

import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import nltk
from nltk.tokenize import sent_tokenize

from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer

from dotenv import load_dotenv

from rouge_score import rouge_scorer

import requests

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

# Ensure NLTK data
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
META_PATH = os.path.join(DATA_DIR, "meta.json")

PROMPTS_DIR = os.path.join(BASE_DIR, "app", "prompts")
SYSTEM_PATH = os.path.join(PROMPTS_DIR, "system.txt")
SUMMARIZER_PATH = os.path.join(PROMPTS_DIR, "summarizer.txt")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)

load_dotenv(override=False)


def load_text_from_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".txt", ".md"]:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    if ext == ".pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf가 설치되어 있지 않습니다. requirements.txt를 확인하세요.")
        reader = PdfReader(path)
        content = []
        for page in reader.pages:
            try:
                content.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(content)
    raise ValueError(f"지원하지 않는 파일 유형: {ext}")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> List[str]:
    text = re.sub(r"\s+\n", "\n", text.strip())
    if not text:
        return []
    try:
        sentences = sent_tokenize(text)  # language auto
    except Exception:
        sentences = re.split(r"(?<=[.!?\\n])\\s+", text)

    chunks = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 <= max_chars:
            buf += (" " if buf else "") + s
        else:
            if buf:
                chunks.append(buf)
            # start new with overlap from previous
            if overlap > 0 and chunks:
                tail = chunks[-1][-overlap:]
                buf = tail + " " + s
            else:
                buf = s
    if buf:
        chunks.append(buf)
    return chunks


class STEmbeddingFunction:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def name(self) -> str:
        return self.model_name

    def _encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        vecs = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return [v.tolist() for v in vecs]

    def __call__(self, input):
        return self._encode(input)

    def embed_documents(self, documents):
        return self._encode(documents)

    def embed_query(self, input):
        # 쿼리도 "벡터들의 리스트" 모양을 기대하므로, 단일 쿼리도 리스트로 감싸서 인코딩
        if isinstance(input, list):
            input = " ".join(str(x) for x in input)
        return self._encode([input])





def get_prompts() -> Tuple[str, str]:
    with open(SYSTEM_PATH, "r", encoding="utf-8") as f:
        system = f.read().strip()
    with open(SUMMARIZER_PATH, "r", encoding="utf-8") as f:
        summarizer = f.read().strip()
    return system, summarizer


class Summarizer:
    """
    선택적 LLM(OpenAI/Gemini/Ollama) → 없으면 sumy LexRank 폴백
    """
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.use_openai = bool(self.openai_key and OpenAI is not None)
        self.use_gemini = bool(self.gemini_key and genai is not None)
        self.use_ollama = False

        if self.use_openai:
            try:
                self._openai = OpenAI(api_key=self.openai_key)
            except Exception:
                self.use_openai = False

        if self.use_gemini:
            try:
                genai.configure(api_key=self.gemini_key)
                self._gemini = genai.GenerativeModel("gemini-1.5-flash")
            except Exception:
                self.use_gemini = False

        # Ollama is optional via HTTP
        try:
            # quick health check
            r = requests.get("http://127.0.0.1:11434/")
            if r.status_code in (200, 404):
                self.use_ollama = True
        except Exception:
            self.use_ollama = False

    def summarize(self, system_prompt: str, user_prompt: str, max_words: int = 200) -> str:
        # Normalize user prompt to include max words guidance
        user_prompt = user_prompt + f"\\n\\n[길이 지시] 최대 {max_words} 단어(한국어는 문장 10~14개 이내)."

        if self.use_openai:
            try:
                resp = self._openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                print("[OpenAI error]", e)
                # fallback chain
                pass

        if self.use_gemini:
            try:
                resp = self._gemini.generate_content(system_prompt + "\\n\\n" + user_prompt)
                return resp.text.strip()
            except Exception:
                pass

        if self.use_ollama:
            try:
                payload = {
                    "model": self.ollama_model,
                    "prompt": f"System: {system_prompt}\\n\\nUser: {user_prompt}\\nAssistant:",
                    "stream": False,
                    "options": {"temperature": 0.2}
                }
                r = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=120)
                if r.ok:
                    out = r.json().get("response", "").strip()
                    if out:
                        return out
            except Exception:
                pass

                # ---------- Offline fallback (no konlpy / no sumy) ----------
        import re
        def _extract_context(u: str):
            m = re.search(r"\[문맥\](.*)\[질문/요청\]", u, flags=re.S)
            return (m.group(1).strip() if m else u)

        def _simple_sentences_ko_en(text: str):
            parts = re.split(r"(?<=[\.\?\!])\s+|[\r\n]+", text)
            return [p.strip() for p in parts if p.strip()]

        ctx_only = _extract_context(user_prompt)
        sents = _simple_sentences_ko_en(ctx_only)
        picked = sents[:12]

        labels = ["위험 요약","영향 범위","악용 여부/지표","영향 대상/버전","완화/우회 방안","권고 조치(우선순위)"]
        while len(picked) < len(labels): picked.append("자료 불충분")

        out = "\n".join(f"- {lab}: {picked[i]}" for i, lab in enumerate(labels))
        return out if out.strip() else (ctx_only[:800] + "...")




class RAGPipeline:
    def __init__(self):
        embed_fn = STEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.client.get_or_create_collection(name="docs", embedding_function=embed_fn)
        self.summarizer = Summarizer()
        self.system_prompt, self.summarizer_prompt = get_prompts()

    def _save_meta(self, meta: Dict[str, Any]):
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _load_meta(self) -> Dict[str, Any]:
        if not os.path.exists(META_PATH):
            return {"docs": {}}
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def ingest(self, paths: List[str]) -> Tuple[int, int]:
        meta = self._load_meta()
        docs_meta = meta.get("docs", {})

        added_chunks = 0
        doc_count = 0

        for path in paths:
            if os.path.isdir(path):
                files = [os.path.join(path, x) for x in os.listdir(path) if os.path.isfile(os.path.join(path, x))]
            else:
                files = [path]

            for fpath in files:
                ext = os.path.splitext(fpath)[1].lower()
                if ext not in (".txt", ".md", ".pdf"):
                    continue

                doc_id = os.path.basename(fpath)
                try:
                    text = load_text_from_file(fpath)
                except Exception as e:
                    print(f"[WARN] {doc_id}: 로드 실패 {e}")
                    continue

                chunks = chunk_text(text, max_chars=1200, overlap=200)
                if not chunks:
                    print(f"[WARN] {doc_id}: 추출된 텍스트/청크 없음")
                    continue

                # remove previous chunks of this doc (if reingesting)
                existing = self.collection.get(where={"doc_id": doc_id})
                if existing and existing.get("ids"):
                    self.collection.delete(ids=existing["ids"])

                # add chunks
                ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
                metas = [{"doc_id": doc_id, "chunk_index": i, "source": fpath} for i in range(len(chunks))]
                self.collection.add(ids=ids, metadatas=metas, documents=chunks)

                # save chunks to disk for debugging
                out_dir = os.path.join(CHUNKS_DIR, doc_id)
                os.makedirs(out_dir, exist_ok=True)
                for i, c in enumerate(chunks):
                    with open(os.path.join(out_dir, f"{i:04d}.txt"), "w", encoding="utf-8") as cf:
                        cf.write(c)

                docs_meta[doc_id] = {"source": fpath, "chunks": len(chunks)}
                added_chunks += len(chunks)
                doc_count += 1
                print(f"[OK] {doc_id}: {len(chunks)} chunks")

        meta["docs"] = docs_meta
        self._save_meta(meta)
        return added_chunks, doc_count

    def retrieve(self, query: str, k: int = 4) -> Dict[str, Any]:
        res = self.collection.query(query_texts=[query], n_results=k)
        return res

    def build_prompt(self, question: str, retrieved: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        docs = (retrieved.get("documents") or [[]])[0]
        metas = (retrieved.get("metadatas") or [[]])[0]
        ids = (retrieved.get("ids") or [[]])[0]

        # merge contexts
        contexts = []
        cited = []
        for i, (d, m, _id) in enumerate(zip(docs, metas, ids)):
            contexts.append(f"[{i+1}] {d}")
            cited.append({
                "rank": i + 1,
                "doc_id": m.get("doc_id"),
                "chunk_index": m.get("chunk_index"),
                "source": m.get("source")
            })

        ctx = "\\n\\n".join(contexts)
        user_prompt = self.summarizer_prompt.replace("{{CONTEXT}}", ctx).replace("{{QUESTION}}", question)
        return user_prompt, cited

    def ask(self, question: str, k: int = 4, max_words: int = 200) -> Dict[str, Any]:
        t0 = time.time()
        retrieved = self.retrieve(question, k=k)
        user_prompt, cited = self.build_prompt(question, retrieved)
        answer = self.summarizer.summarize(self.system_prompt, user_prompt, max_words=max_words)
        t1 = time.time()
        return {
            "answer": answer,
            "sources": cited,
            "latency_ms": int((t1 - t0) * 1000)
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", nargs="*", help="경로 목록(.txt/.md/.pdf 폴더 또는 파일)")
    parser.add_argument("--ask", type=str, help="질문/요약 요청")
    parser.add_argument("--k", type=int, default=4, help="검색 상위 k")
    parser.add_argument("--max_words", type=int, default=200, help="요약 최대 단어(가이드)")
    args = parser.parse_args()

    pipe = RAGPipeline()

    if args.ingest is not None:
        paths = args.ingest if args.ingest else [RAW_DIR]
        added, docs = pipe.ingest(paths)
        print(json.dumps({"added_chunks": added, "docs": docs}, ensure_ascii=False))
        return

    if args.ask:
        out = pipe.ask(args.ask, k=args.k, max_words=args.max_words)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
