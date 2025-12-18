import json
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infra.db.models import NoticeTemplate
from app.models.schemas import ClassificationResult
from app.services.agents import (
    create_change_validator_agent,
    create_template_comparator_agent,
)
from app.services.nara_bid_service import get_latest_bid_notice
from app.services.tasks import (
    create_change_validation_task,
    create_multi_template_comparison_task,
)
from app.tools.template_selector import get_template_selector
from app.utils.document_parser import parse_document
from crewai import Crew, Process


def detect_file_type(content: bytes) -> str:
    """
    파일 바이트 시그니처로 파일 타입 감지

    Args:
        content: 파일 바이트

    Returns:
        파일 타입 ('pdf', 'hwp', 'docx', 'txt')
    """
    if not content or len(content) < 4:
        return "txt"

    # PDF: %PDF (0x25 0x50 0x44 0x46)
    if content[:4] == b"%PDF":
        return "pdf"

    # HWP 5.0 이상 (ZIP based): PK (0x50 0x4B)
    if content[:2] == b"PK":
        # DOCX도 ZIP이므로 추가 확인 필요
        if b"HWP Document File" in content[:1024] or b"hwp" in content[:512].lower():
            return "hwp"
        if b"word/" in content[:1024]:
            return "docx"
        # 기본적으로 ZIP 시그니처면 HWP로 가정 (나라장터에서는 주로 HWP)
        return "hwp"

    # HWP 3.0 이하 (OLE based): D0 CF 11 E0
    if content[:4] == b"\xd0\xcf\x11\xe0":
        return "hwp"

    # 기본값
    return "txt"


def validate_template_workflow(
    cntrctCnclsMthdNm: str,
    days_ago: int,
    db: Session,
) -> Dict[str, Any]:
    # 1. 최신 공고문 URL 여러 개 조회
    num_samples = 3  # 비교할 샘플 개수
    print(f"📥 최신 공고문 {num_samples}개 조회 중... (유형: {cntrctCnclsMthdNm}, 기간: {days_ago}일)")
    doc_urls = get_latest_bid_notice(
        days_ago=days_ago,
        cntrctCnclsMthdNm=cntrctCnclsMthdNm,
        limit=num_samples,
    )

    if isinstance(doc_urls, str):
        doc_urls = [doc_urls]

    latest_docs = _download_and_parse_docs(doc_urls)
    print(f"✅ 총 {len(latest_docs)}개 공고문 파싱 완료")

    latest_template, our_template_content = _load_latest_template(db, cntrctCnclsMthdNm)
    template_version = latest_template.version if latest_template else None

    comparison_result = _run_comparison_loop(
        latest_docs,
        our_template_content,
        template_version=template_version,
    )

    comparison_result = _normalize_comparison_result(comparison_result)

    new_template_row = _save_updated_template(
        db,
        cntrctCnclsMthdNm,
        comparison_result,
    )

    return _build_response(
        cntrctCnclsMthdNm,
        comparison_result,
        new_template_row,
        latest_template,
    )


def _download_and_parse_docs(doc_urls: List[str]) -> List[Dict[str, Any]]:
    latest_docs: List[Dict[str, Any]] = []
    for idx, doc_url in enumerate(doc_urls, 1):
        print(f"📄 공고문 {idx}/{len(doc_urls)} 다운로드 중: {doc_url}")
        try:
            response = requests.get(doc_url, timeout=30)
            response.raise_for_status()

            file_content = response.content
            file_type = detect_file_type(file_content)
            doc_content = parse_document(file_content, f"latest_notice_{idx}.{file_type}")
            latest_docs.append(
                {"url": doc_url, "content": doc_content, "index": idx}
            )
            print(f"✅ 공고문 {idx} 파싱 완료 (형식: {file_type}, 길이: {len(doc_content)}자)")
        except Exception as exc:
            print(f"⚠️ 공고문 {idx} 다운로드 실패: {str(exc)}")
            continue

    if not latest_docs:
        raise HTTPException(status_code=500, detail="모든 공고문 다운로드 실패")

    return latest_docs


