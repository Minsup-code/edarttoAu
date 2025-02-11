import time
from tradingview_ws import TradingViewWebSocket
from trading_strategy import TradingStrategy
from mexc_trader import MexcTrader
import config

class AutoTrader:
    def __init__(self):
        self.tv_ws = TradingViewWebSocket(config.SYMBOL)
        self.strategy = TradingStrategy()
        self.trader = MexcTrader()
        self.current_position = None  

    def start_trading(self):
        print(f"🚀 {config.SYMBOL} 자동매매 시작...")

        while True:
            data = self.tv_ws.data
            if not data:
                continue

            signal = self.strategy.check_signal(data)

            if signal and signal != self.current_position:
                self.trader.place_order(signal)
                self.current_position = signal
            
            elif self.current_position and signal != self.current_position:
                self.trader.close_position()
                self.current_position = None

            time.sleep(1)

if __name__ == "__main__":
    trader = AutoTrader()
    trader.start_trading()
