# MEXC 무손실 거래량 쌓기 자동매매 프로그램

MEXC 선물 거래에서 초단타 스캘핑을 반복하며 거래량을 많이 쌓고,  
“거의 무손실” 상태를 유지하여 M-Day 등 이벤트의 증정금, 레퍼럴 리베이트를 극대화하기 위한 자동매매 시스템입니다.

## 구성 요소

1. **메인 자동매매(main.py)**  
   - Selenium Stealth 브라우저를 통해 MEXC에 자동 로그인  
   - **프로그램 만료일(license_manager.py) 체크** 및 **UID 화이트리스트 인증(uid_auth.py)** 추가  
   - WebSocket을 통한 시세 수신 → `strategy.py`의 매매전략 실행 → `order_executor.py`로 주문 실행  
   - `risk_manager.py`를 통해 팝업창 닫기, 일정 시간 휴식, 세션 만료 시 재로그인 등의 안티봇 기능 수행  
   - 교차 모드/레버리지 자동 설정 등 추가 기능 포함  
   - 매일 15:00에 누적 거래량을 0으로 리셋하는 로직 포함  

2. **백테스트(backtest_simulator.py)**  
   - 로컬 CSV 파일의 시세 데이터를 불러와 매매전략(`strategy.py`)을 적용하는 간단한 시뮬레이터  
   - CSV 예시 형식: `datetime,open,high,low,close,volume` (현재는 `close`만 사용)  

3. **환경 설정(config & secrets)**  
   - `config/config.py` : 프로젝트 전반 설정(심볼, 레버리지, 휴식 조건, 가격 변동성 기준 등)  
   - `config/secrets.py` : 민감 정보(MEXC API Key, 이메일·비밀번호, UID 화이트리스트 등)  
   - 예) `UID_AUTH_REQUIRED = True` → 프로그램 실행 시 UID 화이트리스트 인증 요구  

4. **코어 로직(core/)**  
   - **order_executor.py** : Selenium으로 MEXC 주문 버튼 클릭, 매매 씹힘 시 재시도  
   - **position_tracker.py** : 포지션/잔고 조회, 누적 거래량(Accumulated Volume) 파싱 (UI 기반)  
   - **risk_manager.py** : 팝업 닫기, 주기적 휴식, 목표 거래량 초과 시 매매 중단, 세션 만료 감지 후 자동 재로그인, 매일 15:00 거래량 리셋 등  
   - **strategy.py** : EMA(1,3,7) 기반 ±0.05% 변동으로 초단타 스캘핑 및 헷징  
   - **uid_auth.py** : 콘솔에서 UID 입력받아 화이트리스트 검증  
   - **websocket_feed.py** : Binance WebSocket을 이용해 1분봉 시세를 실시간으로 받아 `strategy`에 전달  

5. **유틸리티(utils/)**  
   - **db.py** : 로컬 JSON DB 예시  
   - **logger.py** : `loguru` 기반 로깅 설정  
   - **signer.py** : MEXC API 요청 시 HMAC-SHA256 서명 (필요 시)  
   - **license_manager.py** : 프로그램 만료일(`check_program_expiry`)과 UID 사용 가능 여부(`check_uid_valid`) 확인  

6. **웹 브라우저 자동화(web_selenium/browser_stealth.py)**  
   - `undetected-chromedriver` 기반으로 감지 위험을 줄인 브라우저 실행  
   - MEXC 자동 로그인(이메일/비밀번호), 교차모드/레버리지 50배 설정, 코인 단위 변경 등  
   - 팝업 닫기, 스텔스 옵션 등을 통해 봇 탐지를 최소화  

---

## 실행 방법

1. **Python 3.9+ 환경 준비**  
2. `requirements.txt` 내 라이브러리 설치  
3. `config/secrets.py`에서 MEXC 계정 정보(이메일·비밀번호, API Key)와 UID 화이트리스트, 만료일(선택)을 설정  
4. **메인 실행**  
   ```bash
   python main.py
   ```  
   - 실행 시 프로그램 만료일(`license_manager`) 확인 및 UID 화이트리스트 인증(콘솔 입력) 진행  
   - 심볼(BTC_USDT, ETH_USDT 등) 선택 후 운용 시드(USDT) 입력  
   - 브라우저가 자동 로그인 후 매매 시작  

5. **백테스트**  
   ```bash
   python backtest\backtest_simulator.py
   ```  
   - `backtest/data` 폴더 내 CSV 파일(예: `btc_1m.csv`)을 기반으로, `strategy.on_new_price()`를 순차 호출해 시뮬레이션  

6. **UI 기능 테스트(선택)**  
   ```bash
   python test_ui_flow.py
   ```  
   - MEXC 선물 페이지에서 직접 주문/청산 버튼 클릭이 정상 동작하는지 확인할 수 있는 스크립트  
   - 실제로 주문 체결이 발생하므로 테스트 시 유의  

---

## 파일 구조

```
mexc_autotrade/
├── README.md
├── backtest/
│   ├── data/
│   └── backtest_simulator.py
├── config/
│   ├── config.py
│   └── secrets.py
├── core/
│   ├── order_executor.py
│   ├── position_tracker.py
│   ├── risk_manager.py
│   ├── strategy.py
│   ├── uid_auth.py
│   └── websocket_feed.py
├── main.py
├── test_ui_flow.py
├── utils/
│   ├── db.py
│   ├── license_manager.py
│   ├── logger.py
│   └── signer.py
└── web_selenium/
    └── browser_stealth.py
```

---

## 요약

- **자동 로그인** : `browser_stealth.py`가 MEXC 페이지 접속 후 이메일/비밀번호 입력 및 재시도  
- **프로그램 만료일 & UID 인증** : `license_manager.py`(만료일) + `uid_auth.py`(화이트리스트)  
- **시세 수신** : `websocket_feed.py`에서 1분봉 시세 구독 후 `strategy.py`에 전달  
- **매매 전략** : `strategy.py`에서 EMA(1,3,7) + ±0.05% 변동으로 초단타 스캘핑 및 헷징  
- **주문 실행** : `order_executor.py` (Selenium으로 시장가/청산 버튼 클릭, 씹힘 방지 재시도)  
- **안티봇/휴식** : `risk_manager.py`가 팝업 닫기, 일정 주기 휴식, 목표 거래량 초과 시 매매 중단, 세션 만료 재로그인 등 담당  
- **백테스트** : `backtest_simulator.py`로 CSV를 통한 전략 시뮬레이션 가능  
- **UI 기능 테스트** : `test_ui_flow.py`로 주문/청산 버튼 클릭 테스트  