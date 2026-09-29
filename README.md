# 🥕 당근마켓 상품 정보 크롤러 (Daangn Market Scraper)

Playwright와 HTTPX를 이용해 당근마켓 상품 상세 페이지의 제목, 가격, 본문 텍스트 및 고화질 원본 이미지를 추출하고 Base64로 인코딩하는 비동기 크롤러입니다.

## 🚀 주요 기능
- **안티봇 우회**: AutomationControlled 플래그 비활성화 및 브라우저 환경 최적화
- **본문 및 메타데이터 추출**: 제목, 본문 설명, 가격 등 파싱
- **고화질 이미지 추출 & Base64 인코딩**: `httpx` 비동기 통신을 통해 이미지를 메모리 상에서 Base64로 즉시 변환

## 📦 설치 방법

```powershell
# 1. 가상환경 생성 및 활성화
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 의존성 패키지 설치
pip install -r requirements.txt

# 3. Playwright 브라우저 설치
playwright install chromium
```

## 🛠️ 사용 방법

```powershell
python daangn_scraper.py <당근마켓_상품_URL>
```

### 예시
```powershell
python daangn_scraper.py https://www.daangn.com/articles/1250699716?share=true
```
