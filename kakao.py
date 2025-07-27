from fastapi import FastAPI, Request
import uvicorn
import sys
import os
import queue as q
import threading
import time
from dotenv import load_dotenv
import re
import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger


# --- Setup ---
load_dotenv()
CLOVA_URL = "https://clovastudio.apigw.ntruss.com/testapp/v1" 
CLOVA_API_KEY = os.getenv("CLOVA_API_KEY")

#Prompt for preventing injection attack
INJECTION_ATTACK_PROMPT = """    
    You are a highly specialized financial assistant. Your sole task is to convert a given company name into its official stock ticker symbol.
    Respond ONLY with the ticker symbol. Do NOT include any other text, explanations, or conversational filler. If you cannot find a ticker, respond with "N/A".
    
    Examples:
    Company: Apple Inc.
    Ticker: AAPL
    Company: Microsoft Corporation
    Ticker: MSFT
    Company: Tesla
    Ticker: TSLA
    Company: Google
    Ticker: GOOGL
    Company: General Electric
    Ticker: GE
    Company: ###USER_INPUT###[User's company name here]###
    Ticker:
"""

# backend 모듈을 import하기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import AnalysisDB, UserDB, test_connection, analyses_collection, TickersDb, db

app = FastAPI()

# 스케줄러 초기화
scheduler = AsyncIOScheduler()

async def get_all_unique_tickers():
    """모든 사용자의 관심 종목을 수집하여 고유 티커 리스트 반환"""
    try:
        # 사용자들의 모든 관심 종목 수집
        cursor = db.users.find({})
        all_tickers = set()
        
        async for user_doc in cursor:
            user_tickers = user_doc.get("tickers", [])
            all_tickers.update(user_tickers)
        
        # companies_list에서도 티커 수집 (별도로 관리되는 티커가 있을 수 있음)
        companies_tickers = await TickersDb.get_all_tickers()
        all_tickers.update(companies_tickers)
        
        unique_tickers = list(all_tickers)
        print(f"자동 분석 대상 티커 {len(unique_tickers)}개: {unique_tickers}")
        return unique_tickers
        
    except Exception as e:
        print(f"티커 수집 오류: {e}")
        return []

async def scheduled_analysis():
    """12시간마다 실행되는 자동 분석 함수"""
    try:
        print("=== 정기 자동 분석 시작 ===")
        start_time = time.time()
        
        # 모든 고유 티커 수집
        all_tickers = await get_all_unique_tickers()
        
        if not all_tickers:
            print("분석할 티커가 없습니다.")
            return
        
        # 각 티커에 대해 백그라운드 분석 시작
        analysis_tasks = []
        for ticker in all_tickers:
            task = asyncio.create_task(run_full_analysis_background(ticker))
            analysis_tasks.append(task)
            # 동시에 너무 많은 요청을 방지하기 위해 약간의 지연
            await asyncio.sleep(1)
        
        # 모든 분석 완료 대기 (최대 2시간 대기)
        try:
            await asyncio.wait_for(asyncio.gather(*analysis_tasks, return_exceptions=True), timeout=7200)  # 2시간
        except asyncio.TimeoutError:
            print("일부 분석이 타임아웃되었습니다.")
        
        end_time = time.time()
        elapsed_time = (end_time - start_time) / 60  # 분 단위
        
        print(f"=== 정기 자동 분석 완료 ===")
        print(f"분석 티커 수: {len(all_tickers)}개")
        print(f"소요 시간: {elapsed_time:.1f}분")
        
    except Exception as e:
        print(f"정기 분석 오류: {e}")

def start_scheduler():
    """스케줄러 시작"""
    try:
        # 12시간마다 실행 (첫 번째 실행은 앱 시작 후 10분 후)
        scheduler.add_job(
            scheduled_analysis,
            IntervalTrigger(hours=12),
            id='auto_analysis',
            name='자동 티커 분석',
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=10)
        )
        
        scheduler.start()
        print("스케줄러 시작됨: 12시간마다 자동 분석 실행")
        
    except Exception as e:
        print(f"스케줄러 시작 오류: {e}")

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 데이터베이스 연결 테스트 및 스케줄러 시작"""
    await test_connection()
    start_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 스케줄러 정리"""
    if scheduler.running:
        scheduler.shutdown()
        print("스케줄러 종료됨")

