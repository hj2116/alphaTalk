import requests 
import uuid 
from dotenv import load_dotenv
import json
import os
from quantTools import QuantTools, get_daily_candles
from fundamentalTools import FundamentalAnalyzer, analyze_fundamental
from newsTools import NewsAnalyzer, analyze_news
import yfinance as yf
import pandas as pd 
load_dotenv()
CLOVA_URL = "https://clovastudio.apigw.ntruss.com/testapp/v1" 
CLOVA_API_KEY = os.getenv("CLOVA_API_KEY")

# --- Prompts for Specialized Agents ---

QUANT_PROMPT = """
You are a specialized quantitative analyst AI. 
Your sole task is to provide key quantitative metrics for a given stock ticker.
Focus on data like PER, PBR, ROE, EPS growth, and key technical indicators.
Present the data in a clear, list-based format. Provide your opinion on the stock and give an appropritate price valuation. 
"""

FUNDAMENTAL_PROMPT = """
You are a specialized fundamental analyst AI.
You will receive comprehensive fundamental data for a stock ticker in a structured format.
Your task is to provide a qualitative analysis based on this data.

Focus on:
1. Business model strength and competitive positioning based on the financial metrics
2. Industry trends and sector analysis using the provided industry information
3. Financial health assessment using profitability and debt ratios
4. Growth prospects based on revenue trends and asset growth
5. Valuation assessment using PER/PBR in industry context
6. Risk factors including interest rate sensitivity and leverage
7. Investment quality assessment based on ROE, ROA, and momentum indicators

Present your analysis in clear, structured paragraphs. Include specific insights about:
- Company's competitive advantages or weaknesses revealed by the metrics
- Industry positioning relative to sector norms
- Financial strength or concerns
- Growth trajectory and sustainability
- Key risks and opportunities

Do NOT repeat the raw numbers - focus on interpreting what they mean for the business.
Provide actionable insights for investment decision-making.
Write in a professional, analytical tone suitable for investment research.
"""

NEWS_PROMPT = """
You are a specialized news analysis AI.
Your sole task is to find and summarize the most recent, impactful news for a given stock ticker.
Then, determine the overall sentiment (Positive, Neutral, Negative) of the news.
Present the key news items as a bulleted list and state the final sentiment. 
Provide your opinion on the stock and give an appropritate price valuation. 
"""

FINAL_PROMPT = """
You are a master investment analysis agent.
You have received reports from three specialized sub-agents: Quantitative, Fundamental, and News Analysis.
Your task is to synthesize these reports into a single, final investment recommendation.
Your output must include:
1.  A brief summary of each sub-agent's report.
2.  A final, reasoned investment decision (e.g., Strong Buy, Buy, Hold, Sell).
3.  The reasoning behind your decision, based on the provided reports.
Present the final report in a clear, structured format in Korean.
"""

# --- Core Functions ---

# def get_stock_fundamentals(ticker):
#     """주식의 기본 재무 지표를 가져옵니다."""
#     try:
#         stock = yf.Ticker(ticker)
#         info = stock.info
        
#         fundamentals = {
#             "company_name": info.get("longName", "N/A"),
#             "sector": info.get("sector", "N/A"),
#             "industry": info.get("industry", "N/A"),
#             "market_cap": info.get("marketCap", "N/A"),
#             "pe_ratio": info.get("trailingPE", "N/A"),
#             "pb_ratio": info.get("priceToBook", "N/A"),
#             "roe": info.get("returnOnEquity", "N/A"),
#             "eps": info.get("trailingEps", "N/A"),
#             "dividend_yield": info.get("dividendYield", "N/A"),
#             "beta": info.get("beta", "N/A"),
#             "52_week_high": info.get("fiftyTwoWeekHigh", "N/A"),
#             "52_week_low": info.get("fiftyTwoWeekLow", "N/A"),
#             "current_price": info.get("currentPrice", "N/A"),
#             "volume": info.get("volume", "N/A"),
#             "avg_volume": info.get("averageVolume", "N/A")
#         }
#         return fundamentals
#     except Exception as e:
#         print(f"Error getting fundamentals for {ticker}: {e}")
#         return {}

