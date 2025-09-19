\
import os
import json
import time
from statistics import mean, median

from rouge_score import rouge_scorer
from app.rag import RAGPipeline, RAW_DIR

DATASET = os.path.join(os.path.dirname(__file__), "dataset.jsonl")

def ensure_docs_from_dataset():
    # 보장을 위해 dataset의 doc_file이 없으면 dataset의 내용을 raw에 쓴다
    with open(DATASET, "r", encoding="utf-8") as f:
        lines = [json.loads(x) for x in f if x.strip()]
    for item in lines:
        path = os.path.join(RAW_DIR, item["doc_file"])
        if not os.path.exists(path):
            # doc_file 이름과 동일 텍스트를 dataset에 추가했다고 가정하지 않으므로 skip
            # 본 PoC에서는 이미 저장된 샘플 3종이 있으므로 pass
            pass
    return lines

def compute_keywords(text, top_k=8):
    # 매우 단순한 키워드 추출 (빈도 기준, stopwords 미적용)
    import re
    words = re.findall(r"[A-Za-z0-9가-힣\.-]{3,}", text.lower())
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    kws = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [k for k, _ in kws]

def main():
    ds = ensure_docs_from_dataset()
    pipe = RAGPipeline()
    # 인덱스 보장
    pipe.ingest([RAW_DIR])

    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)

    f1s = []
    lat_ms = []
    covs = []

    samples = []

    for item in ds:
        q = item["question"]
        ref = item["reference_summary"]

        t0 = time.time()
        out = pipe.ask(q, k=4, max_words=200)
        t1 = time.time()

        pred = out.get("answer", "")
        score = scorer.score(ref, pred)["rougeL"].fmeasure
        f1s.append(score)
        lat_ms.append((t1 - t0) * 1000)

        # 간단 키워드 커버리지
        rk = set(compute_keywords(ref))
        pk = set(compute_keywords(pred))
        cov = len(rk & pk) / max(1, len(rk))
        covs.append(cov)

        samples.append({
            "id": item["id"],
            "question": q,
            "rougeL_f1": round(score, 3),
            "coverage": round(cov, 3),
            "latency_ms": int(lat_ms[-1]),
            "answer_preview": pred[:240].replace("\n", " ")
        })

    print(f"Total: {len(ds)}")
    print(f"ROUGE-L F1: mean={mean(f1s):.3f}, median={median(f1s):.3f}")
    print(f"Coverage:   mean={mean(covs):.3f}, median={median(covs):.3f}")
    print(f"Latency(ms): mean={mean(lat_ms):.1f}, p50={sorted(lat_ms)[len(lat_ms)//2]:.1f}, max={max(lat_ms):.1f}")
    print("\nSamples:")
    for s in samples:
        print(json.dumps(s, ensure_ascii=False))

if __name__ == "__main__":
    main()