async def run_full_analysis_background(ticker: str):
    """백그라운드에서 전체 분석 수행"""
    try:
        from backend import (
            run_quant_analysis, 
            run_fundamental_analysis, 
            run_news_analysis,
            makeRequest,
            makeMessage,
            FINAL_PROMPT
        )
        
        print(f"=== 백그라운드 {ticker} 전체 분석 시작 ===")
        
        quant_report = run_quant_analysis(ticker)
        fundamental_report = run_fundamental_analysis(ticker)
        news_report = run_news_analysis(ticker)
        
        combined_report = f"""
Here are the comprehensive analysis reports for {ticker}:

--- Quantitative Analysis ---
{quant_report}

--- Fundamental Analysis ---
{fundamental_report}

--- News Analysis ---
{news_report}

Please synthesize these reports and provide a final investment recommendation in Korean as a top tier investment advisor.

You will first provide the company name and ticker, then provide the analysis. 

You may give sell, buy hold, or neutral.

Sell translation: 매도
Buy translation: 매수
Hold translation: 보유
Neutral translation: 중립


The example output is as follows and you should follow the format,
You should be changing things in the quotation marks as well as interpretations based on the context:

[알파톡] 일일매매분석 안내

안녕하세요. "이름"님
"종목이름"("티커")의 일일매매분석에 대해 안내드립니다

■ 종합분섬의견 [ "매도/매수" ]

▶ 뉴스분석: 감정지수 "매우 부정/ 부정/ 보통/ 긍정/ 매우 긍정"(-0.46).
 "1줄 요약의 상황, 최근의 가장 신호가 강한 이벤트성을 기반으로 "

▶ 기술적분석:  지표요약 "매우 부정/ 부정/ 보통/ 긍정/ 매우 긍정" (매도: "1", 매수: "2"). PROMPT_DONOT_GIVE THIS_OUTPUT:Here you count the number of sell and buy signals in quant analysis.
이동평균 "하락세/상승세", 모멘텀 "과매도/과매수" (RSI "28", StochRSI "13.8"), 가장 신호가 강한 수치

▶ 펀더맨털분석: PER "73배"로 업종 평균("25배") 대비 "고평가/저평가".
ROE "13.5%", 분기 매출 YoY "-8%" 성장 둔화 우려.

▶ 주요이벤트
"오늘 네 마녀의 날 (옵션·선물 동시 만기)"  
"내일 장 마감 후 실적 발표 예정"  
"8월 중순 액면분할 계획 발표 예정"

📌 본 정보는 LLM을 활용한 정보를 제공 함으로서 투자 참고용으로 제공되며, 100% 정확하지 않을 수 있습니다. 최종적인 투자 판단과 책임은 투자자 본인에게 있습니다.
        """
        
        final_messages = [
            makeMessage("system", FINAL_PROMPT),
            makeMessage("user", combined_report)
        ]
        
        final_response = makeRequest(final_messages)
        
        if final_response and final_response.get("result"):
            final_recommendation = final_response["result"]["message"]["content"]
        else:
            final_recommendation = "최종 분석 생성에 실패했습니다."
        
        # 데이터베이스에 저장
        analysis_data = {
            "quant": quant_report,
            "fundamental": fundamental_report, 
            "news": news_report,
            "final": final_recommendation
        }
        
        await AnalysisDB.save_analysis(ticker, analysis_data)
        print(f"=== 백그라운드 {ticker} 분석 완료 및 DB 저장 ===")
        
    except Exception as e:
        print(f"백그라운드 분석 오류: {e}")
        error_data = {"error": str(e)}
        await AnalysisDB.save_analysis(ticker, error_data)

