"""
웹 크롤링 도구

CrewAI Agent가 웹 페이지를 크롤링할 수 있도록 하는 Tool입니다.
"""

import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict, Any
import logging
from urllib.parse import urljoin, urlparse
import time
import json

from crewai_tools import tool

logger = logging.getLogger(__name__)

# User-Agent 설정 (봇 차단 방지)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


@tool("웹 페이지 크롤링 도구")
def crawl_web_page(url: str, extract_text: bool = True, extract_links: bool = False) -> str:
    """
    웹 페이지를 크롤링하여 내용을 추출합니다.
    
    Args:
        url: 크롤링할 웹 페이지 URL
        extract_text: 텍스트 추출 여부 (기본값: True)
        extract_links: 링크 추출 여부 (기본값: False)
    
    Returns:
        크롤링된 내용 (JSON 형식 문자열)
    """
    try:
        # URL 유효성 검사
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return f"❌ 잘못된 URL 형식: {url}"
        
        # HTTP 요청
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        
        # 인코딩 확인
        if response.encoding is None:
            response.encoding = 'utf-8'
        
        # HTML 파싱
        soup = BeautifulSoup(response.content, 'html.parser')
        
        result = {
            "url": url,
            "status_code": response.status_code,
            "title": "",
            "text": "",
            "links": []
        }
        
        # 제목 추출
        title_tag = soup.find('title')
        if title_tag:
            result["title"] = title_tag.get_text(strip=True)
        
        # 텍스트 추출
        if extract_text:
            # 스크립트와 스타일 태그 제거
            for script in soup(["script", "style", "meta", "link"]):
                script.decompose()
            
            # 본문 텍스트 추출
            text = soup.get_text(separator='\n', strip=True)
            # 연속된 공백 제거
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            result["text"] = '\n'.join(lines[:1000])  # 최대 1000줄로 제한
        
        # 링크 추출
        if extract_links:
            links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                text = link.get_text(strip=True)
                # 상대 URL을 절대 URL로 변환
                absolute_url = urljoin(url, href)
                links.append({
                    "url": absolute_url,
                    "text": text
                })
            result["links"] = links[:50]  # 최대 50개 링크
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"웹 크롤링 요청 실패: {str(e)}")
        return f"❌ 웹 크롤링 실패: {str(e)}"
    except Exception as e:
        logger.error(f"웹 크롤링 중 오류 발생: {str(e)}")
        return f"❌ 오류 발생: {str(e)}"


@tool("여러 웹 페이지 크롤링 도구")
def crawl_multiple_pages(urls: str, extract_text: bool = True) -> str:
    """
    여러 웹 페이지를 순차적으로 크롤링합니다.
    
    Args:
        urls: 크롤링할 URL 목록 (쉼표로 구분된 문자열 또는 JSON 배열 문자열)
        extract_text: 텍스트 추출 여부 (기본값: True)
    
    Returns:
        크롤링된 내용들 (JSON 형식 문자열)
    """
    try:
        # URL 목록 파싱
        if urls.strip().startswith('['):
            # JSON 배열 형식
            url_list = json.loads(urls)
        else:
            # 쉼표로 구분된 문자열
            url_list = [url.strip() for url in urls.split(',') if url.strip()]
        
        if not url_list:
            return "❌ URL 목록이 비어있습니다."
        
        results = []
        for i, url in enumerate(url_list[:10], 1):  # 최대 10개 URL
            logger.info(f"크롤링 중 ({i}/{len(url_list)}): {url}")
            
            # 각 페이지 크롤링
            result = crawl_web_page(url, extract_text=extract_text, extract_links=False)
            
            try:
                # JSON 파싱 시도
                result_dict = json.loads(result)
                results.append(result_dict)
            except:
                # JSON이 아니면 텍스트로 추가
                results.append({"url": url, "error": result})
            
            # 요청 간 딜레이 (서버 부하 방지)
            if i < len(url_list):
                time.sleep(1)
        
        return json.dumps({
            "total": len(results),
            "results": results
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"여러 페이지 크롤링 중 오류 발생: {str(e)}")
        return f"❌ 오류 발생: {str(e)}"


@tool("특정 요소 크롤링 도구")
def crawl_specific_elements(url: str, selector: str) -> str:
    """
    CSS 선택자나 태그명으로 특정 요소만 크롤링합니다.
    
    Args:
        url: 크롤링할 웹 페이지 URL
        selector: CSS 선택자 또는 태그명 (예: "div.content", "h1", "#main")
    
    Returns:
        선택된 요소들의 내용 (JSON 형식 문자열)
    """
    try:
        # URL 유효성 검사
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return f"❌ 잘못된 URL 형식: {url}"
        
        # HTTP 요청
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        
        # HTML 파싱
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 선택자로 요소 찾기
        elements = soup.select(selector)
        
        if not elements:
            return json.dumps({
                "url": url,
                "selector": selector,
                "found": 0,
                "elements": []
            }, ensure_ascii=False)
        
        results = []
        for elem in elements[:20]:  # 최대 20개 요소
            results.append({
                "tag": elem.name,
                "text": elem.get_text(strip=True),
                "html": str(elem)[:500]  # 최대 500자
            })
        
        return json.dumps({
            "url": url,
            "selector": selector,
            "found": len(elements),
            "elements": results
        }, ensure_ascii=False, indent=2)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"웹 크롤링 요청 실패: {str(e)}")
        return f"❌ 웹 크롤링 실패: {str(e)}"
    except Exception as e:
        logger.error(f"요소 크롤링 중 오류 발생: {str(e)}")
        return f"❌ 오류 발생: {str(e)}"


def get_crawler_tools():
    """크롤링 도구 목록 반환"""
    return [crawl_web_page, crawl_multiple_pages, crawl_specific_elements]