def _load_latest_template(
    db: Session,
    cntrctCnclsMthdNm: str,
) -> Tuple[Optional[NoticeTemplate], str]:
    print(f"📋 DB에서 최신 템플릿 조회 중... (유형: {cntrctCnclsMthdNm})")
    latest_template = (
        db.query(NoticeTemplate)
        .filter(NoticeTemplate.template_type == cntrctCnclsMthdNm)
        .order_by(NoticeTemplate.created_at.desc())
        .first()
    )

    if not latest_template:
        print("⚠️ DB에 템플릿이 없어 파일 시스템에서 로드합니다")
        template_selector = get_template_selector()
        classification_result = ClassificationResult(
            recommended_type=cntrctCnclsMthdNm,
            confidence=1.0,
            reason="템플릿 검증용",
            alternative_types=[],
        )
        template = template_selector.select_template(
            classification_result,
            preferred_format="md",
        )
        print(f"✅ 파일 템플릿 로드 완료: {template.template_id}")
        return None, template.content

    print(
        f"✅ DB 템플릿 로드 완료: id={latest_template.id}, "
        f"version={latest_template.version}, created_at={latest_template.created_at}"
    )

    keywords_to_check = [
        ("예정가격 범위 내", "이미 업데이트된 표현"),
        ("청렴계약 이행 서약", "청렴계약 섹션"),
        ("예정가격 이하", "구버전 표현 (있으면 안됨)"),
    ]
    print("🔍 템플릿 키워드 검사:")
    for keyword, desc in keywords_to_check:
        exists = keyword in latest_template.content
        status = (
            "✅"
            if (keyword != "예정가격 이하" and exists)
            or (keyword == "예정가격 이하" and not exists)
            else "⚠️"
        )
        print(f"  {status} '{keyword}' ({desc}): {'포함됨' if exists else '없음'}")

    return latest_template, latest_template.content


def _run_comparison_loop(
    latest_docs: List[Dict[str, Any]],
    our_template_content: str,
    template_version: Optional[str] = None,
) -> Dict[str, Any]:
    max_recheck_iterations = 2
    current_iteration = 0
    recheck_guideline = None

    print("🔄 템플릿 검증 오케스트레이션 시작")

    comparison_result: Dict[str, Any] = {}

    while current_iteration < max_recheck_iterations:
        current_iteration += 1
        print(f"\n{'=' * 60}")
        print(f"🔍 반복 {current_iteration}/{max_recheck_iterations}: 템플릿 비교 시작")
        print(f"{'=' * 60}")

        comparator = create_template_comparator_agent()
        comparison_task = create_multi_template_comparison_task(
            comparator,
            latest_docs,
            our_template_content,
            template_version=template_version,
            recheck_guideline=recheck_guideline,
        )
        crew = Crew(
            agents=[comparator],
            tasks=[comparison_task],
            process=Process.sequential,
            verbose=True,
        )

        result_str = str(crew.kickoff())
        print(f"🔍 Comparator Agent 응답 길이: {len(result_str)}자")
        comparison_result = _parse_agent_json(result_str, allow_updated_template=True)

        if not (comparison_result.get("has_changes") and comparison_result.get("changes")):
            print("ℹ️  Comparator만 실행됨 (변경사항 없음) - 루프 종료")
            break

        validation_data = _run_change_validation(
            comparison_result,
            our_template_content,
        )

        if not validation_data:
            print("⚠️ Validator 결과가 비어있음 - 변경사항 없음으로 처리")
            comparison_result["has_changes"] = False
            comparison_result["changes"] = []
            break

        decision = validation_data.get("decision")
        if decision:
            decision, requires_recheck, approved = _apply_decision_format(
                validation_data,
            )
            print(
                f"✅ 검증 결과: decision={decision}, recheck={requires_recheck}, "
                f"approved={len(approved)}개"
            )

            if decision == "APPROVE" and approved:
                comparison_result["changes"] = approved
                comparison_result["summary"] = validation_data.get(
                    "summary",
                    f"{len(approved)}개 변경사항 승인됨",
                )
                print(f"✅ {len(approved)}개 변경사항 승인됨 - 루프 종료")
                break

            if decision == "REJECT" and requires_recheck:
                recheck_guideline = validation_data.get("recheck_guideline", {})
                print(f"🔄 재검사 필요: {recheck_guideline}")
                print(f"   - 현재 반복: {current_iteration}/{max_recheck_iterations}")
                if current_iteration < max_recheck_iterations:
                    print("   → 다음 반복에서 재검사 수행")
                    continue
                print("   → 최대 반복 횟수 도달, 변경사항 없음으로 처리")
                comparison_result["has_changes"] = False
                comparison_result["changes"] = []
                comparison_result["summary"] = "최대 재검사 횟수 도달. 변경사항 없음으로 처리."
                break

            print("✅ 변경사항 없음 (재검사 불필요)")
            comparison_result["has_changes"] = False
            comparison_result["changes"] = []
            comparison_result["summary"] = validation_data.get(
                "summary",
                "변경사항 없음. 템플릿이 이미 최신 상태입니다.",
            )
            break

        if "has_real_changes" in validation_data:
            approved, rejected = _apply_legacy_validation_format(
                validation_data,
                comparison_result,
            )

            print(f"✅ 검증 완료: 승인={len(approved)}개, 거부={len(rejected)}개")
            if rejected:
                print("🚫 거부된 변경사항:")
                for rejected_change in rejected:
                    print(f"  - {rejected_change.get('reason', 'N/A')}")

            if not approved:
                print("✅ 실질적 변경사항 없음 - has_changes를 false로 설정")
                comparison_result["has_changes"] = False
                comparison_result["changes"] = []
                comparison_result["summary"] = validation_data.get(
                    "summary",
                    "변경사항 없음. 템플릿이 이미 최신 상태입니다.",
                )
            else:
                comparison_result["changes"] = approved
                comparison_result["summary"] = validation_data.get(
                    "summary",
                    f"{len(approved)}개 변경사항 승인됨",
                )
                print(f"✅ {len(approved)}개 변경사항 승인됨")
            break

        print("⚠️ Validator 결과 포맷을 알 수 없음 - 변경사항 없음으로 처리")
        comparison_result["has_changes"] = False
        comparison_result["changes"] = []
        break

    print(f"\n{'=' * 60}")
    print(f"🏁 템플릿 검증 오케스트레이션 완료 (총 {current_iteration}회 반복)")
    print(f"{'=' * 60}\n")

    return comparison_result