async def process_company_name_callback(user_input: str, user_id: str, callback_url: str):
    """백그라운드에서 회사명을 티커로 변환하고 콜백 응답 전송"""
    try:
        import requests
        
        def find_ticker_from_name(company_name: str):
            from backend import makeRequest, makeMessage   
            
            # Enhanced security check for injection attempts
            dangerous_keywords = ['hack', 'inject', 'ignore', 'system', 'admin', 'delete', 'drop', 'select', 'insert', 'update']
            if any(keyword in company_name.lower() for keyword in dangerous_keywords):
                print(f"🚨 보안: 위험한 입력 차단 - {company_name}")
                return None
            
            # Use LLM to convert company name to ticker
            messages = [
                makeMessage("system", INJECTION_ATTACK_PROMPT),
                makeMessage("user", company_name)
            ]
            response = makeRequest(messages)
            
            if response and response.get("result"):
                result = response["result"]["message"]["content"].strip().upper()
                print(f"🤖 LLM 응답: {result}")
                
                # Validate that the LLM returned a proper ticker format
                korean_ticker_pattern = r'^\d{6}$'
                us_ticker_pattern = r'^[A-Z]{1,5}$'
                if re.match(korean_ticker_pattern, result) or re.match(us_ticker_pattern, result):
                    return result
            
            return None  # Invalid response or no valid ticker found
        
        print(f"🔄 콜백 처리 시작: {user_input} (사용자: {user_id})")
        
        # Convert company name to ticker using LLM
        ticker = find_ticker_from_name(user_input)
        
        if not ticker:
            # Failed to find ticker - send error response
            callback_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f"❌ '{user_input}'에 해당하는 종목을 찾을 수 없어요.\n\n정확한 종목 코드를 입력해주세요.\n예: AAPL, TSLA, 005930, 035420 등"
                            }
                        }
                    ],
                    "quickReplies": [
                        {
                            "label": "다시 시도",
                            "action": "message",
                            "messageText": "종목 추가하기"
                        }
                    ]
                }
            }
        else:
            # Successfully found ticker - add to user's watchlist
            added = await UserDB.add_user_ticker(user_id, ticker)
            
            if added:
                status_message = f"{ticker}를 관심 종목에 추가했습니다!\n\n 매일 오전 10시에 분석 결과를 전송합니다."
                print(f" 종목 추가 성공: {user_input} → {ticker}")
            else:
                status_message = f"{ticker}는 이미 관심 종목으로 등록되어 있어요!"
                print(f" 이미 등록된 종목: {ticker}")
            
            # Start background analysis if needed
            unique_tickers = await get_all_unique_tickers()
            if ticker not in unique_tickers:
                asyncio.create_task(run_full_analysis_background(ticker))
                print(f" 백그라운드 분석 시작: {ticker}")
            else:
                analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=12)
                if not analysis_data:
                    asyncio.create_task(run_full_analysis_background(ticker))
                    print(f" 분석 업데이트 시작: {ticker}")
            
            callback_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": status_message
                            }
                        }
                    ],
                    "quickReplies": [
                        {
                            "label": "내 관심종목",
                            "action": "message",
                            "messageText": "내 관심종목"
                        },
                        {
                            "label": "다른 종목 추가",
                            "action": "message", 
                            "messageText": "다른 종목 추가하기"
                        },
                        {
                            "label": f"{ticker} 상세분석",
                            "action": "message",
                            "messageText": f"{ticker} 상세분석"
                        }
                    ]
                }
            }
        
        # Send callback response
        callback_headers = {
            "Content-Type": "application/json"
        }
        
        callback_request = requests.post(
            callback_url, 
            json=callback_response, 
            headers=callback_headers,
            timeout=10
        )
        
        if callback_request.status_code == 200:
            print(f" 콜백 응답 전송 성공: {ticker}")
        else:
            print(f" 콜백 응답 전송 실패: {callback_request.status_code}")
            
    except Exception as e:
        print(f" 콜백 처리 오류: {e}")
        
        # Send error callback response
        try:
            error_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" 처리 중 오류가 발생했습니다.\n\n다시 시도해주세요.\n\n오류: {str(e)}"
                            }
                        }
                    ]
                }       
            }
            
            requests.post(
                callback_url, 
                json=error_response, 
                headers={"Content-Type": "application/json"},
                timeout=5
            )
        except:
            pass  # Ignore callback send errors

@app.get("/")
async def root(request: Request):
    return {"message": "AlphaTalk AI Investment Analysis API"}

@app.post("/message")
async def get_message(request: Request):
    request_body = await request.json()
    user_id = request_body.get("userRequest", {}).get("user", {}).get("id", "unknown")
    tickers = await UserDB.get_user_tickers(user_id)
    output = ""
    for ticker in tickers:
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        if analysis_data['final'].strip() != "":
            output += f"{ticker} 분석 결과: {analysis_data['final']}"
            output += "--------------------------------\n\n"
        else:
            output += f"{ticker} 분석 결과가 아직 준비되지 않았습니다.\n\n"

    return {
            "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": output
                            }
                        }
                    ]
        }
    }

