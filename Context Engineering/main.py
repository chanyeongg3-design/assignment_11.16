"""main.py의 todo(...) 부분을 작성하세요. support.py와 checks.py는 그대로 사용합니다."""
import copy
import hashlib
import json
import sys

import support


def todo(message):
    raise NotImplementedError(message)


# 필수 1. 필요한 자료와 사용자 기억 관리하기
# 주어진 항목 중 사용할 컨텍스트를 고르는 함수 
def select_context(items, user_id, now):
    # items: 자료 후보들, user_id: 현재 사용자, now: 만료 판단 기준일
    kept = []
    for item in items:
        # and로 연결한 조건을 모두 만족해야 allowed가 True가 된다.
        allowed = (
            item["user_id"] in ("public", user_id)  # 공개 자료 또는 내 자료
            and item["trusted"] # 신뢰할 수 있는 자료
            and item["active"]  # 현재 유효한 자료
            and (
                item["expires_at"] is None  # 만료일이 없거나
                or item["expires_at"] > now # 아직 만료되지 않은 자료 
            )
        )
        if allowed:
            # 선택한 자료를 복사해 원본과 별도로 보관한다.
            kept.append(copy.deepcopy(item))
    # 이유: 우선순위가 높아도 다른 사용자의 자료이거나 신뢰할 수 없고,
    # 현재 유효하지 않거나 만료된 자료일 수 있으므로 사용 가능 여부를 먼저 확인한다. 
    return sorted(kept, key=lambda item: (-item["priority"], item["id"]))


def memory_action(records, user_id, action, name, value=None):
    support.validate_memory_input(user_id, action, name, value)
    # 사용자 ID와 기억 이름을 합쳐 다른 사용자의 기억과 구분한다.
    key = f"{user_id}:{name}"
    if action == "read":
        # get(key)는 기억이 없으면 None을 반환한다.
        # deepcopy는 조회한 값을 수정해도 원본 기억이 바뀌지 않도록 복사한다.
        return copy.deepcopy(records.get(key))
    if action == "create":
        if key in records:
            raise ValueError("이미 있는 기억입니다. update를 사용하세요.")
        # 새 기억을 복사해 저장하므로 외부에서 value를 수정해도 영향을 받지 않는다.
        records[key] = copy.deepcopy(value)
    elif action == "update":
        if key not in records:
            raise KeyError("수정할 기억이 없습니다.")
        # 기존 기억을 새 value의 복사본으로 교체한다: copy.deepcopy(value)
        records[key] = copy.deepcopy(value)
    elif action == "delete":
        # pop(key, None)은 해당 기억을 삭제하고 반환하며, 없으면 None을 반환한다.
        return records.pop(key, None)
    return copy.deepcopy(records[key])


def build_messages(prefix, question, context, turns, summary):
    data = json.dumps({"reference_data": context, "summary": summary}, ensure_ascii=False)
    history = [message for turn in turns for message in turn["messages"]]
    # 이유: 장기 기억과 세션 상태의 차이, 자료와 지시를 나누는 이유를 적으세요.
    return [
        {"role": "developer", "content": prefix},   # 고정 지시
        {"role": "user", "content": data},          # 참고 자료와 요약
        *history,   # 기존 대화 메시지들
        {"role": "user", "content": question},  # 현재 질문
    ]


# 필수 2. 긴 대화를 줄이고 반복 입력 재사용하기
def summarize(turns):
    summary = {}
    for turn in turns:
        # fact_lines: (항목, 값)을 쌍으로 하나씩 꺼내주는 함수
        for name, value in support.fact_lines(turn["messages"][0]["content"]):
            summary[name] = {
                "value": value, # 최신 값
                "source_turn_id": turn["id"], # 출처 턴
            }
    return summary


def select_window(turns, limit, reserve, margin, make_messages, count):
    # validate_budget(): 토큰 예산 계산에 들어갈 숫자가 모두 0이상의 정수인지 확인하는 함수
    support.validate_budget(limit, reserve, margin)
    budget = limit - reserve - margin
    if budget <= 0 or count(make_messages([])) > budget:
        raise ValueError("고정 입력만으로 예산을 넘었습니다.")
    kept = []
    for turn in reversed(turns):
        candidate = [turn, *kept]
        # 후보 턴을 포함한 전체 입력이 토큰 예산을 넘으면 선택을 멈춘다.
        if count(make_messages(candidate)) > budget:
            break
        kept = candidate
    # 관측: 압축 비교 후 토큰 수, 빠진 사실, 선택한 한도를 기록합니다.
    # 압축 후 토큰 수: 요약과 최근 대화를 사용해 입력을 1,999 -> 1744 토큰으로 줄임
    # 빠진 사실: 최근 대화만 보내면 담당자, 마감일, 승인조건이 빠졌고, 요약을 붙이니 세 항목이 모두 남음
    # 선택한 한도: 전체 한도 2,300토큰에서 `요약 + 최근 대화`를 선택했고 입력 1,744토큰이 입력예산 1,788토큰 안에 들어감
    return kept


def cache_key(prefix, user_id):
    key_text = f"{user_id}\n{prefix}"
    return hashlib.sha256(key_text.encode("utf-8")).hexdigest()
    # 관측: 실제 캐시 읽기/쓰기와 비용을 확인하고 미관측이면 그대로 적습니다.


# 선택 심화 1. 새 대화만 반영하고 변경 이력 남기기
def merge_summary(previous, turns):
    return todo("선택 심화: 새 턴의 요약과 변경 이력")


if __name__ == "__main__":
    raise SystemExit(support.cli(sys.modules[__name__]))