def get_technical_indicators(ticker, period="30d"):
    try:
        data = get_daily_candles(ticker, 30)
        if data.empty:
            return {}
        
        # 이동평균 계산
        data['MA5'] = data['Close'].rolling(window=5).mean()
        data['MA20'] = data['Close'].rolling(window=20).mean()
        
        # RSI 계산 (간단한 버전)
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        latest_data = data.iloc[-1]
        
        technical_data = {
            "current_price": latest_data['Close'],
            "ma5": latest_data['MA5'],
            "ma20": latest_data['MA20'],
            "rsi": rsi.iloc[-1] if not rsi.empty else "N/A",
            "volume": latest_data['Volume'],
            "high_52w": data['High'].max(),
            "low_52w": data['Low'].min(),
            "price_change_1d": ((latest_data['Close'] - data['Close'].iloc[-2]) / data['Close'].iloc[-2] * 100) if len(data) > 1 else "N/A"
        }
        
        return technical_data
    except Exception as e:
        print(f"Error calculating technical indicators for {ticker}: {e}")
        return {}

def run_quant_analysis(ticker):

    

    technical = get_technical_indicators(ticker)
    
    quant_tools = QuantTools()
    counter_trend_result = {}
    trend_following_result = {}
    
    try:
        counter_trend_result = quant_tools.getCounterTrendStrategy(ticker, kValue=2.0, nDays=30)
        print(f"Counter Trend Strategy: {counter_trend_result}")
    except Exception as e:
        print(f"Counter trend analysis error: {e}")
        counter_trend_result = {"error": str(e)}
    
    try:
        trend_following_result = quant_tools.getTrendFollowingStrategy(ticker, shortPeriod=5, longPeriod=20)
        print(f"Trend Following Strategy: {trend_following_result}")
    except Exception as e:
        print(f"Trend following analysis error: {e}")
        trend_following_result = {"error": str(e)}
    
    analysis_text = f"""
    === {ticker} 실시간 퀀트/기술적 분석 데이터 ===
    
    ## 기술적 지표
    - 현재가: {technical.get('current_price', 'N/A')}
    - 5일 이동평균: {technical.get('ma5', 'N/A')}
    - 20일 이동평균: {technical.get('ma20', 'N/A')}
    - RSI: {technical.get('rsi', 'N/A')}
    - 일일 변동률: {technical.get('price_change_1d', 'N/A')}%
    - 52주 최고가: {technical.get('high_52w', 'N/A')}
    - 52주 최저가: {technical.get('low_52w', 'N/A')}
    - 거래량: {technical.get('volume', 'N/A')}
    
    ## 퀀트 전략 분석
    ### Counter Trend Strategy (볼린저 밴드)
    - 신호: {counter_trend_result.get('signal', 'N/A')}
    - 상단 밴드: {counter_trend_result.get('upper_band', 'N/A')}
    - 하단 밴드: {counter_trend_result.get('lower_band', 'N/A')}
    - 중심선(MA): {counter_trend_result.get('ma', 'N/A')}
    
    ### Trend Following Strategy (이동평균 교차)
    - 신호: {trend_following_result.get('signal', 'N/A')}
    - 단기 이동평균(5일): {trend_following_result.get('ma_short', 'N/A')}
    - 장기 이동평균(20일): {trend_following_result.get('ma_long', 'N/A')}
    """
    
    return analysis_text