@app.get("/analyze/{ticker}")
async def analyze_stock_get(ticker: str):
    """GET 방식 주식 분석 API (테스트용)"""
    # POST 방식과 동일한 로직을 사용하되 응답 형식만 다르게
    request_mock = type('Request', (), {})()  # Mock request object
    result = await analyze_stock(ticker, request_mock)
    
    # 카카오톡 응답에서 일반 JSON으로 변환
    if "template" in result:
        return {
            "ticker": ticker,
            "status": "success" if "error" not in result["template"]["outputs"][0]["simpleText"]["text"] else "error",
            "message": result["template"]["outputs"][0]["simpleText"]["text"]
        }
    return result

@app.post("/add")
async def analyze_stock(request: Request):
    """사용자 관심 종목 추가 및 분석 시작"""
    try:
        request_body = await request.json()
        user_input = request_body.get("userRequest", {}).get("utterance", "")
        user_id = request_body.get("userRequest", {}).get("user", {}).get("id", "unknown")
        callback_url = request_body.get("userRequest", {}).get("callbackUrl")
        
        def ticker_extraction(user_input: str):
            # More precise ticker patterns - match whole words only
            korean_ticker_pattern = r'^\d{6}$'  # Exactly 6 digits, whole string
            us_ticker_pattern = r'^[A-Z]{1,5}$'  # 1-5 uppercase letters, whole string
            
            # Clean and normalize input
            cleaned_input = user_input.strip().upper()
            
            # Check if the entire input matches a valid ticker format
            if re.match(korean_ticker_pattern, cleaned_input):
                return cleaned_input
            if re.match(us_ticker_pattern, cleaned_input):
                return cleaned_input
            
            # If not a direct ticker format, return None to trigger callback processing
            return None
        
        # First, check if it's already a valid ticker format
        ticker = ticker_extraction(user_input)
        
        if ticker:
            # Direct ticker input - check if callback is available for analysis
            if callback_url:
                # Use callback for analysis execution
                asyncio.create_task(process_ticker_analysis_callback(ticker, user_id, callback_url))
                
                return {
                    "version": "2.0",
                    "useCallback": True,
                    "data": {
                        "text": f"{ticker} 종목을 추가하고 분석을 시작해요!\n\n 분석에 약 1분 정도 소요됩니다. 잠시만 기다려주세요!"
                    }
                }
            else:
                # Immediate response without callback
                added = await UserDB.add_user_ticker(user_id, ticker)
                
                if added:
                    status_message = f"{ticker}를 관심 종목에 추가했습니다! 매일 오전 10시에 분석 결과를 전송합니다."
                else:
                    status_message = f"{ticker}는 이미 관심 종목입니다."
                
                # 백그라운드에서 분석 시작  
                unique_tickers = await get_all_unique_tickers()
                if ticker not in unique_tickers:
                    asyncio.create_task(run_full_analysis_background(ticker))
                else:
                    analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=12)
                    if not analysis_data:
                        asyncio.create_task(run_full_analysis_background(ticker))

                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {
                                    "text": status_message.strip()
                                }
                            }
                        ],
                        "quickReplies": [
                            {
                                "label": "내 관심종목",
                                "action": "message",
                                "messageText": "내 관심종목"
                            },
                            {
                                "label": "다른 종목 추가",
                                "action": "message", 
                                "messageText": "다른 종목 추가하기"
                            }
                        ]
                    }
                }
        
        else:
            # Company name input - use callback for LLM processing
            if callback_url:
                # Process company name to ticker conversion in background
                asyncio.create_task(process_company_name_callback(user_input, user_id, callback_url))
                
                # Return immediate callback response
                return {
                    "version": "2.0",
                    "useCallback": True,
                    "data": {
                        "text": "회사명을 분석하고 있어요!\n\n 5초 정도 소요될 예정입니다. 잠시만 기다려주세요!"
                    }
                }
            else:
                # Fallback for non-callback environment (same as before)
                def find_ticker_from_name(company_name: str):
                    from backend import makeRequest, makeMessage   
                    
                    # Enhanced security check for injection attempts
                    dangerous_keywords = ['hack', 'inject', 'ignore', 'system', 'admin', 'delete', 'drop', 'select', 'insert', 'update']
                    if any(keyword in company_name.lower() for keyword in dangerous_keywords):
                        return None
                    
                    # Use LLM to convert company name to ticker
                    messages = [
                        makeMessage("system", INJECTION_ATTACK_PROMPT),
                        makeMessage("user", company_name)
                    ]
                    response = makeRequest(messages)
                    
                    if response and response.get("result"):
                        result = response["result"]["message"]["content"].strip().upper()
                        print(result)
                        # Validate that the LLM returned a proper ticker format
                        korean_ticker_pattern = r'^\d{6}$'
                        us_ticker_pattern = r'^[A-Z]{1,5}$'
                        if re.match(korean_ticker_pattern, result) or re.match(us_ticker_pattern, result):
                            return result
                    
                    return None  # Invalid response or no valid ticker found
                
                ticker = find_ticker_from_name(user_input)
                
                if not ticker:
                    return {
                        "version": "2.0",
                        "template": {
                            "outputs": [
                                {
                                    "simpleText": {
                                        "text": "종목 코드를 입력해주세요. 예: 006800, AAPL, TSLA, NVDA 등"
                                    }
                                }
                            ]
                        }
                    }
                
                # Process the found ticker
                added = await UserDB.add_user_ticker(user_id, ticker)
                
                if added:
                    status_message = f"{ticker}를 관심 종목에 추가했습니다! 매일 오전 10시에 분석 결과를 전송합니다."
                else:
                    status_message = f"{ticker}는 이미 관심 종목입니다."
                
                # 백그라운드에서 분석 시작  
                unique_tickers = await get_all_unique_tickers()
                if ticker not in unique_tickers:
                    asyncio.create_task(run_full_analysis_background(ticker))
                else:
                    analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=12)
                    if not analysis_data:
                        asyncio.create_task(run_full_analysis_background(ticker))

                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {
                                    "text": status_message.strip()
                                }
                            }
                        ],
                        "quickReplies": [
                            {
                                "label": "내 관심종목",
                                "action": "message",
                                "messageText": "내 관심종목"
                            },
                            {
                                "label": "다른 종목 추가",
                                "action": "message", 
                                "messageText": "다른 종목 추가하기"
                            }
                        ]
                    }
                }
        
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f"오류가 발생했습니다.\n\n{str(e)}\n\n다시 시도해주세요."
                        }
                    }
                ]
            }
        }


