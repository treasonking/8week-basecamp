# RAG 요약봇 PoC — 보안 리포트 요약 자동화 (프롬프트 · 평가셋 포함)

이 PoC는 **보안 리포트 문서**(예: 취약점 공지, 대응 가이드)를 수집·분할·임베딩하고,
질문/요약 요청 시 **관련 근거 문맥**을 검색해 **근거 기반 요약**을 생성합니다.
- 검색/저장은 **ChromaDB(로컬)** + **Sentence-Transformers 임베딩**
- 요약 모델은 **클라우드(OPENAI/GEMINI)** 또는 **로컬(Ollama)**, 없으면 **오프라인 요약(sumy)** 로 자동 폴백
- **평가셋(JSONL)** 과 **ROUGE-L 지표 평가 스크립트** 포함

> OS는 Windows 기준 PowerShell 명령을 우선 표기 (WSL/Linux도 동일 구조).

---

## 1) 빠른 시작

```powershell
# 1. 프로젝트 진입
cd rag-summary-bot

# 2. 가상환경 생성/활성화 (Windows PowerShell)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. 필수 패키지 설치
pip install -U pip
pip install -r requirements.txt

# 4. (선택) API 키 설정
#   - OpenAI:   setx OPENAI_API_KEY "sk-..."
#   - Gemini:    setx GEMINI_API_KEY "AIza..."
#   - Ollama:    로컬에서 모델(예: llama3.1, mistral)을 받아서 ollama 서버 실행 필요

# 5. 샘플 문서 인덱싱
python -m app.rag --ingest .\data\raw

# 6. 서버 실행
uvicorn app.main:app --reload --port 8000
```

이후 테스트:
```powershell
# 요약 질문 (PowerShell)
$body = @{ question = "Log4Shell 대응 요약(핵심 위험/영향/완화)"; k = 2; max_words = 200 } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing `
  -Uri "http://127.0.0.1:8000/ask" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body | % Content | Write-Output
```

---

## 2) 폴더 구조

```
rag-summary-bot/
├─ app/
│  ├─ main.py                 # FastAPI 엔드포인트(/ingest, /ask)
│  ├─ rag.py                  # 인덱싱/검색/요약 파이프라인, CLI 지원
│  ├─ prompts/
│  │  ├─ system.txt
│  │  └─ summarizer.txt
│  └─ eval/
│     ├─ dataset.jsonl        # 평가셋 (테스트 문항/정답 요약)
│     └─ run_eval.py          # ROUGE-L 평가 스크립트
├─ data/
│  ├─ raw/                    # 원문(샘플 3종 포함)
│  ├─ chroma/                 # ChromaDB(생성됨)
│  ├─ chunks/                 # 분할 텍스트(생성됨)
│  └─ meta.json               # 문서 메타(생성됨)
├─ .env.example               # API 키 샘플
├─ requirements.txt
└─ README.md
```

---

## 3) 사용법 (자주 하는 작업)

### 3.1 새 문서 넣기(인덱싱)
```powershell
# data/raw 아래에 .pdf/.txt/.md 파일 복사 후:
python -m app.rag --ingest .\data\raw
```
- PDF는 자동 텍스트 추출(pypdf)
- 텍스트 분할: 1,200자, 200자 오버랩(한국어/영어 혼합 안전)

### 3.2 질문/요약 API
- `POST /ask` : { question, k?, max_words? } → { answer, sources[] }
- `POST /ingest` : { paths[] } → { added_chunks, docs }

```powershell
$ask = @{ question = "xz 백도어(CVE-2024-3094) 핵심 영향·완화"; k = 4; max_words = 160 } | ConvertTo-Json
Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/ask" -Method POST -ContentType "application/json" -Body $ask | % Content
```

### 3.3 CLI 모드(서버 없이 바로 실행)
```powershell
# 인덱싱
python -m app.rag --ingest .\data\raw
# 질문
python -m app.rag --ask "MOVEit SQLi 핵심 요약(영향·타임라인·권고)"
```

### 3.2 간단 실행법
@'
# RAG Summary Bot (Security Report Summarizer)

## Quickstart (Windows PowerShell)
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt

# Ingest sample docs
python -m app.rag --ingest .\data\raw

# Run API
uvicorn app.main:app --reload --port 8000
Ask API
POST /ask
body: {"question":"...", "k":2, "max_words":160}

Set OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_MODEL as needed.
'@ | Out-File README.md -Encoding utf8 -NoNewline'

## 3) (선택) 정확한 의존성 고정
이미 `requirements.txt`가 있겠지만, 현재 venv 상태를 저장하려면:
```powershell
.\.venv\Scripts\python.exe -m pip freeze | Out-File requirements.txt -Encoding utf8


---

## 4) 요약 모델 우선순위 & 설정

1. **OpenAI** (`OPENAI_API_KEY` 있으면 자동 사용, 모델 기본: `gpt-4o-mini`)
2. **Gemini** (`GEMINI_API_KEY` 있으면 `gemini-1.5-flash` 사용)
3. **Ollama** (로컬 http://127.0.0.1:11434, 모델명 기본 `llama3.1`)
4. **오프라인(sumy LexRank)** — 위 1~3이 모두 없을 때 폴백

환경변수는 한 가지만 있어도 됩니다. 우선순위대로 선택됩니다.

---

## 5) 프롬프트

- `app/prompts/system.txt`: 보안 분석가 역할, 한국어/영어 혼용 안전, 인용/근거, 금칙어 등
- `app/prompts/summarizer.txt`: “위험/영향/악용 여부/대상/완화/조치” 6요소를 **글머리표**로 정리하는 규칙

필요시 자유롭게 수정하세요.

---

## 6) 평가(ROUGE-L F1)

```powershell
python -m app.eval.run_eval
```
- `app/eval/dataset.jsonl` 의 각 항목에 대해 요약 생성 → **ROUGE-L F1** 계산
- 출력: 개수, 평균/중앙값, 지연시간(평균/분위/최대), 샘플 예시

> 참고: ROUGE는 “문장 겹침” 기반이라 **정확한 사실성**을 완벽히 보장하지 않습니다.
추가로 “키워드 커버리지” 같은 보조 지표를 함께 출력합니다.

---

## 7) 흔한 오류 대처

- **SentenceTransformer 모델 다운로드 지연**: 최초 1회만 다운로드됩니다.
- **PDF 추출이 비어있음**: 스캔본/이미지 PDF는 OCR이 필요합니다(본 PoC는 텍스트 PDF 기준).
- **Ollama 연결 실패**: Ollama 서버 실행/모델 설치 확인(`ollama run llama3.1` 등).

---

## 8) 라이선스

학습/포트폴리오 용도. 상용/배포 시 각 라이브러리의 라이선스를 확인하세요.
