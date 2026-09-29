import asyncio
import json
import base64
import httpx
from playwright.async_api import async_playwright

async def download_image_as_base64(url: str) -> str:
    """
    httpx를 사용하여 비동기로 이미지를 다운로드하고 메모리 상에서 Base64로 인코딩합니다.
    """
    async with httpx.AsyncClient() as client:
        try:
            # 타임아웃을 넉넉히 주어 고화질 이미지를 안정적으로 다운로드
            response = await client.get(url, timeout=15.0)
            response.raise_for_status()
            encoded = base64.b64encode(response.content).decode("utf-8")
            return encoded
        except Exception as e:
            print(f"Failed to download or encode image from {url}: {e}")
            return ""

async def scrape_daangn_item(url: str) -> dict:
    """
    당근마켓 URL을 받아 본문 텍스트와 이미지 URL, 그리고 Base64 인코딩된 이미지를 추출합니다.
    """
    scraped_data = {
        "url": url,
        "title": "",
        "price": "",
        "description": "",
        "images": [],
        "images_base64": []
    }

    async with async_playwright() as p:
        # 1. 브라우저 실행 (안티봇 우회 옵션 적용)
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # [선택사항] 2. 네트워크 응답 가로채기 (Remix API JSON 데이터 확보용)
        # async def handle_response(response):
        #     if "json" in response.headers.get("content-type", ""):
        #         # 여기서 당근 내부 API 응답을 파싱할 수 있습니다.
        #         pass
        # page.on("response", handle_response)

        # 3. 페이지 이동 및 대기
        # 당근마켓 상품 페이지 접근 시 충분한 로딩 대기
        await page.goto(url, wait_until="networkidle", timeout=15000)

        # 4. 데이터 추출 (DOM 기반 안전한 추출)
        try:
            # 제목 추출 (CSS: #article-title 또는 h1)
            title_locator = page.locator("#article-title, h1").first
            if await title_locator.count() > 0:
                scraped_data["title"] = await title_locator.inner_text(timeout=3000)
            else:
                scraped_data["title"] = await page.title()
        except Exception:
            scraped_data["title"] = await page.title()

        try:
            # 가격 추출 (CSS: #article-price 또는 가격 관련 태그)
            price_locator = page.locator("#article-price, [id*='price']").first
            if await price_locator.count() > 0:
                scraped_data["price"] = await price_locator.inner_text(timeout=3000)
        except Exception:
            pass

        try:
            # 본문 추출 (CSS: #article-detail 또는 article 본문 영역)
            desc_locator = page.locator("#article-detail, #article-description, article p").first
            if await desc_locator.count() > 0:
                scraped_data["description"] = await desc_locator.inner_text(timeout=3000)
        except Exception:
            pass

        # 5. 이미지 원본 URL 추출
        try:
            image_urls = []
            img_elements = await page.locator("img").all()
            for img in img_elements:
                src = await img.get_attribute("src")
                # gcp-karroter.net 또는 daangn 이미지 도메인 필터링
                if src and ("gcp-karroter.net/origin/article" in src or "dnvefa72aowie.cloudfront.net" in src):
                    if src not in image_urls:
                        image_urls.append(src)
            scraped_data["images"] = image_urls

            # 6. 이미지 URL들을 httpx를 사용해 메모리 상에서 Base64로 인코딩
            if image_urls:
                print(f"[{len(image_urls)}개] 이미지 다운로드 및 Base64 인코딩 중...")
                base64_tasks = [download_image_as_base64(img_url) for img_url in image_urls]
                scraped_data["images_base64"] = await asyncio.gather(*base64_tasks)
        except Exception as e:
            print(f"Error during image processing: {e}")
        finally:
            await browser.close()

    return scraped_data

import sys

# 실행 테스트
if __name__ == "__main__":
    # 커맨드라인 인자로 URL을 받습니다. 없으면 기본 예시 URL을 사용합니다.
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
    else:
        # 가상의 URL 대신 웹에 존재하는 실제 당근마켓 글 URL 예시를 넣었습니다. (만료될 수 있음)
        test_url = "https://www.daangn.com/articles/861219665"
        print(f"⚠️ URL이 지정되지 않아 기본 예시 URL로 테스트를 진행합니다: {test_url}")
        print("💡 팁: 터미널에서 실행할 때 URL을 직접 입력할 수 있습니다.")
        print("예시: python daangn_scraper.py https://www.daangn.com/articles/당근마켓글번호\n")
    
    print(f"[{test_url}] 스크래핑을 시작합니다...")
    result = asyncio.run(scrape_daangn_item(test_url))
    
    # 결과 출력 (Base64 데이터는 너무 길어서 콘솔에서는 일부만 출력하도록 처리)
    result_for_print = result.copy()
    result_for_print["images_base64"] = [
        b64[:30] + "...(truncated)" if b64 else "FAILED"
        for b64 in result.get("images_base64", [])
    ]
    print(json.dumps(result_for_print, ensure_ascii=False, indent=2))