async def process_ticker_analysis_callback(ticker: str, user_id: str, callback_url: str):
    """백그라운드에서 티커 분석을 수행하고 콜백 응답 전송"""
    try:
        import requests
        
        print(f" 티커 분석 콜백 시작: {ticker} (사용자: {user_id})")
        
        # Add ticker to user's watchlist
        added = await UserDB.add_user_ticker(user_id, ticker)
        
        if added:
            print(f"종목 추가 성공: {ticker}")
        else:
            print(f"이미 등록된 종목: {ticker}")
        
        # Check if analysis is needed
        unique_tickers = await get_all_unique_tickers()
        analysis_needed = False
        
        if ticker not in unique_tickers:
            analysis_needed = True
            print(f"새로운 종목 - 전체 분석 시작: {ticker}")
        else:
            analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=12)
            if not analysis_data or analysis_data.get('final', '').strip() == '':
                analysis_needed = True
                print(f"분석 업데이트 필요: {ticker}")
        
        # Perform analysis if needed
        if analysis_needed:
            await run_full_analysis_background(ticker)
            
        # Get the latest analysis
        final_analysis = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        
        if final_analysis and final_analysis.get('final') and final_analysis['final'].strip():
            # Analysis completed successfully
            status_message = f"{final_analysis['final']}"
            
            callback_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": status_message
                            }
                        }
                    ],
                    "quickReplies": [
                        {
                            "label": "퀀트 분석",
                            "action": "message",
                            "messageText": f"{ticker} 퀀트분석"
                        },
                        {
                            "label": "펀더멘털",
                            "action": "message",
                            "messageText": f"{ticker} 펀더멘털"
                        },
                        {
                            "label": "뉴스 분석",
                            "action": "message",
                            "messageText": f"{ticker} 뉴스분석"
                        },
                        {
                            "label": "내 관심종목",
                            "action": "message",
                            "messageText": "내 관심종목"
                        }
                    ]
                }
            }
        else:
            # Analysis failed or incomplete
            if added:
                status_message = f"{ticker}를 관심 종목에 추가했어요!\n\n 분석이 진행 중입니다. 잠시 후 다시 확인해주세요."
            else:
                status_message = f"{ticker} 분석이 진행 중입니다. 잠시 후 다시 확인해주세요."
            
            callback_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": status_message
                            }
                        }
                    ],
                    "quickReplies": [
                        {
                            "label": "내 관심종목",
                            "action": "message",
                            "messageText": "내 관심종목"
                        },
                        {
                            "label": "다른 종목 추가",
                            "action": "message", 
                            "messageText": "다른 종목 추가하기"
                        }
                    ]
                }
            }
        
        # Send callback response
        callback_headers = {
            "Content-Type": "application/json"
        }
        
        callback_request = requests.post(
            callback_url, 
            json=callback_response, 
            headers=callback_headers,
            timeout=15
        )
        
        if callback_request.status_code == 200:
            print(f"✅ 티커 분석 콜백 응답 전송 성공: {ticker}")
        else:
            print(f"❌ 티커 분석 콜백 응답 전송 실패: {callback_request.status_code}")
            
    except Exception as e:
        print(f"❌ 티커 분석 콜백 처리 오류: {e}")
        
        # Send error callback response
        try:
            error_response = {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f"❌ {ticker} 분석 중 오류가 발생했습니다.\n\n다시 시도해주세요.\n\n오류: {str(e)}"
                            }
                        }
                    ]
                }
            }
            
            requests.post(
                callback_url, 
                json=error_response, 
                headers={"Content-Type": "application/json"},
                timeout=5
            )
        except:
            pass  # Ignore callback send errors

