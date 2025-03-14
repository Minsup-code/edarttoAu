# ----------------------------
# [기본 환경 설정]
# ----------------------------

DEFAULT_SYMBOL = "ETH_USDT"

# 목표 거래량 예시 (4,200,000 USDT)
GOAL_VOLUME_1 = 4_200_000
GOAL_VOLUME_2 = 7_000_000
GOAL_VOLUME_3 = 12_000_000
GOAL_VOLUME_4 = 14_000_000

# EMA 파라미터
EMA_SHORT = 1
EMA_MID = 3
EMA_LONG = 7

# 변동성 기준: ±0.05% => 0.0005
PRICE_THRESHOLD = 0.0005

# 심볼별 최소 거래 단위 설정 (floor 처리용) 
MIN_TRADE_AMOUNT = {
    "BTC_USDT": 0.0001,
    "ETH_USDT": 0.01,
    "SOL_USDT": 0.1,
    "XRP_USDT": 1
}

# ----------------------------
# [Selenium 브라우저 설정]
# ----------------------------
SELENIUM_HEADLESS = False
ORDER_CLICK_DELAY = 0.1
MAX_ORDER_RETRY = 3

# ----------------------------
# [안티봇 (무작위 딜레이 등)]
# ----------------------------
MIN_RANDOM_DELAY = 0.2
MAX_RANDOM_DELAY = 1.2
LONG_REST_EVERY_N_ORDERS = 10
MIN_LONG_REST_SEC = 30
MAX_LONG_REST_SEC = 60

UID_AUTH_REQUIRED = True

# ----------------------------
# [PyInstaller / 난독화]
# ----------------------------
# (실전 배포시 main.py를 파이인스톨러로 빌드:
#  $ pyinstaller --onefile main.py
#  $ pyarmor obfuscate main.py
# )
