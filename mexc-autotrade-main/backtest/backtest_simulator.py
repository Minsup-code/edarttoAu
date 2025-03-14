import csv
import os
from loguru import logger
from core.strategy import TradingStrategy

"""
백테스트 시뮬레이터 예시:
- CSV (datetime, open, high, low, close, volume) 포맷
- 종가만 읽어 strategy.on_new_price(close) 호출
"""

# 시세 데이터를 저장해둘 CSV 파일 경로 (예: btc_1m.csv)
CSV_FILE = os.path.join("backtest", "data", "btc_1m.csv")

class BacktestSimulator:
    def __init__(self, csv_file=CSV_FILE):
        self.csv_file = csv_file
        self.strategy = TradingStrategy()
        # 백테스트 시에는 실제 주문(OrderExecutor)이 필요 없으므로 None (또는 Mock) 할당
        self.strategy.set_order_executor(None)
        # TODO: 백테스트용 PositionTracker, RiskManager 등을 연결할 수도 있음.

    def run(self):
        if not os.path.exists(self.csv_file):
            logger.error(f"[BacktestSimulator] CSV 파일이 없습니다: {self.csv_file}")
            return

        logger.info(f"[BacktestSimulator] CSV 로드: {self.csv_file}")

        with open(self.csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row_count = 0
            for row in reader:
                row_count += 1
                # CSV에서 종가만 사용 (datetime, open, high, low 등은 생략)
                close_price = float(row["close"])
                # 새로운 종가가 들어올 때마다 전략 실행
                self.strategy.on_new_price(close_price)

        logger.info(f"[BacktestSimulator] 총 {row_count} 건 처리 완료.")
        # 예시) 최종 포지션 상태
        logger.info(
            f"[BacktestSimulator] 최종 포지션: long={self.strategy.long_size}, "
            f"short={self.strategy.short_size}"
        )

if __name__ == "__main__":
    sim = BacktestSimulator()
    sim.run()