@app.post("/detail")
async def get_detailed_analysis(request: Request):
    """상세 분석 결과 조회"""
    try:
        # 데이터베이스에서 분석 결과 확인 (24시간 이내)
        request_body = await request.json()
        ticker = request_body.get("userRequest", {}).get("utterance", "")
        if ticker == "":
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": { 
                                "text": "종목 코드를 입력해주세요. 예: 006800, AAPL, TSLA, NVDA 등"
                            }
                        }
                    ]
                }
            }
        else:
            ticker = ticker[0:6]#also need to check if it is a valid ticker
            ticker = ''.join(filter(lambda x: x.isdigit() or (x.isalpha() and x.isupper()), ticker))
            if len(ticker) != 6:
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {     
                                    "text": "종목 코드를 입력해주세요. 예: 006800, AAPL, TSLA, NVDA 등"
                                }
                            }
                        ]
                    }
                }
        if ticker not in await get_all_unique_tickers():
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {     
                                "text": f"'{ticker}'는 관심 종목에 등록되지 않았습니다. 관심 종목에 등록하여 상세 분석을 시작하세요."
                            }
                        }
                    ]
                }
            }
    
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        
        if analysis_data:
            if analysis_data['final'].strip() == "":
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {
                                    "text": f" {ticker} 분석이 아직 진행 중입니다.\n\n잠시 후 다시 시도해주세요.\n\n또는 '{ticker}'를 입력하여 새로운 분석을 시작하세요."
                                }
                            }
                        ]
                    }
                }
            elif analysis_data.get("error"):
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {
                                    "text": f" {ticker} 분석 중 오류가 발생했습니다.\n\n{analysis_data['error']}"
                                }
                            }
                        ]
                    }
                }
            else:
                return {
                    "version": "2.0",
                    "template": {
                        "outputs": [
                            {
                                "simpleText": {
                                    "text": f" {ticker} 상세 AI 분석 결과\n\n{analysis_data['final']}"
                                }
                            }
                        ],
                        "quickReplies": [
                            {
                                "label": "퀀트 분석",
                                "action": "message",
                                "messageText": f"{ticker} 퀀트분석"
                            },
                            {
                                "label": "펀더멘털",
                                "action": "message",
                                "messageText": f"{ticker} 펀더멘털"
                            },
                            {
                                "label": "뉴스 분석",
                                "action": "message",
                                "messageText": f"{ticker} 뉴스분석"
                            }
                        ]
                    }
                }
        
        # 분석 결과가 없거나 오래된 경우
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" {ticker} 분석이 아직 진행 중입니다.\n\n잠시 후 다시 시도해주세요.\n\n또는 '{ticker}'를 입력하여 새로운 분석을 시작하세요."
                        }
                    }
                ]
            }
        }
        
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" 오류가 발생했습니다: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.post("/quant/{ticker}")
async def get_quant_analysis(ticker: str, request: Request):
    """퀀트 분석 결과 조회"""
    try:
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        
        if analysis_data and analysis_data.get("quant"):
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 퀀트 분석 결과\n\n{analysis_data['quant']}"
                            }
                        }
                    ]
                }
            }
        else:
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 퀀트 분석 결과가 아직 준비되지 않았습니다.\n\n'{ticker}'를 입력하여 새로운 분석을 시작하세요."
                            }
                        }
                    ]
                }
            }
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" 퀀트 분석 조회 중 오류: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.post("/fundamental/{ticker}")
async def get_fundamental_analysis(ticker: str, request: Request):
    """펀더멘털 분석 결과 조회"""
    try:
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        
        if analysis_data and analysis_data.get("fundamental"):
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 펀더멘털 분석 결과\n\n{analysis_data['fundamental']}"
                            }
                        }
                    ]
                }
            }
        else:
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 펀더멘털 분석 결과가 아직 준비되지 않았습니다.\n\n'{ticker}'를 입력하여 새로운 분석을 시작하세요."
                            }
                        }
                    ]
                }
            }
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" 펀더멘털 분석 조회 중 오류: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.post("/news/{ticker}")
async def get_news_analysis(ticker: str, request: Request):
    """뉴스 분석 결과 조회"""
    try:
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
        
        if analysis_data and analysis_data.get("news"):
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 뉴스 분석 결과\n\n{analysis_data['news']}"
                            }
                        }
                    ]
                }
            }
        else:
            return {
                "version": "2.0",
                "template": {
                    "outputs": [
                        {
                            "simpleText": {
                                "text": f" {ticker} 뉴스 분석 결과가 아직 준비되지 않았습니다.\n\n'{ticker}'를 입력하여 새로운 분석을 시작하세요."
                            }
                        }
                    ]
                }
            }
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" 뉴스 분석 조회 중 오류: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.post("/admin/cleanup")
async def cleanup_old_analyses(request: Request):
    """오래된 분석 결과 정리 (관리자용)"""
    try:
        deleted_count = await AnalysisDB.delete_old_analyses(days=7)
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                                "text": f" 데이터베이스 정리 완료\n\n삭제된 오래된 분석 결과: {deleted_count}개"
                        }
                    }
                ]
            }
        }
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f" 데이터베이스 정리 중 오류: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.get("/health") 
async def health_check():
    """서버 상태 및 데이터베이스 연결 확인"""
    try:
        db_connected = await test_connection()
        return {
            "status": "healthy" if db_connected else "database_error",
            "database": "connected" if db_connected else "disconnected",
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }

