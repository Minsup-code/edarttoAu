# ----------------------------------------------------
# ema_live_printer.py
#  - MEXC REST Polling(실시간-like)으로 들어오는 현재가와,
#  - TradingStrategy를 이용해 계산된 ema1, ema2, ema3 값을
#    계속 프린트해주는 단일 스크립트
# ----------------------------------------------------

import time
import sys
from loguru import logger

# core 폴더의 Strategy, PollingFeed를 import (폴더 구조에 맞게 수정)
from core.strategy import TradingStrategy
from core.websocket_feed import MexcRestPollingFeed

# ----------------------------------------------------
# [1] 콜백 함수: 실시간 시세를 받아 EMA 업데이트 & 화면 출력
# ----------------------------------------------------
def on_data_received(data_dict, strategy: TradingStrategy):
    """
    MexcRestPollingFeed로부터 받은 데이터:
      data_dict = {
        "lastPrice": float or None,
        "deals": [...],
        "kline": [...]
      }
    """
    last_price = data_dict.get("lastPrice")
    if last_price is None:
        return

    # (1) Strategy에 현재가 전달 -> 내부적으로 ema1, ema2, ema3 갱신
    strategy.on_new_price(float(last_price))

    # (2) 최신 EMA들을 화면에 프린트
    #     (Strategy에서 ema1, ema2, ema3가 public 속성이라 직접 참조)
    ema1 = getattr(strategy, "ema1", None)
    ema2 = getattr(strategy, "ema2", None)
    ema3 = getattr(strategy, "ema3", None)

    logger.info(
        f"[시세] last_price={last_price:.4f} | "
        f"EMA1={ema1:.4f}, EMA2={ema2:.4f}, EMA3={ema3:.4f}"
    )

# ----------------------------------------------------
# [2] 메인 함수
# ----------------------------------------------------
def main():
    # 터미널 인자 등으로 심볼을 받거나, 기본값 사용
    if len(sys.argv) > 1:
        symbol = sys.argv[1]
    else:
        symbol = "BTC_USDT"  # 기본 심볼

    logger.info(f"=== 실시간 EMA 프린터 시작 (심볼={symbol}) ===")

    # (1) Strategy 초기화
    strategy = TradingStrategy(symbol=symbol)

    # (2) REST 폴링 피드 시작
    feed = MexcRestPollingFeed(
        symbol=symbol,
        on_data_callback=lambda data: on_data_received(data, strategy),
        poll_interval=1.0,    # 1초 간격으로 호출 (원하는 값으로 조정 가능)
        kline_interval="Min1" # K라인 주기 (필요 시 변경)
    )
    feed.start()

    try:
        # (3) Ctrl + C를 누를 때까지 무한 대기
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("사용자 종료(Ctrl + C).")
    finally:
        # (4) 종료 시 폴링 스레드 중단
        feed.stop()
        logger.info("=== 프로그램 종료 ===")

# ----------------------------------------------------
# [Entry Point]
# ----------------------------------------------------
if __name__ == "__main__":
    main()