def run_fundamental_analysis(ticker):
    
    try:
        analyzer = FundamentalAnalyzer()
        
        # 종합 펀더멘털 분석 수행
        analysis_result = analyzer.comprehensive_fundamental_analysis(ticker)
        
        # Extract clean data for LLM analysis
        ratios = analysis_result.get('financial_ratios', {})
        earnings = analysis_result.get('earnings_analysis', {})
        interest = analysis_result.get('interest_rate_analysis', {})
        calendar = analysis_result.get('earnings_calendar', {})
        
        # Handle both multi-source and legacy data structures
        if ratios.get('source') == 'multi-source':
            # New multi-source structure
            metrics = ratios.get('financial_metrics', {})
            data_sources = ratios.get('data_sources_used', [])
            data_quality = ratios.get('data_quality_score', 0)
            missing_metrics = ratios.get('missing_metrics', [])
        else:
            # Legacy structure handling
            if ratios.get('source') == 'naver_finance':
                metrics = ratios.get('financial_metrics', {})
                data_sources = ['naver_finance']
                data_quality = 85
            else:
                metrics = ratios
                data_sources = ['yfinance']
                data_quality = 75
            missing_metrics = []
        
        # Create clean, structured data for LLM analysis
        clean_fundamental_data = f"""
=== {ticker} 실시간 펀더멘털 분석 데이터 ===

## 회사 기본 정보
- 티커: {ticker}
- 데이터 출처: {', '.join(data_sources)}
- 데이터 품질: {data_quality:.1f}%

## 핵심 재무지표 (최신 연간 기준)
- 매출액: {analyzer.format_currency(metrics.get('revenue', 0))}
- 순이익: {analyzer.format_currency(metrics.get('net_income', 0))}
- 총자산: {analyzer.format_currency(metrics.get('total_assets', 0))}
- 자기자본: {analyzer.format_currency(metrics.get('shareholders_equity', 0))}
- 시가총액: {analyzer.format_currency(metrics.get('market_cap', 0))}

## 수익성 지표
- ROA (총자산이익률): {metrics.get('roa', 'N/A')}%
- ROE (자기자본이익률): {metrics.get('roe', 'N/A')}%
- 매출총이익률: {metrics.get('gross_margin', 'N/A')}%
- 자산성장률: {metrics.get('asset_growth', 'N/A')}%

## 밸류에이션 지표
- PER (주가수익비율): {metrics.get('pe_ratio', 'N/A')}
- PBR (주가순자산비율): {metrics.get('pb_ratio', 'N/A')}

## 재무 건전성
- 부채비율: {metrics.get('debt_ratio', 'N/A')}%
- 유동비율: {metrics.get('current_ratio', 'N/A')}%

## 실적 모멘텀
- 펀더멘털 모멘텀: {earnings.get('momentum_description', 'N/A')}
- 최근 분기 실적 개선 여부: {"예" if earnings.get('fundamental_momentum', False) else "아니오"}

## 금리 민감도 분석
- 부채자본비율: {interest.get('debt_to_equity', 'N/A')}%
- 업종: {interest.get('sector', 'N/A')}
- 금리 영향도 점수: {interest.get('interest_impact_score', 'N/A')}/10
- 금리 민감도: {interest.get('analysis', 'N/A')}

## 실적 일정
- 다음 실적발표일: {calendar.get('next_earnings_date', 'N/A')}

## 데이터 품질 정보
- 수집 성공한 핵심 지표 수: {len([m for m in ['revenue', 'net_income', 'market_cap', 'pe_ratio', 'pb_ratio', 'roe', 'roa'] if m in metrics and metrics[m] not in [None, 0, 'N/A']])}/7개
- 누락된 지표: {', '.join(missing_metrics) if missing_metrics else '없음'}

위 데이터를 바탕으로 {ticker}의 펀더멘털 분석을 수행해주세요. 
회사의 비즈니스 모델, 경쟁 우위, 업계 동향 및 리스크를 중심으로 분석하되, 
정량적 데이터는 이미 제공되었으므로 정성적 분석에 집중해주세요.
"""
        
        print("펀더멘털 분석 완료")
        return clean_fundamental_data
        
    except Exception as e:
        error_msg = f"펀더멘털 분석 중 오류 발생: {str(e)}"
        print(error_msg)
        return error_msg


def run_news_analysis(ticker):
    """RAG 기반 실시간 뉴스 분석을 수행합니다."""
    print(f"=== RAG 기반 뉴스 분석 수행 중: {ticker} ===")

    try:
        # NewsAnalyzer 인스턴스 생성
        analyzer = NewsAnalyzer()
        
        # 회사명 가져오기 (새로운 NewsAnalyzer는 자동으로 처리)
        # try:
        #     stock = yf.Ticker(ticker)
        #     company_name = stock.info.get('longName', ticker)
        # except:
        #     company_name = ticker
        
        # 뉴스 분석 수행 (새로운 방식)
        formatted_report = analyzer.analyze_news(ticker)
        
        print("RAG 기반 뉴스 분석 완료")
        return formatted_report
        
    except Exception as e:
        error_msg = f"뉴스 분석 중 오류 발생: {str(e)}"
        print(error_msg)
        return error_msg

def makeMessage(role, content):
    """Creates a message object for the API call."""
    return {"role": role, "content": content}

def makeRequest(messages, model="HCX-003"):
    """Sends a request to the CLOVA Studio API and returns the response."""
    header = {
        "Authorization": "Bearer " + CLOVA_API_KEY,
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    body = {
        "messages": messages,
        "temperature": 0.5,
        "maxTokens": 2048 
    }
    completion_url = f"{CLOVA_URL}/chat-completions/{model}"
    
    response = requests.post(completion_url, headers=header, json=body)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}\nResponse: {response.text}")
        return None