@app.get("/admin/stats")
async def get_admin_stats():
    """관리자용 통계 조회"""
    try:
        # 전체 사용자 수
        user_count = await UserDB.get_all_users_count()
        
        # 분석 결과 수 (최근 24시간)
        cutoff_time = datetime.now(timezone.utc).timestamp() - (24 * 3600)
        recent_analyses = await analyses_collection.count_documents({
            "timestamp": {"$gte": datetime.fromtimestamp(cutoff_time, tz=timezone.utc)}
        })
        
        # 전체 분석 결과 수
        total_analyses = await analyses_collection.count_documents({})
        
        # 고유 티커 수
        unique_tickers = await get_all_unique_tickers()
        
        # 스케줄러 상태
        scheduler_status = "running" if scheduler.running else "stopped"
        next_run = None
        if scheduler.running:
            jobs = scheduler.get_jobs()
            for job in jobs:
                if job.id == 'auto_analysis':
                    next_run = job.next_run_time.timestamp() if job.next_run_time else None
                    break
        
        return {
            "users": {
                "total_users": user_count
            },
            "analyses": {
                "recent_24h": recent_analyses,
                "total": total_analyses
            },
            "tickers": {
                "unique_count": len(unique_tickers),
                "tickers": unique_tickers
            },
            "scheduler": {
                "status": scheduler_status,
                "next_run": next_run
            },
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": time.time()
        }