def _run_change_validation(
    comparison_result: Dict[str, Any],
    our_template_content: str,
) -> Optional[Dict[str, Any]]:
    print("🔍 Change Validator Agent로 변경사항 검증 중...")
    validator = create_change_validator_agent()
    validation_task = create_change_validation_task(
        validator,
        comparison_result,
        our_template_content,
    )
    validation_crew = Crew(
        agents=[validator],
        tasks=[validation_task],
        process=Process.sequential,
        verbose=True,
    )

    validation_str = str(validation_crew.kickoff())
    print(f"🔍 Validator Agent 응답 길이: {len(validation_str)}자")

    return _parse_agent_json(validation_str, allow_updated_template=False)


def _parse_agent_json(
    result_str: str,
    allow_updated_template: bool,
) -> Dict[str, Any]:
    try:
        parsed = json.loads(result_str)
        print("✅ 직접 JSON 파싱 성공")
        return parsed
    except json.JSONDecodeError as exc:
        print(f"⚠️ 직접 JSON 파싱 실패: {str(exc)}")

    patterns = [
        r"```json\s*(\{[\s\S]*\})\s*```",
        r"```\s*(\{[\s\S]*\})\s*```",
        r"(\{[\s\S]*\})",
    ]

    for pattern in patterns:
        json_match = re.search(pattern, result_str)
        if not json_match:
            continue

        json_text = json_match.group(1)
        print(f"📝 패턴 매칭, JSON 길이: {len(json_text)}자")

        if allow_updated_template:
            parsed = _try_parse_with_updated_template(json_text)
        else:
            parsed = _try_parse_json(json_text)

        if parsed is not None:
            print("✅ JSON 추출 및 파싱 성공")
            return parsed

    print("❌ 모든 JSON 추출 패턴 실패")
    print(f"🔍 응답 앞 500자: {result_str[:500]}")
    return {
        "error": "JSON 파싱 실패",
        "raw_output": result_str[:2000],
        "has_changes": False,
    }


