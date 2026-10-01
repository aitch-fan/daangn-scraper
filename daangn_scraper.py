import asyncio
import json
import base64
import httpx
import os
import sys
import csv
import re
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
from pydantic import BaseModel

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==============================================================================
# Gemini API 키 설정 파일 경로
# ==============================================================================
API_KEY_FILE = "api_key.txt"

def load_or_prompt_api_key() -> str:
    """
    1) 환경 변수(GEMINI_API_KEY) 확인
    2) api_key.txt 파일 확인
    3) 없으면 사용자에게 터미널에서 입력받아 api_key.txt 파일로 자동 저장
    """
    # 1. 환경변수 확인
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key and env_key != "여기에_GEMINI_API_키를_입력하세요":
        return env_key

    # 2. api_key.txt 파일 확인
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key and key != "여기에_GEMINI_API_키를_입력하세요":
                    return key
        except Exception:
            pass

    # 3. 없으면 사용자에게 직접 입력받아 저장
    print("\n" + "=" * 60)
    print("🔑 Gemini API 키가 설정되지 않았습니다. (최초 1회 설정)")
    print("💡 입력하신 키는 api_key.txt 파일에 자동 저장되어 다음부터는 묻지 않습니다.")
    print("=" * 60)
    
    while True:
        try:
            user_key = input("👉 Gemini API 키를 입력해주세요: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n프로그램을 종료합니다.")
            sys.exit(0)
            
        if user_key:
            try:
                with open(API_KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(user_key)
                print(f"✅ API 키가 '{API_KEY_FILE}'에 저장되었습니다.\n")
                return user_key
            except Exception as e:
                print(f"⚠️ API 키 저장 실패: {e}")
                return user_key
        else:
            print("❌ API 키가 입력되지 않았습니다. 다시 입력해주세요.")

# Gemini 응답 형식을 강제하기 위한 Pydantic 모델
class DaangnItemDetail(BaseModel):
    model: str  # "15", "16", "15p", "16p" 중 하나
    price: str  # 숫자만 (원, 쉼표 제외)
    capacity: str  # 숫자만 (GB 제외)
    battery: str  # 숫자만 (% 제외)
    front_damage: int  # 전면액정: 0(무하자), 1(작은 하자), 2(중대한 하자), 3(사용불가)
    back_damage: int   # 후면액정: 0(무하자), 1(작은 하자), 2(중대한 하자), 3(사용불가)
    side_damage: int   # 측면파손: 0(무하자), 1(작은 하자), 2(중대한 하자), 3(사용불가)
    box: int  # 박스여부: 1(있음), 0(없음)
    third_party_repair: int  # 사설수리여부: 1(사설수리 기록/언급 있음), 0(사설수리 없음/언급없음)
    note: str  # 비고 (색상, 거래방식, 특이사항 요약)

def sanitize_data(data: dict, scraped_price: str = "") -> dict:
    """
    Gemini 응답 데이터를 사용자 지정 규칙(숫자만, 코드화)에 맞게 검증 및 정제합니다.
    """
    # 1. 모델: 15, 16, 15p, 16p 정규화
    raw_model = str(data.get("model", "")).lower().replace(" ", "")
    if "16p" in raw_model or "16프로" in raw_model or "16pro" in raw_model:
        data["model"] = "16p"
    elif "15p" in raw_model or "15프로" in raw_model or "15pro" in raw_model:
        data["model"] = "15p"
    elif "16" in raw_model:
        data["model"] = "16"
    elif "15" in raw_model:
        data["model"] = "15"
    else:
        data["model"] = raw_model

    # 2. 가격: 원, 쉼표 등 제거하고 숫자만
    price_val = str(data.get("price") or scraped_price or "")
    data["price"] = re.sub(r'[^0-9]', '', price_val)

    # 3. 용량: GB 등 제거하고 숫자만
    data["capacity"] = re.sub(r'[^0-9]', '', str(data.get("capacity", "")))

    # 4. 배터리: % 등 제거하고 숫자만
    data["battery"] = re.sub(r'[^0-9]', '', str(data.get("battery", "")))

    # 5. 파손 상태 클램프 (0~3)
    for field in ["front_damage", "back_damage", "side_damage"]:
        try:
            val = int(data.get(field, 0))
            data[field] = max(0, min(3, val))
        except (ValueError, TypeError):
            data[field] = 0

    # 6. 박스 & 사설수리 (0 또는 1)
    for field in ["box", "third_party_repair"]:
        try:
            val = int(data.get(field, 0))
            data[field] = 1 if val >= 1 else 0
        except (ValueError, TypeError):
            data[field] = 0

    return data

def analyze_with_gemini(scraped_data: dict) -> dict:
    """
    수집된 텍스트와 이미지를 Gemini API로 분석하여 정형화된 데이터를 반환합니다.
    분석 실패 시 None을 반환합니다.
    """
    prompt = """
    당근마켓 게시글의 제목, 가격, 본문, 사진을 분석하여 아이폰 상태 정보를 추출해주세요.
    
    [추출 및 서식 규칙]
    1. model: 대상 모델은 아이폰 15, 16, 15 프로, 16 프로 4종류입니다.
       - 아이폰 15 / 15 플러스 -> "15"
       - 아이폰 16 / 16 플러스 -> "16"
       - 아이폰 15 프로 / 15 프로맥스 -> "15p"
       - 아이폰 16 프로 / 16 프로맥스 -> "16p"
    2. price: '원'과 쉼표(,)를 제외한 순수 숫자만 추출 (예: 1000000, 500000). 모를 경우 빈 문자열.
    3. capacity: 'GB' 등을 제외한 숫자만 추출 (예: 128, 256, 512, 1024). 모를 경우 빈 문자열.
    4. battery: '%'를 제외한 배터리 최대 효율 숫자만 추출 (예: 100, 80). 모를 경우 빈 문자열.
    5. 파손상태 평가 (0~3 정수):
       - 0: 무하자 (기스/흠집/파손 일절 없음, 미사용 새상품 또는 S급)
       - 1: 작은 하자 (미세 기스, 생활 흠집, 테두리 작은 찍힘)
       - 2: 중대한 하자 (화면 줄감, 멍, 파손, 심한 찍힘, 액정 금)
       - 3: 사용이 불가능한 하자 (터치 불량, 화면 미출력, 완전 파손)
       위 기준에 따라 아래 3개 항목 각각 평가:
       - front_damage: 전면액정 상태 (0, 1, 2, 3 중 정수)
       - back_damage: 후면액정/뒷판 상태 (0, 1, 2, 3 중 정수)
       - side_damage: 측면/테두리 파손 상태 (0, 1, 2, 3 중 정수)
    6. box: 박스 유무. 박스가 있으면 1, 없으면 0.
    7. third_party_repair: 사설 수리 여부. 사설 수리 이력이 있거나 '알 수 없는 부품' 알림이 있으면 1, 없거나 정품 수리/수리이력 없음이면 0.
    8. note: 비고 (색상, 구성품, 직거래 위치/일정 등 핵심 특이사항 요약).
    """
    
    contents = [prompt]
    contents.append(f"제목: {scraped_data.get('title', '')}")
    if scraped_data.get('price'):
        contents.append(f"가격: {scraped_data.get('price')}")
    contents.append(f"본문: {scraped_data.get('description', '')}")
    
    # 분석 속도 및 비용 최적화를 위해 이미지는 최대 3장까지만 전달
    for b64 in scraped_data.get("images_base64", [])[:3]:
        if b64:
            # Base64 문자열을 바이트로 변환하여 새 SDK에 전달
            image_bytes = base64.b64decode(b64)
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            )
            
    api_key = load_or_prompt_api_key()
    if not api_key:
        print("\n❌ Gemini API 키가 없어 분석을 진행할 수 없습니다.")
        return None

    client = genai.Client(api_key=api_key)

    import time
    candidate_models = ['gemini-3-flash-preview', 'gemini-3.8-flash']
    for model_name in candidate_models:
        for attempt in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DaangnItemDetail,
                    ),
                )
                data = json.loads(response.text)
                # 데이터 포맷 검증 및 정제 적용
                data = sanitize_data(data, scraped_data.get("price", ""))
                return data
            except Exception as e:
                print(f"[{model_name}][{attempt}/2] Gemini API 호출 오류: {e}")
                time.sleep(2 * attempt)

    print("❌ Gemini API 분석에 최종 실패했습니다.")
    return None