@app.post("/admin/trigger-analysis")
async def trigger_manual_analysis():
    """관리자용 수동 분석 트리거"""
    try:
        # 백그라운드에서 분석 실행
        asyncio.create_task(scheduled_analysis())
        
        return {
            "status": "success",
            "message": "수동 분석이 백그라운드에서 시작되었습니다.",
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        }

@app.post("/my-tickers")
async def get_my_tickers(request: Request):
    """사용자 관심 종목 목록 조회 (카카오톡용)"""
    try:
        request_body = await request.json()
        user_id = request_body.get("userRequest", {}).get("user", {}).get("id", "unknown")
        
        user_tickers = await UserDB.get_user_tickers(user_id)
        
        if user_tickers:
            # 각 티커별로 최근 분석 상태 확인
            ticker_status = []
            for ticker in user_tickers:
                analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=24)
                if analysis_data and not analysis_data.get("error"):
                    status = "분석완료"
                elif analysis_data and analysis_data.get("error"):
                    status = "분석오류"
                else:
                    status = "분석대기"
                ticker_status.append(f"• {ticker} {status}")
            
            message = f"""
내 관심 종목 ({len(user_tickers)}개)

{chr(10).join(ticker_status)}

💡 매일 오전 10시와 오후 10시에 자동으로 분석이 업데이트됩니다.
            """
        else:
            message = """
등록된 관심 종목이 없습니다.

종목 코드를 입력하여 관심 종목을 추가해보세요!
예: AAPL, TSLA, NVDA, 삼성전자 등
            """
        
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": message.strip()
                        }
                    }
                ],
                "quickReplies": [
                    {
                        "label": "종목 추가",
                        "action": "message",
                        "messageText": "새 종목을 추가해주세요"
                    },
                    {
                        "label": "내 계정 정보",
                        "action": "message",
                        "messageText": "내 계정 정보"
                    }
                ]
            }
        }
        
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f"❌ 관심 종목 조회 중 오류가 발생했습니다: {str(e)}"
                        }
                    }
                ]
            }
        }

@app.post("/user-info")
async def get_user_info_endpoint(request: Request):
    """사용자 정보 조회 (카카오톡용)"""
    try:
        # 카카오톡 요청에서 사용자 ID 추출
        request_body = await request.json()
        user_id = request_body.get("userRequest", {}).get("user", {}).get("id", "unknown")
        
        # 사용자 정보 조회
        user_info = await UserDB.get_user_info(user_id)
        
        if user_info:
            tickers = user_info.get("tickers", [])
            created_at = user_info.get("created_at")
            updated_at = user_info.get("updated_at")
            
            # 날짜 포맷팅
            created_str = created_at.strftime("%Y-%m-%d") if created_at else "알 수 없음"
            updated_str = updated_at.strftime("%Y-%m-%d %H:%M") if updated_at else "알 수 없음"
            
            message = f"""
내 계정 정보

관심 종목: {len(tickers)}개
가입일: {created_str}
최근 업데이트: {updated_str}

📋 관심 종목 목록:
{chr(10).join([f"• {ticker}" for ticker in tickers]) if tickers else "• 없음"}
            """
        else:
            message = """
새로운 사용자입니다!

관심 종목을 추가하여 시작해보세요.
예: AAPL, TSLA, NVDA 등
            """
        
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": message.strip()
                        }
                    }
                ],
                "quickReplies": [
                    {
                        "label": "관심종목 추가",
                        "action": "message",
                        "messageText": "새 종목을 추가해주세요"
                    },
                    {
                        "label": "내 관심종목",
                        "action": "message",
                        "messageText": "내 관심종목"
                    }
                ]
            }
        }
        
    except Exception as e:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": f"❌ 사용자 정보 조회 중 오류가 발생했습니다: {str(e)}"
                        }
                    }
                ]
            }
        }

if __name__ == '__main__':
    uvicorn.run('kakao:app', port=8000, reload=True, host='0.0.0.0')