def _try_parse_json(json_text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


def _try_parse_with_updated_template(json_text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        template_match = re.search(
            r"\"updated_template\":\s*\"([\s\S]*?)\"(?=\s*[,}])",
            json_text,
        )
        if not template_match:
            return None

        json_without_template = re.sub(
            r"\"updated_template\":\s*\"[\s\S]*?\"(?=\s*[,}])",
            "\"updated_template\": \"PLACEHOLDER\"",
            json_text,
        )
        try:
            parsed = json.loads(json_without_template)
        except json.JSONDecodeError:
            return None

        parsed["updated_template"] = template_match.group(1)
        return parsed


def _apply_decision_format(
    validation_data: Dict[str, Any],
) -> Tuple[str, bool, List[Dict[str, Any]]]:
    decision = validation_data.get("decision", "REJECT")
    requires_recheck = validation_data.get("requires_recheck", False)
    approved = validation_data.get("approved_changes", [])
    return decision, requires_recheck, approved


def _apply_legacy_validation_format(
    validation_data: Dict[str, Any],
    comparison_result: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    has_real = validation_data.get("has_real_changes", False)
    approved = validation_data.get("approved_changes", [])
    rejected = validation_data.get("rejected_changes", [])

    if not has_real or not approved:
        comparison_result["has_changes"] = False
        comparison_result["changes"] = []
    else:
        comparison_result["changes"] = approved

    return approved, rejected


def _normalize_comparison_result(comparison_result: Dict[str, Any]) -> Dict[str, Any]:
    if not comparison_result.get("has_changes"):
        comparison_result["changes"] = []
        if comparison_result.get("summary") and (
            "추가" in comparison_result["summary"]
            or "변경" in comparison_result["summary"]
        ):
            comparison_result["summary"] = "변경사항 없음. 템플릿이 이미 최신 상태입니다."
        print("✅ 응답 정규화: has_changes=false이므로 changes 배열을 비웠습니다")
    else:
        if not comparison_result.get("changes"):
            print("⚠️ 경고: has_changes=true이지만 changes 배열이 비어있습니다")
            comparison_result["has_changes"] = False
            comparison_result["summary"] = "변경사항 없음 (changes 배열이 비어있음)"

    return comparison_result


def _save_updated_template(
    db: Session,
    cntrctCnclsMthdNm: str,
    comparison_result: Dict[str, Any],
) -> Optional[NoticeTemplate]:
    if not comparison_result.get("has_changes"):
        return None

    updated_template = comparison_result.get("updated_template", "")
    if not updated_template:
        return None

    updated_template = (
        updated_template.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
    )

    print("🔍 업데이트된 템플릿 검증:")
    changes_applied: List[str] = []
    for change in comparison_result.get("changes", []):
        if change.get("type") == "modified":
            new_text = change.get("new_text", "")
            if new_text and new_text in updated_template:
                changes_applied.append(f"✅ '{new_text[:30]}...' 반영됨")
            else:
                changes_applied.append(f"⚠️ '{new_text[:30]}...' 반영 안됨")
        elif change.get("type") == "added":
            section = change.get("section", "")
            if section and section in updated_template:
                changes_applied.append(f"✅ 섹션 '{section}' 추가됨")
            else:
                changes_applied.append(f"⚠️ 섹션 '{section}' 추가 안됨")

    for status in changes_applied:
        print(f"  {status}")

    not_applied = [status for status in changes_applied if "⚠️" in status]
    if not_applied:
        print(f"❌ {len(not_applied)}개 변경사항이 반영되지 않아 저장하지 않습니다")
        comparison_result["has_changes"] = False
        return None

    latest_existing = (
        db.query(NoticeTemplate)
        .filter(NoticeTemplate.template_type == cntrctCnclsMthdNm)
        .order_by(NoticeTemplate.created_at.desc())
        .first()
    )

    new_version = "1.0.0"
    if latest_existing and latest_existing.version:
        parts = latest_existing.version.split(".")
        if len(parts) == 3 and parts[2].isdigit():
            parts[2] = str(int(parts[2]) + 1)
            new_version = ".".join(parts)
        else:
            new_version = latest_existing.version

    summary = comparison_result.get("summary", "자동 검증 결과에 따른 업데이트 템플릿")

    new_template_row = NoticeTemplate(
        template_type=cntrctCnclsMthdNm,
        version=new_version,
        content=updated_template,
        summary=summary[:255] if summary else None,
    )
    db.add(new_template_row)
    db.commit()
    db.refresh(new_template_row)

    print(
        f"✅ 업데이트된 템플릿을 DB에 저장: id={new_template_row.id}, "
        f"type={new_template_row.template_type}, version={new_template_row.version}"
    )

    return new_template_row


def _build_response(
    cntrctCnclsMthdNm: str,
    comparison_result: Dict[str, Any],
    new_template_row: Optional[NoticeTemplate],
    latest_template: Optional[NoticeTemplate],
) -> Dict[str, Any]:
    latest_template_id = None
    if new_template_row:
        latest_template_id = new_template_row.id
    elif latest_template:
        latest_template_id = latest_template.id

    return {
        "status": "unchanged" if not comparison_result.get("has_changes") else "changed",
        "template_type": cntrctCnclsMthdNm,
        "changes_detected": comparison_result.get("has_changes", False),
        "summary": comparison_result.get("summary", ""),
        "changes": comparison_result.get("changes", []),
        "latest_template_id": latest_template_id,
        "saved_template": (
            {
                "id": new_template_row.id,
                "version": new_template_row.version,
                "created_at": (
                    new_template_row.created_at.isoformat()
                    if new_template_row.created_at
                    else None
                ),
            }
            if new_template_row
            else None
        ),
    }