def save_to_csv(data: dict, article_id: str, csv_path="daangn_items.csv"):
    """
    분석된 데이터를 CSV 파일의 마지막 줄에 추가합니다.
    """
    file_exists = os.path.isfile(csv_path) and os.path.getsize(csv_path) > 0
    
    with open(csv_path, mode="a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        # 파일이 처음 생성되거나 비어있는 경우 헤더 작성
        if not file_exists:
            writer.writerow([
                "모델", "가격", "용량", "배터리효율", 
                "전면액정", "후면액정", "측면파손", 
                "박스여부", "사설수리여부", "비고", "게시물번호"
            ])
        
        # 데이터 행 작성
        writer.writerow([
            data.get("model", ""),
            data.get("price", ""),
            data.get("capacity", ""),
            data.get("battery", ""),
            data.get("front_damage", 0),
            data.get("back_damage", 0),
            data.get("side_damage", 0),
            data.get("box", 0),
            data.get("third_party_repair", 0),
            data.get("note", ""),
            article_id
        ])
    print(f"✅ 결과가 CSV 파일({csv_path})에 성공적으로 저장되었습니다.")

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
            # 가격 추출 (CSS: 구버전 #article-price 또는 신버전 article h3)
            price_locator = page.locator("#article-price, [id*='price']").first
            if await price_locator.count() > 0:
                scraped_data["price"] = await price_locator.inner_text(timeout=3000)
            else:
                h3_price = page.locator("article h3").first
                if await h3_price.count() > 0:
                    scraped_data["price"] = await h3_price.inner_text(timeout=3000)
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

# 메인 실행부
if __name__ == "__main__":
    initial_url = sys.argv[1].strip() if len(sys.argv) > 1 else None

    print("=" * 60)
    print("🥕 당근마켓 아이폰 정보 추출기")
    print("💡 당근마켓 상품 URL을 입력하면 분석 후 CSV에 자동 저장됩니다.")
    print("💡 프로그램을 종료하려면 'c'를 입력하세요.")
    print("=" * 60)

    while True:
        if initial_url:
            user_input = initial_url
            initial_url = None  # 첫 인자 처리 후 초기화
        else:
            try:
                user_input = input("\n🔗 당근마켓 상품 URL을 입력해주세요 (종료: c): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n프로그램을 종료합니다.")
                break

        if not user_input:
            continue

        # 종료 조건 ('c' 입력 시 종료)
        if user_input.lower() in ["c", "q", "exit", "quit"]:
            print("👋 프로그램을 종료합니다.")
            break

        target_url = user_input

        print(f"\n[{target_url}] 스크래핑을 시작합니다...")
        try:
            # 1. 당근마켓 게시글 스크래핑
            scraped_data = asyncio.run(scrape_daangn_item(target_url))
            
            # 2. Gemini API로 정형 데이터 추출
            print("\n🤖 Gemini API로 데이터 분석 중...")
            analyzed_data = analyze_with_gemini(scraped_data)
            
            # 분석 실패 또는 정보가 없는 경우 CSV에 저장하지 않음
            if not analyzed_data or not analyzed_data.get("model"):
                print("\n⚠️ 분석 정보가 없거나 분석에 실패하여 CSV 파일에 기록하지 않습니다.")
            else:
                print("\n[분석 완료]")
                print(json.dumps(analyzed_data, ensure_ascii=False, indent=2))
                
                # 3. URL에서 게시물 번호 추출 (파라미터 제거 후 경로의 마지막 부분 추출)
                parsed_path = urlparse(target_url).path.rstrip("/")
                article_id = parsed_path.split("/")[-1] if parsed_path else ""
                
                # 4. CSV 파일에 저장 (한 행 추가)
                save_to_csv(analyzed_data, article_id)
        except Exception as e:
            print(f"❌ 처리 중 예기치 않은 오류가 발생했습니다: {e}")
