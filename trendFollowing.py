from typing import Dict, List
import numpy as np
from .baseStrategy import BaseStrategy

class TrendFollowingStrategy(BaseStrategy):
    def __init__(self, parameters: Dict):
        self.volatilityWindow = parameters.get('volatility_window', 20)
        self.volatilities = []
        self.tickers = parameters.get('tickers', [])
        self.trendType = parameters.get('trendType', 'sma')
        self.alpha = parameters.get('alpha', 0.1)
        self.prevShortEma = 0
        self.prevLongEma = 0
        self.prevNHigh = float('inf')
        self.prevNLow = float('-inf')
        print(parameters)

        if(self.trendType == 'breakout'): # breakout 전략
            self.nDays = int(parameters.get('nDays', 20))
        else: # sma, ema 전략
            self.shortWindow = int(parameters.get('shortPeriod', 20))
            self.longWindow = int(parameters.get('longPeriod', 50))
        
    def calculate_signals(self):
        if(self.trendType == 'breakout'):
            return self.calculate_breakout_signals()
        elif(self.trendType == 'sma'):
            return self.set_sma()
        elif(self.trendType == 'ema'):
            return self.set_ema()
        else:
            return {}
        
    async def set_n_high_low(self):
        candles = []
        for ticker in self.tickers:
            candles.extend(candles_from_api)
        candleswithoutrecent = candles[1:]
        self.prevNHigh = max(candleswithoutrecent, key=lambda x: x['high_price'])['high_price']
        self.prevNLow = min(candleswithoutrecent, key=lambda x: x['low_price'])['low_price']
        
        current_candle = await self.upbitService.get_daily_candles(ticker, 1)
        current_price = current_candle[0]['trade_price']
        if(self.prevNHigh == float('inf')):
            return {}
        elif(self.prevNLow == float('-inf')):
            return {}
        elif(self.prevNHigh <= current_price):
            return {"signal": "buy"}
        elif(self.prevNLow >= current_price):
            return {"signal": "sell"}
        else:
            return {"signal": "hold", "message":f"will buy or sell if current price is higher than {self.prevNHigh} or lower than {self.prevNLow} current price is {current_price}"}
        
    def calculate_breakout_signals(self):
        return self.set_n_high_low()
    
    async def set_sma(self):
        candles = []
        for ticker in self.tickers:
            candles_from_api = await self.upbitService.get_daily_candles(ticker, self.longWindow + 1)
            candles.extend(candles_from_api)
        candleswithoutrecent = candles[1:]
        closes = [candle['trade_price'] for candle in candleswithoutrecent]
        shortSma = np.mean(closes[-self.shortWindow:])
        longSma = np.mean(closes[-self.longWindow:])
        if(shortSma >= longSma):
            return {"signal": "long", "message": "will close long position tomorrow"}
        else:
            return {"signal": "short", "message": "will close short position tomorrow"}

    async def set_ema(self):
        candles = []
        for ticker in self.tickers:
            candles_from_api = await self.upbitService.get_daily_candles(ticker, self.longWindow+1)
            candles.extend(candles_from_api)
        candleswithoutrecent = candles[1:]
        closes = [candle['trade_price'] for candle in candleswithoutrecent]
        
        if(self.prevShortEma == 0):
            firstShortEma = np.mean(closes[-self.shortWindow:])
            self.prevShortEma = firstShortEma
        if(self.prevLongEma == 0):
            firstLongEma = np.mean(closes[-self.longWindow:])
            self.prevLongEma = firstLongEma
        

        shortEma = (closes[-1] - self.prevShortEma) * self.alpha + self.prevShortEma
        longEma = (closes[-1] - self.prevLongEma) * self.alpha + self.prevLongEma
        if(shortEma > longEma):
            return {"signal": "buy"}
        else:
            return {"signal": "sell"}