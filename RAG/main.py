"""KANT NEXT DevDesk RAG. 이 파일의 빈칸만 작성하세요."""
from qdrant_client import models

import support
import re

def todo(message):
    raise NotImplementedError(message)


# 필수 1. 문서를 저장하고 현행 자료만 검색하기

# 원본 문서를 검색에 사용할 문단 조각으로 정리하는 함수 
def prepare_chunks(documents):
    chunks = []
    for document in documents:
        seen = set()
        number = 0
        for paragraph in document["paragraphs"]:
            text = " ".join(paragraph.split())
            if not text or text == "KANT NEXT | 내부 문서" or text in seen:
                continue
            seen.add(text)
            
            chunk = {
                "document_id": document["document_id"],
                "title": document["title"],
                "category": document["category"],
                "status": document["status"],
                "source": document["source"],
                "file": document["file"],
                "chunk_id": f"{document['document_id']}:{number}", 
                "text": text,
            }
            chunks.append(chunk)
            number += 1
    # 이유: 문단을 유지하는 이유와 보존해야 할 메타데이터를 한두 줄로 적으세요.
    # 문단 단위를 유지하면 관련 내용이 함께 남아 검색과 답변에 필요한 의미를 보존할 수 없습니다.
    # 출처 추적과 검색 필터링을 위해 document_id, title, category, status, source를 보존합니다.
    return chunks

# 문단 조각을 벡터로 변환하고, Qdrant에 저장해 검색할 준비를 하는 함수 
def build_index(chunks, embedder):
    texts = ["passage: " + row["title"] + "\n" + row["text"] for row in chunks]
    
    # vectors = todo("texts를 정규화된 문서 벡터로 바꾸세요.")
    # 각 문서를 벡터로 변환하고, 벡터의 길이(크기)를 1로 정규화
    vectors = embedder.encode(texts, normalize_embeddings=True)
    client = support.empty_store(len(vectors[0]))
    points = []
    for i, (row, vector) in enumerate(zip(chunks, vectors, strict=True)):

        
        
        # Qdrant에 저장할 데이터 한 건을 만든다. 
        point = models.PointStruct(
            id=i,   # 반복문의 순번을 저장 ID로 사용
            vector=list(vector),    # 문서 벡터를 리스트로 변환해 넣는다.
            payload=row,    # payload=row: 청크 본문과 문서 정보 5개, chunk_id를 함께 저장
        )
        points.append(point)
    client.upsert(collection_name="devdesk", points=points, wait=True)
    return client

# 질문과 의미가 비슷한 청크를 Qdrant에서 찾는 함수
# 현행 문서이면서 지정한 분류에 속한 자료만 검색 
def search(client, embedder, question, category, top_k=2):
    if type(top_k) is not int or not 1 <= top_k <= 5:
        raise ValueError("top_k는 1~5의 정수여야 합니다.")
    vector = embedder.encode(["query: " + question], normalize_embeddings=True)[0]
    
    # 현행 문서이면서 지정한 분류에 해당하는 자료만 검색하도록 필터를 만든다. 
    scope = models.Filter(
        # 아래 조건을 모두 만족해야 한다.
        must=[
            models.FieldCondition(
                key="status",   # 문서의 상태를 확인
                match=models.MatchValue(value="current"),   # 현행 문서만 선택
            ),
            models.FieldCondition(
                key="category", # 문서의 분류를 확인
                match=models.MatchValue(value=category),   # 전달받은 분류와 같은 문서만 선택
            ),
        ]
    )
    hits = client.query_points(collection_name="devdesk", query=list(vector),
                               query_filter=scope, limit=top_k, with_payload=True).points
    return [{**hit.payload, "score": hit.score} for hit in hits]


# 필수 2. 별칭 검색을 개선하고 답변을 비교하기

# 질문에 들어 있는 별칭을 정식 명칭으로 바꿔 검색하기 좋은 질문으로 만드는 함수
def rewrite_query(question, aliases):
    rewritten = question
    for alias, formal_name in aliases.items():
        # 현재 문자열에서 alias와 일치하는 부분을 foraml_name으로 바꿈.
        rewritten = rewritten.replace(alias, formal_name)
    return rewritten

# 검색한 문서를 근거로 답변을 만들고, 답변 형식과 출처를 검사하는 함수
def answer_question(question, rows, generate):
    if not rows:
        return {"answer": "확인할 문서가 없습니다.", "citations": [], "needs_human": True}
    context = "\n\n".join(
        f"[{row['chunk_id']}] {row['text']}" for row in rows
    )
    reply = support.validate_shape(generate(question, context))
    allowed = {row["chunk_id"] for row in rows}

    # 답변에 검색 결과에 없는 출처가 하나라도 있다면 오류가 발생한다. 
    if any(citation not in allowed for citation in reply["citations"]):
        raise ValueError("검색하지 않은 출처가 있습니다.")

    # bool(citations)는 출처가 있으면 True, 없으면 False.
    # 정상 답변(False)에 출처가 없거나, 담당자 확인(True)에 출처가 있으면 오류
    if reply["needs_human"] == bool(reply["citations"]):
        raise ValueError("답변에는 출처가 필요하며 담당자 확인에는 출처를 비웁니다.")
    return reply

# 평가 기준으로 사용할 골든 데이터셋을 만드는 함수 
# 골든 데이터셋은 쉽게 말해 문제와 모범 답안이 담긴 채점 기준표 
def make_golden():
    return [
        # 제공 문서에서 답을 찾을 수 있는 별칭 질문
        {
            "question_id": "custom-vpn",
            "question": "초록문을 사용하려면 누구에게 승인을 요청해야 하나요?",
            "category": "access",
            "reference_answer": "VPN 원격 접속을 사용하려면 보안팀에 승인을 요청해야 합니다.",
            "relevant_document_ids": ["vpn"],
            "required_terms": ["보안팀"],
        },
        # 제공 문서에 자료가 없어 담당자 확인이 필요한 질문
        {
            "question_id": "custom-overseas",
            "question": "해외 출장 숙박비의 지원 한도는 얼마인가요?",
            "category": "overseas",
            "reference_answer": "제공 자료에 해외 출장 숙박비 지원 규정이 없어 담장자 확인이 필요합니다.",
            "relevant_document_ids": [],
            "required_terms": [],
        },
    ]

# 평가 기준과 실제 검색·답변 결과를 비교해, 잘된 점과 실패 원인을 판정하는 함수
def measure(case, rows, reply):
    expected = set(case["relevant_document_ids"])
    found = {row["document_id"] for row in rows}

    # 필요한 문서 중 실제로 찾은 문서의 비율을 계산하고, 필요한 문서가 없으면 None을 반환한다. 
    recall = len(expected & found) / len(expected) if expected else None
    answer_ok = (all(term in reply["answer"] for term in case["required_terms"])
                 and not reply["needs_human"]) if expected else reply["needs_human"]
    failure = "없음"
    if expected and recall < 1:
        failure = "검색 누락"
    elif not answer_ok:
        failure = "답변 확인 필요" if expected else "보류 실패"
    # 관측: 실제 evaluate 결과에서 개선, 악화 질문과 답변 본문을 확인해 기록합니다.
    return {"document_recall": recall, "answer_check": bool(answer_ok), "failure": failure}


# 선택 심화 1. 두 검색 순위를 합쳐 근거를 모으기
def fuse_rankings(rankings, top_k=2):
    # 선택 심화: 문제의 RRF 규칙에 맞춰 직접 작성하세요.
    return todo("검색 순위 목록을 RRF 점수로 합치세요.")


if __name__ == "__main__":
    support.cli(globals())
