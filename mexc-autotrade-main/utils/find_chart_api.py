import re
import asyncio
import json
from playwright.async_api import async_playwright

# "실시간 가격"으로 보이는 URL만 필터링할 키워드 예시
REALTIME_KEYWORDS = re.compile(r"ticker|deal|trade|price", re.IGNORECASE)

# 최대 몇 바이트까지 전체를 저장할지 설정 (너무 크면 잘라냄)
MAX_SAVE_SIZE = 3000  

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # URL:응답 데이터를 담아둘 딕셔너리
        realtime_price_responses = {}

        # ----- 응답(Response) 이벤트 콜백 함수 정의 -----
        async def handle_response(response):
            """응답 내용을 받아서 실시간 가격 관련이면 저장."""
            url = response.url
            # URL에 REALTIME_KEYWORDS가 있는지 확인
            if REALTIME_KEYWORDS.search(url):
                try:
                    # 먼저 MIME 타입 등으로 JSON 여부를 간단 체크
                    content_type = response.headers.get("content-type", "")
                    body_bytes = await response.body()

                    # 텍스트(UTF-8)로 변환 시도
                    # 큰 파일이거나 바이너리면 크기가 클 수 있으니 주의
                    try:
                        decoded_text = body_bytes.decode("utf-8", errors="replace")
                    except:
                        decoded_text = str(body_bytes)

                    # JSON 파싱 가능하면 처리
                    # 1) content-type에 "application/json"이 포함되어 있거나
                    # 2) 혹은 수동으로 JSON.loads 시도
                    parsed_json = None
                    if "application/json" in content_type.lower():
                        try:
                            parsed_json = json.loads(decoded_text)
                        except:
                            pass
                    else:
                        # content-type이 명시되어 있지 않아도 
                        # 그냥 json.loads를 시도해 볼 수 있음
                        try:
                            parsed_json = json.loads(decoded_text)
                        except:
                            pass

                    # 실제 저장할 최종 문자열
                    final_output = ""

                    if parsed_json is not None:
                        # 여기서는 일단 pretty-print 전체를 보여주되,
                        # 내용이 너무 크면 문자열 길이를 제한
                        pretty_json = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                        if len(pretty_json) > MAX_SAVE_SIZE:
                            # 너무 클 경우 잘라낸 뒤, 뒤에 "... (truncated)" 붙이기
                            pretty_json = pretty_json[:MAX_SAVE_SIZE] + "\n... (truncated)"
                        final_output = pretty_json
                    else:
                        # JSON이 아닐 경우, 텍스트 일부만 보여주기
                        if len(decoded_text) > MAX_SAVE_SIZE:
                            final_output = decoded_text[:MAX_SAVE_SIZE] + "\n... (truncated)"
                        else:
                            final_output = decoded_text

                    realtime_price_responses[url] = final_output
                    print(f"[실시간 가격 후보 URL]: {url}")
                except Exception as e:
                    print(f"[오류] 응답 바디 수집 중 오류가 발생했습니다: {e}")

        # 응답 이벤트를 비동기로 처리하도록 설정
        page.on("response", lambda r: asyncio.create_task(handle_response(r)))

        # 페이지 이동
        await page.goto("https://futures.mexc.com/ko-KR/exchange/ETH_USDT")
        
        # 추가 비동기 요청 대기를 위해 약간의 시간 대기
        await asyncio.sleep(10)
        
        # 브라우저 종료
        await browser.close()

        # 수집된 URL과 응답 데이터를 파일에 저장
        with open("realtime_price_candidates.txt", "w", encoding="utf-8") as f:
            for url, data in realtime_price_responses.items():
                f.write(f"### URL: {url}\n")
                f.write(data)
                f.write("\n\n" + "="*80 + "\n\n")

        print("실시간 가격 관련 URL 및 응답(구조 파악 가능 형태)을 'realtime_price_candidates.txt'에 저장했습니다.")

if __name__ == "__main__":
    asyncio.run(main())
