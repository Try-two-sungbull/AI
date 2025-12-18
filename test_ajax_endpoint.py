"""
AJAX 엔드포인트 직접 호출 테스트
"""
import requests
from bs4 import BeautifulSoup
import re

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000251078",
    "X-Requested-With": "XMLHttpRequest"
}

BASE_URL = "https://www.law.go.kr"

def test_ajax_endpoints():
    """AJAX 엔드포인트 테스트"""
    print("=" * 60)
    print("AJAX 엔드포인트 테스트")
    print("=" * 60)
    
    # 스크립트에서 찾은 파라미터
    param = {
        "admRulSeq": "2100000251078",
        "admRulId": "27952",
        "joTpYn": "N",
        "languageType": "KO",
        "chrClsCd": "010202",
        "preview": "",
        "urlMode": ""
    }
    
    # 가능한 엔드포인트들
    endpoints = [
        "/LSW/admRulInfoR.do",  # 본문
        "/LSW/ileAdmRulInfoR.do",  # 미리보기
        "/LSW/admRulRvsInfoR.do",  # 연혁
    ]
    
    for endpoint in endpoints:
        print(f"\n{'='*60}")
        print(f"테스트: {endpoint}")
        print(f"{'='*60}")
        
        try:
            url = BASE_URL + endpoint
            response = requests.post(url, data=param, headers=DEFAULT_HEADERS, timeout=10)
            
            print(f"HTTP {response.status_code}")
            
            if response.status_code == 200:
                if response.encoding is None:
                    response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                
                print(f"텍스트 길이: {len(text):,}자")
                
                # 고시금액 패턴 찾기
                patterns = [
                    r'물품\s*및\s*용역[:\s]*(\d+)\s*억\s*(\d+)\s*천만\s*원',
                    r'○\s*물품\s*및\s*용역[:\s]*(\d+)\s*억\s*(\d+)\s*천만\s*원',
                    r'(\d+)\s*억\s*(\d+)\s*천만\s*원',
                ]
                
                amount = None
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        if len(match.groups()) == 2:
                            billions = int(match.group(1))
                            ten_millions = int(match.group(2))
                            amount = billions * 100_000_000 + ten_millions * 10_000_000
                            print(f"\n✅ 고시금액 발견!")
                            print(f"   패턴: {pattern}")
                            print(f"   매칭: {match.group(0)}")
                            print(f"   금액: {amount:,}원")
                            print(f"   형식: {billions}억 {ten_millions}천만 원")
                            
                            # 주변 텍스트
                            start = max(0, match.start() - 200)
                            end = min(len(text), match.end() + 200)
                            context = text[start:end]
                            print(f"\n주변 텍스트:")
                            print(context)
                            
                            return amount
                
                if not amount:
                    # 관련 키워드가 있는지 확인
                    if '물품' in text or '용역' in text:
                        print("   '물품/용역' 키워드 발견, 하지만 금액 패턴 매칭 실패")
                        # 관련 라인 출력
                        lines = text.split('\n')
                        for i, line in enumerate(lines):
                            if '물품' in line or '용역' in line:
                                print(f"   [{i}] {line[:150]}")
                    else:
                        print("   관련 키워드를 찾을 수 없습니다.")
                        
            else:
                print(f"   ❌ 실패: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ 오류: {str(e)}")
    
    # GET 방식도 시도
    print(f"\n{'='*60}")
    print("GET 방식 테스트")
    print(f"{'='*60}")
    
    get_url = f"{BASE_URL}/LSW/admRulInfoR.do?admRulSeq=2100000251078&admRulId=27952"
    try:
        response = requests.get(get_url, headers=DEFAULT_HEADERS, timeout=10)
        if response.status_code == 200:
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            
            print(f"텍스트 길이: {len(text):,}자")
            
            # 고시금액 패턴 찾기
            pattern = r'물품\s*및\s*용역[:\s]*(\d+)\s*억\s*(\d+)\s*천만\s*원'
            match = re.search(pattern, text)
            if match:
                billions = int(match.group(1))
                ten_millions = int(match.group(2))
                amount = billions * 100_000_000 + ten_millions * 10_000_000
                print(f"\n✅ 고시금액 발견!")
                print(f"   금액: {amount:,}원")
                return amount
            else:
                print("   고시금액을 찾을 수 없습니다.")
    except Exception as e:
        print(f"   ❌ 오류: {str(e)}")
    
    return None

if __name__ == "__main__":
    result = test_ajax_endpoints()
    if result:
        print(f"\n{'='*60}")
        print(f"✅ 최종 결과: {result:,}원")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print("❌ 고시금액을 찾을 수 없습니다.")
        print(f"{'='*60}")


