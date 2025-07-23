from fastapi import FastAPI, Request
import uvicorn
import sys
import os
import queue as q
import threading
import time
import re

# backend 모듈을 import하기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import AnalysisDB, UserDB, test_connection, analyses_collection

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 데이터베이스 연결 테스트"""
    await test_connection()

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

Please synthesize these reports and provide a final investment recommendation in Korean.
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

@app.get("/")
async def root(request: Request):
    return {"message": "AlphaTalk AI Investment Analysis API"}

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
        def ticker_extraction(user_input: str):
            ticker_pattern = r"[A-Z]{1,5}"
            ticker_match = re.search(ticker_pattern, user_input)
            return ticker_match.group(0) if ticker_match else None
        
        ticker = ticker_extraction(user_input)
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
        
        user_id = request_body.get("userRequest", {}).get("user", {}).get("id", "unknown")
        
        added = await UserDB.add_user_ticker(user_id, ticker)
        
        if added:
            status_message = f"{ticker}를 관심 종목에 추가했습니다! 매일 오전 10시에 분석 결과를 전송합니다."
        else:
            status_message = f"{ticker}는 이미 관심 종목입니다."
        
        # 백그라운드에서 분석 시작  
        import asyncio

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
                        "messageText": "다른 종목을 추가해주세요"
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
                            "text": f"{ticker} 추가 중 오류가 발생했습니다.\n\n오류 내용: {str(e)}\n\n다른 종목 코드로 다시 시도해주세요."
                        }
                    }
                ]
            }
        }


@app.post("/detail/{ticker}")
async def get_detailed_analysis(ticker: str, request: Request):
    """상세 분석 결과 조회"""
    try:
        # 데이터베이스에서 분석 결과 확인 (1시간 이내)
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=1)
        
        if analysis_data:
            if analysis_data.get("error"):
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
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=1)
        
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
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=1)
        
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
                                "text": f"⏰ {ticker} 펀더멘털 분석 결과가 아직 준비되지 않았습니다.\n\n'{ticker}'를 입력하여 새로운 분석을 시작하세요."
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
        analysis_data = await AnalysisDB.get_analysis(ticker, max_age_hours=1)
        
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
                                "text": f"⏰ {ticker} 뉴스 분석 결과가 아직 준비되지 않았습니다.\n\n'{ticker}'를 입력하여 새로운 분석을 시작하세요."
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
                            "text": f"🧹 데이터베이스 정리 완료\n\n삭제된 오래된 분석 결과: {deleted_count}개"
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
        from datetime import datetime, timezone
        cutoff_time = datetime.now(timezone.utc).timestamp() - (24 * 3600)
        recent_analyses = await analyses_collection.count_documents({
            "timestamp": {"$gte": datetime.fromtimestamp(cutoff_time, tz=timezone.utc)}
        })
        
        # 전체 분석 결과 수
        total_analyses = await analyses_collection.count_documents({})
        
        return {
            "users": {
                "total_users": user_count
            },
            "analyses": {
                "recent_24h": recent_analyses,
                "total": total_analyses
            },
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": time.time()
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
👤 내 계정 정보

📊 관심 종목: {len(tickers)}개
📅 가입일: {created_str}
🔄 최근 업데이트: {updated_str}

📋 관심 종목 목록:
{chr(10).join([f"• {ticker}" for ticker in tickers]) if tickers else "• 없음"}
            """
        else:
            message = """
👤 새로운 사용자입니다!

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
    uvicorn.run('kakao:app', port=8000, reload=True)
