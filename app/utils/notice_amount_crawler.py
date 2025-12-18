"""
기획재정부 고시금액 크롤링 도구

국가법령정보센터에서 최신 고시금액을 크롤링합니다.
연혁 탭에서 최신 고시를 확인하여 고시금액을 추출합니다.
고시금액은 2년마다 변경되므로, 공고문 생성 시마다 최신 정보를 확인합니다.
"""

import requests
from bs4 import BeautifulSoup
from typing import Optional
import re
import logging
from datetime import datetime, timedelta
import json
import time
import os

from app.config import get_settings

logger = logging.getLogger(__name__)

# User-Agent 설정
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 고시금액 URL (기획재정부 고시)
NOTICE_AMOUNT_URL = "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000251078"

# 하드코딩된 기본 고시금액 (2025년 기준: 2억 3천만 원)
# 고시금액은 2년마다 변경되므로, 크롤링 실패 시 이 값을 사용
# 변경 시 이 값만 업데이트하면 됨
DEFAULT_NOTICE_AMOUNT = 230_000_000  # 2억 3천만 원


class NoticeAmountCrawler:
    """기획재정부 고시금액 크롤러"""
    
    def __init__(self):
        self.cached_amount: Optional[int] = None
        self.cache_date: Optional[datetime] = None
        self.cache_duration = timedelta(days=30)  # 30일 캐시
    
    def get_notice_amount(self, force_refresh: bool = False) -> int:
        """
        최신 고시금액 조회
        
        우선순위:
        1. 환경변수 NOTICE_AMOUNT (선택적 오버라이드, 테스트용 등)
        2. 캐시된 값 (30일 캐시)
        3. 크롤링 시도 (최신 값 확인)
        4. 하드코딩된 기본값 (DEFAULT_NOTICE_AMOUNT)
        
        Args:
            force_refresh: 캐시 무시하고 강제 새로고침
        
        Returns:
            고시금액 (원 단위), 항상 값 반환 (None 없음)
        """
        # 1순위: 환경변수 확인 (선택적 오버라이드, 테스트/특수 상황용)
        settings = get_settings()
        if settings.notice_amount and settings.notice_amount > 0:
            logger.info(f"환경변수에서 고시금액 사용 (오버라이드): {settings.notice_amount:,}원")
            return settings.notice_amount
        
        env_amount = os.getenv("NOTICE_AMOUNT")
        if env_amount:
            try:
                amount = int(env_amount)
                if amount > 0:
                    logger.info(f"환경변수 NOTICE_AMOUNT에서 고시금액 사용 (오버라이드): {amount:,}원")
                    return amount
            except ValueError:
                logger.warning(f"환경변수 NOTICE_AMOUNT 값이 유효하지 않습니다: {env_amount}")
        
        # 2순위: 캐시 확인 (30일 캐시)
        if not force_refresh and self.cached_amount and self.cache_date:
            if datetime.now() - self.cache_date < self.cache_duration:
                logger.info(f"캐시된 고시금액 사용: {self.cached_amount:,}원 (캐시 날짜: {self.cache_date.strftime('%Y-%m-%d')})")
                return self.cached_amount
        
        # 3순위: 크롤링 시도 (최신 값 확인)
        logger.info("최신 고시금액 확인을 위해 크롤링 시도...")
        
        try:
            # requests로 먼저 시도
            amount = self._crawl_with_requests()
            if amount:
                self.cached_amount = amount
                self.cache_date = datetime.now()
                logger.info(f"✅ 고시금액 크롤링 성공: {amount:,}원 (30일간 캐시됨)")
                return amount
            
            # requests 실패 시 Selenium 시도 (선택적)
            logger.warning("requests 크롤링 실패, Selenium으로 재시도...")
            amount = self._crawl_with_selenium()
            if amount:
                self.cached_amount = amount
                self.cache_date = datetime.now()
                logger.info(f"✅ 고시금액 크롤링 성공 (Selenium): {amount:,}원 (30일간 캐시됨)")
                return amount
                
        except Exception as e:
            logger.error(f"고시금액 크롤링 중 오류 발생: {str(e)}")
        
        # 4순위: 캐시된 값이 있으면 사용 (만료되었어도)
        if self.cached_amount:
            logger.warning(f"크롤링 실패, 만료된 캐시 값 사용: {self.cached_amount:,}원")
            return self.cached_amount
        
        # 5순위: 하드코딩된 기본값 사용 (항상 안정적으로 작동)
        logger.warning(f"크롤링 실패 및 캐시 없음. 하드코딩된 기본값 사용: {DEFAULT_NOTICE_AMOUNT:,}원")
        logger.info(f"💡 고시금액이 변경되었다면 코드의 DEFAULT_NOTICE_AMOUNT 값을 업데이트하세요.")
        self.cached_amount = DEFAULT_NOTICE_AMOUNT
        self.cache_date = datetime.now()
        return DEFAULT_NOTICE_AMOUNT
    
    def _crawl_with_selenium(self) -> Optional[int]:
        """
        Selenium을 사용하여 연혁 탭에서 최신 고시금액 크롤링
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            # Chrome 옵션 설정 (headless 모드)
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument(f'user-agent={DEFAULT_HEADERS["User-Agent"]}')
            
            driver = None
            try:
                # ChromeDriver 실행 (시스템 PATH에 있으면 자동 감지)
                driver = webdriver.Chrome(options=chrome_options)
                driver.get(NOTICE_AMOUNT_URL)
                
                # 페이지 로드 대기
                time.sleep(2)
                
                # 연혁 탭 클릭
                try:
                    history_tab = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '연혁')]"))
                    )
                    history_tab.click()
                    time.sleep(2)  # AJAX 로드 대기
                except Exception as e:
                    logger.warning(f"연혁 탭 클릭 실패: {str(e)}")
                    # 연혁 탭이 없거나 이미 선택된 경우 계속 진행
                
                # 최신 고시의 본문 내용 가져오기
                # 오른쪽 패널에서 고시금액 찾기
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                
                # 고시금액 추출
                amount = self._extract_amount_from_text(text)
                return amount
                
            finally:
                if driver:
                    driver.quit()
                    
        except ImportError:
            logger.warning("Selenium이 설치되지 않았습니다. requests로 대체합니다.")
            return None
        except Exception as e:
            logger.error(f"Selenium 크롤링 실패: {str(e)}")
            return None
    
    def _crawl_with_requests(self) -> Optional[int]:
        """
        requests를 사용하여 고시금액 크롤링
        
        AJAX 엔드포인트를 직접 호출하여 본문 내용을 가져옵니다.
        """
        try:
            # 방법 1: AJAX 엔드포인트 직접 호출 (가장 확실한 방법)
            ajax_url = "https://www.law.go.kr/LSW/admRulInfoR.do"
            ajax_headers = DEFAULT_HEADERS.copy()
            ajax_headers["Referer"] = NOTICE_AMOUNT_URL
            ajax_headers["X-Requested-With"] = "XMLHttpRequest"
            
            # 스크립트에서 확인한 파라미터
            ajax_params = {
                "admRulSeq": "2100000251078",
                "admRulId": "27952",
                "joTpYn": "N",
                "languageType": "KO",
                "chrClsCd": "010202",
                "preview": "",
                "urlMode": ""
            }
            
            response = requests.post(ajax_url, data=ajax_params, headers=ajax_headers, timeout=10)
            response.raise_for_status()
            
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            # HTML 파싱
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            
            # 고시금액 추출
            amount = self._extract_amount_from_text(text)
            if amount:
                logger.info("AJAX 엔드포인트에서 고시금액 추출 성공")
                return amount
            
            # 방법 2: 메인 페이지에서 시도 (fallback)
            logger.warning("AJAX 엔드포인트에서 고시금액을 찾을 수 없어 메인 페이지에서 재시도...")
            response = requests.get(NOTICE_AMOUNT_URL, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()
            
            if response.encoding is None:
                response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            
            amount = self._extract_amount_from_text(text)
            return amount
            
        except Exception as e:
            logger.error(f"requests 크롤링 실패: {str(e)}")
            return None
    
    def _extract_amount_from_text(self, text: str) -> Optional[int]:
        """
        텍스트에서 고시금액 추출
        """
            
        # 고시금액 패턴 찾기
        # 예: "물품 및 용역: 2억 3천만 원" 또는 "○ 물품 및 용역: 2억 3천만 원"
        patterns = [
            r'물품\s*및\s*용역[:\s]*(\d+)\s*억\s*(\d+)\s*천만\s*원',
            r'○\s*물품\s*및\s*용역[:\s]*(\d+)\s*억\s*(\d+)\s*천만\s*원',
            r'(\d+)\s*억\s*(\d+)\s*천만\s*원',
            r'(\d+)\s*억\s*(\d+)\s*천\s*만\s*원',
        ]
        
        amount = None
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    # "2억 3천만 원" 형식
                    billions = int(match.group(1))
                    ten_millions = int(match.group(2))
                    amount = billions * 100_000_000 + ten_millions * 10_000_000
                    break
                elif len(match.groups()) == 1:
                    # "2억원" 형식 (천만 단위 없음)
                    billions = int(match.group(1))
                    amount = billions * 100_000_000
                    break
        
        # 숫자만 있는 경우도 찾기 (예: "230,000,000원" 또는 "230000000원")
        if amount is None:
            number_patterns = [
                r'(\d{1,3}(?:,\d{3})*)\s*원',  # 콤마 포함
                r'(\d{8,})\s*원',  # 8자리 이상 숫자
            ]
            
            for pattern in number_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    # 콤마 제거 후 숫자로 변환
                    num_str = match.replace(',', '')
                    num = int(num_str)
                    # 2억원 ~ 3억원 사이면 고시금액으로 추정
                    if 200_000_000 <= num <= 300_000_000:
                        amount = num
                        break
                if amount:
                    break
        
        return amount
    
    def format_amount(self, amount: int) -> str:
        """
        금액을 한글 형식으로 변환
        
        예: 230000000 → "2억 3천만 원"
        """
        if amount >= 100_000_000:
            billions = amount // 100_000_000
            remainder = amount % 100_000_000
            if remainder >= 10_000_000:
                ten_millions = remainder // 10_000_000
                return f"{billions}억 {ten_millions}천만 원"
            else:
                return f"{billions}억 원"
        else:
            return f"{amount:,}원"


# Singleton 인스턴스
_notice_amount_crawler = None


def get_notice_amount_crawler() -> NoticeAmountCrawler:
    """전역 NoticeAmountCrawler 인스턴스 반환"""
    global _notice_amount_crawler
    if _notice_amount_crawler is None:
        _notice_amount_crawler = NoticeAmountCrawler()
    return _notice_amount_crawler


def get_latest_notice_amount(force_refresh: bool = False) -> int:
    """
    최신 고시금액 조회 (편의 함수)
    
    우선순위:
    1. 환경변수 (선택적 오버라이드)
    2. 캐시 (30일)
    3. 크롤링 (최신 값 확인)
    4. 하드코딩된 기본값 (항상 안정적)
    
    Args:
        force_refresh: 캐시 무시하고 강제 새로고침
    
    Returns:
        고시금액 (원 단위), 항상 값 반환
    """
    crawler = get_notice_amount_crawler()
    return crawler.get_notice_amount(force_refresh=force_refresh)