def run_sub_agent(agent_prompt, user_prompt, ticker=None):
    """Runs a specialized sub-agent and returns its analysis content."""
    agent_name = agent_prompt.splitlines()[1].strip()
    print(f"--- Running {agent_name} ---")
    
    enhanced_prompt = user_prompt
    
    # Quant Agent의 경우 실시간 계산된 데이터 추가
    if "quantitative analyst" in agent_prompt.lower() and ticker:
        real_time_data = run_quant_analysis(ticker)
        enhanced_prompt = f"{user_prompt}\n\n실시간 정량 데이터:\n{real_time_data}\n\n위 실시간 데이터를 바탕으로 정량적 분석을 수행해주세요."
    
    # Fundamental Agent의 경우 펀더멘털 분석 데이터 추가
    elif "fundamental analyst" in agent_prompt.lower() and ticker:
        fundamental_data = run_fundamental_analysis(ticker)
        enhanced_prompt = f"{user_prompt}\n\n실시간 펀더멘털 데이터:\n{fundamental_data}\n\n위 실시간 펀더멘털 데이터를 바탕으로 기본적 분석을 수행해주세요. 특히 다음 관점들을 중점적으로 분석해주세요:\n- 금리 관점에서의 주가 영향\n- 실적발표 및 어닝서프라이즈 관점\n- ROA, ROE, Asset Growth 등 핵심 재무지표\n- Fundamental Momentum (최근 실적 개선 여부)"
    
    # News Agent의 경우 RAG 기반 실시간 뉴스 분석 데이터 추가
    elif "news analysis" in agent_prompt.lower() and ticker:
        news_data = run_news_analysis(ticker)
        enhanced_prompt = f"{user_prompt}\n\n실시간 RAG 뉴스 데이터:\n{news_data}\n\n위 실시간 뉴스 데이터를 바탕으로 뉴스 분석을 수행해주세요. 특히 다음 관점들을 중점적으로 분석해주세요:\n- FinBERT 기반 감정 분석 결과 해석\n- 주요 뉴스 이벤트가 주가에 미치는 영향\n- 시장 센티먼트 변화 추이\n- 투자자 심리 및 단기/중기 전망"
    
    messages = [
        makeMessage("system", agent_prompt),
        makeMessage("user", enhanced_prompt)
    ]
    response = makeRequest(messages)
    if response and response.get("result"):
        content = response["result"]["message"]["content"]
        print(content)
        return content
    return f"Failed to get a response from the agent."


# --- Main Execution Logic for Testing ---

if __name__ == "__main__":
    target_ticker = "005930.KS"  # 삼성전자 (한국 거래소)
    user_request = f"Analyze the stock: {target_ticker}"

    # 1. Run specialized sub-agents
    quant_report = run_sub_agent(QUANT_PROMPT, user_request, ticker=target_ticker)
    fundamental_report = run_sub_agent(FUNDAMENTAL_PROMPT, user_request, ticker=target_ticker)
    news_report = run_sub_agent(NEWS_PROMPT, user_request, ticker=target_ticker)

    # 2. Combine reports for the final agent
    combined_report = f"""
    Here are the reports from the specialized agents for {target_ticker}:

    --- Quantitative Analysis ---
    {quant_report}

    --- Fundamental Analysis ---
    {fundamental_report}

    --- News Analysis ---
    {news_report}

    Please synthesize these reports and provide a final investment recommendation as a top tier investment advisor.
    """

    # 3. Run the final master agent
    print("\n--- Running Master Investment Agent to Finalize Report ---")
    final_messages = [
        makeMessage("system", FINAL_PROMPT),
        makeMessage("user", combined_report)
    ]
    
    final_response = makeRequest(final_messages)

    # 4. Print the final result
    print("\n" + "="*40)
    print("      FINAL INVESTMENT RECOMMENDATION")
    print("="*40 + "\n")
    if final_response and final_response.get("result"):
        final_content = final_response["result"]["message"]["content"]
        print(final_content)
    else:
        print("Could not generate the final report.")


def kakao(ticker):
    target_ticker = ticker
    user_request = f"Analyze the stock: {target_ticker}"

    # 1. Run specialized sub-agents
    quant_report = run_sub_agent(QUANT_PROMPT, user_request, ticker=target_ticker)
    fundamental_report = run_sub_agent(FUNDAMENTAL_PROMPT, user_request, ticker=target_ticker)
    news_report = run_sub_agent(NEWS_PROMPT, user_request, ticker=target_ticker)
    combined_report = f"""
    Here are the reports from the specialized agents for {target_ticker}:

    --- Quantitative Analysis ---
    {quant_report}

    --- Fundamental Analysis ---
    {fundamental_report}

    --- News Analysis ---
    {news_report}

    Please synthesize these reports and provide a final investment recommendation.
    """

    # 3. Run the final master agent
    print("\n--- Running Master Investment Agent to Finalize Report ---")
    final_messages = [
        makeMessage("system", FINAL_PROMPT),
        makeMessage("user", combined_report)
    ]
    
    final_response = makeRequest(final_messages)

    # 4. Print the final result
    if final_response and final_response.get("result"):
        final_content = final_response["result"]["message"]["content"]
        return final_content
    else:
        return "Could not generate the final report."
    