import os
import requests
from datetime import datetime, timedelta
from app.config import get_settings

settings = get_settings()
# 파일 저장 경로가 설정되어 있으면 디렉토리 생성 (PostgreSQL 사용 시 선택적)
if hasattr(settings, 'file_storage_path') and settings.file_storage_path:
    os.makedirs(settings.file_storage_path, exist_ok=True)



def get_latest_bid_notice(days_ago: int = 3, cntrctCnclsMthdNm: str = None, limit: int = 1):
    """
    1️⃣ 최신 입찰공고 URL 조회

    Args:
        days_ago: 며칠 전부터 조회할지 (기본 3일)
        cntrctCnclsMthdNm: 계약체결방법명 (예: "적격심사", "소액수의" 등)
        limit: 반환할 공고 URL 개수 (기본 1개, 최대 10개)

    Returns:
        limit=1: 단일 URL 문자열
        limit>1: URL 리스트
    """
    # 오늘 날짜 기준
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days_ago)

    start = start_date.strftime("%Y%m%d") + "0000"
    end = end_date.strftime("%Y%m%d") + "2359"

    # API 키 확인 및 디버깅
    api_key = settings.nara_api_key
    if not api_key or api_key.strip() == "":
        raise Exception(
            "나라장터 API 키가 설정되지 않았습니다. "
            "환경 변수 NARA_API_KEY를 설정해주세요. "
            "공공데이터포털(https://www.data.go.kr)에서 발급받을 수 있습니다."
        )
    
    # API 키가 있는지 확인 (디버깅용 - 마스킹 처리)
    api_key_preview = api_key[:10] + "..." if len(api_key) > 10 else api_key
    print(f"🔑 나라장터 API 키 확인: {api_key_preview} (길이: {len(api_key)})")
    
    # 나라장터 API URL (올바른 엔드포인트 포함)
    # 환경 변수에 잘못된 값이 있을 수 있으므로 올바른 URL로 강제 설정
    base_url = settings.nara_base_url
    if "/getBidPblancListInfoThng" not in base_url:
        # 올바른 엔드포인트가 없으면 추가
        if base_url.endswith("/"):
            url = base_url + "getBidPblancListInfoThng"
        else:
            url = base_url + "/getBidPblancListInfoThng"
    else:
        url = base_url
    params = {
        "serviceKey": api_key,
        "pageNo": 1,
        "numOfRows": 20,  # 더 많이 조회해서 필터링
        "inqryDiv": "1",  # 필수: 조회구분 (1:등록일시)
        "inqryBgnDt": start,
        "inqryEndDt": end,
        "type": "json",
        "ntceInsttNm": "한국환경공단"  # 공고기관명
    }
    
    print(f"📡 나라장터 API 요청 URL: {url}")
    print(f"📡 요청 파라미터: {', '.join([f'{k}={v[:20] if isinstance(v, str) and len(v) > 20 else v}' for k, v in params.items() if k != 'serviceKey'])}")

    # 선택적 필터: 계약체결방법명
    if cntrctCnclsMthdNm:
        params["cntrctCnclsMthdNm"] = cntrctCnclsMthdNm

    try:
        response = requests.get(url, params=params, timeout=10)
        
        # 응답 상태 코드 확인
        print(f"📥 나라장터 API 응답 상태: {response.status_code}")
        
        # 500 에러인 경우 응답 본문 확인
        if response.status_code == 500:
            print(f"⚠️ 나라장터 API 500 에러 응답 본문: {response.text[:500]}")
            raise Exception(
                f"나라장터 API 서버 오류 (500): "
                f"서버가 일시적으로 응답하지 않습니다. "
                f"잠시 후 다시 시도해주세요. "
                f"응답: {response.text[:200]}"
            )
        
        response.raise_for_status()  # HTTP 에러 확인

        data = response.json()
        
        # API 응답에 에러가 있는지 확인
        if "response" in data and "header" in data["response"]:
            header = data["response"]["header"]
            result_code = header.get("resultCode", "")
            result_msg = header.get("resultMsg", "")
            
            if result_code != "00" and result_code != "0":
                error_msg = f"나라장터 API 오류 (코드: {result_code}): {result_msg}"
                if "SERVICE_KEY" in result_msg.upper() or "인증" in result_msg or "KEY" in result_msg.upper():
                    error_msg += "\n나라장터 API 키가 유효하지 않거나 만료되었습니다. 공공데이터포털에서 확인해주세요."
                raise Exception(error_msg)

        # 응답 구조 확인
        if "response" not in data:
            raise Exception(f"예상치 못한 응답 구조: {data}")

        body = data["response"]["body"]
        items = body.get("items")

        if not items:
            raise Exception("최신 공고를 찾을 수 없습니다")

        # item이 리스트인지 딕셔너리인지 확인
        if isinstance(items, dict) and "item" in items:
            item_list = items["item"]
            # item이 단일 딕셔너리면 리스트로 변환
            if isinstance(item_list, dict):
                item_list = [item_list]
        elif isinstance(items, list):
            item_list = items
        else:
            raise Exception(f"items 구조가 예상과 다릅니다: {type(items)}")

        if not item_list or len(item_list) == 0:
            raise Exception("공고 목록이 비어있습니다")

        # ntceSpecDocUrl1이 있는 공고 URL 수집
        doc_urls = []
        for item in item_list:
            doc_url = item.get("ntceSpecDocUrl1")
            if doc_url:
                doc_urls.append(doc_url)
                if len(doc_urls) >= limit:
                    break

        if not doc_urls:
            raise Exception(f"공고문 URL(ntceSpecDocUrl1)을 찾을 수 없습니다. 조회된 공고 수: {len(item_list)}")

        print(f"✅ 공고문 URL {len(doc_urls)}개 찾음")

        # limit=1이면 단일 URL, 아니면 리스트 반환
        return doc_urls[0] if limit == 1 else doc_urls

    except requests.exceptions.RequestException as e:
        raise Exception(f"나라장터 API 요청 실패: {str(e)}")
    except (KeyError, IndexError) as e:
        raise Exception(f"응답 데이터 파싱 실패: {str(e)}")


