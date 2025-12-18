import requests
from datetime import datetime, timedelta
from app.config import get_settings

settings = get_settings()

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

    url = f"{settings.nara_base_url}/getBidPblancListInfoThng"  # 물품조회 API
    params = {
        "serviceKey": settings.nara_api_key,
        "pageNo": 1,
        "numOfRows": 20,  # 더 많이 조회해서 필터링
        "inqryDiv": "1",  # 필수: 조회구분 (1:등록일시)
        "inqryBgnDt": start,
        "inqryEndDt": end,
        "type": "json",
        "ntceInsttNm": "한국환경공단"  # 공고기관명
    }

    # 선택적 필터: 계약체결방법명
    if cntrctCnclsMthdNm:
        params["cntrctCnclsMthdNm"] = cntrctCnclsMthdNm

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # HTTP 에러 확인

        data = response.json()

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


