from typing import Dict, List
import numpy as np
from .baseStrategy import BaseStrategy

class CounterTrendStrategy(BaseStrategy):
    def __init__(self, parameters: Dict):
        print(parameters)
        self.ticker = parameters.get('tickers', [])[0]
        self.kValue = float(parameters.get('kValue', 2.2))
        self.nDays = int(parameters.get('nDays', 20))
    
    async def calculate_signals(self):
        candles = []
        candleswithoutrecent = candles[2:]
        ranges = [candle['high_price'] - candle['low_price'] for candle in candleswithoutrecent]
        avgRange = np.mean(ranges)
        prevHigh = candles[1]['high_price']
        longHitLevel = prevHigh - self.kValue * avgRange
        currentPrice = candles[0]['trade_price']

        prevLow = candles[1]['low_price']
        shortHitLevel = prevLow + self.kValue * avgRange

        if(currentPrice < longHitLevel):
            return {"signal": "long", "message": "will close long position tomorrow"}
        elif(currentPrice > shortHitLevel):
            return {"signal": "short", "message": "will close short position tomorrow"}
        else:
            return {"signal": "hold", "message": "no action"}



