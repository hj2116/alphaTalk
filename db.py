import motor.motor_asyncio
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# MongoDB 클라이언트 설정
client = motor.motor_asyncio.AsyncIOMotorClient(
    os.getenv('MONGO_URI', 'mongodb://localhost:27017')
)
db = client.alphatalk

# 컬렉션
analyses_collection = db.analyses
users_collection = db.users

class TickersDb:
    @staticmethod
    async def add_ticker(ticker: str):
        try:
            if ticker in await TickersDb.get_all_tickers():
                return False
            await db.companies_list.insert_one({"ticker": ticker})
            return True
        except Exception as e:
            print(f"종목 추가 오류: {e}")
            return False
    
    @staticmethod
    async def get_all_tickers():
        try:
            cursor = db.companies_list.find({})
            tickers = []
            async for doc in cursor:
                tickers.append(doc["ticker"])
            return tickers
        except Exception as e:
            print(f"모든 종목 조회 오류: {e}")
            return []
    @staticmethod
    async def remove_ticker(ticker: str):
        try:
            await db.companies_list.delete_one({"ticker": ticker})
            return True
        except Exception as e:
            print(f"종목 제거 오류: {e}")
            return False
    
class UserDB:
    @staticmethod
    async def add_user_ticker(user_id: str, ticker: str):
        try:
            ticker = ticker.upper()
            
            user_doc = await db.users.find_one({"user_id": user_id})
            
            if user_doc:
                if ticker in user_doc.get("tickers", []):
                    return False  
                
                await db.users.update_one(
                    {"user_id": user_id},
                    {
                        "$push": {"tickers": ticker},
                        "$set": {"updated_at": datetime.now(timezone.utc)}
                    }
                )
            else:
                await db.users.insert_one({
                    "user_id": user_id,
                    "tickers": [ticker],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                })
            
            return True
        except Exception as e:
            print(f"사용자 관심 종목 추가 오류: {e}")
            return False
    
    @staticmethod
    async def get_user_tickers(user_id: str):
        """사용자의 관심 종목 목록 조회"""
        try:
            user_doc = await db.users.find_one({"user_id": user_id})
            if user_doc:
                return user_doc.get("tickers", [])
            return []
        except Exception as e:
            print(f"사용자 관심 종목 조회 오류: {e}")
            return []
    
    @staticmethod
    async def remove_user_ticker(user_id: str, ticker: str):
        try:
            ticker = ticker.upper()
            
            result = await db.users.update_one(
                {"user_id": user_id},
                {
                    "$pull": {"tickers": ticker},
                    "$set": {"updated_at": datetime.now(timezone.utc)}
                }
            )
            
            return result.modified_count > 0
        except Exception as e:
            print(f"사용자 관심 종목 제거 오류: {e}")
            return False
    
    @staticmethod
    async def get_ticker_users(ticker: str): # 특정 종목을 관심 종목으로 등록한 사용자들 조회 필요한진 아직 모름
        try:
            ticker = ticker.upper()
            cursor = db.users.find({"tickers": ticker})
            users = []
            async for doc in cursor:
                users.append(doc["user_id"])
            return users
        except Exception as e:
            print(f"종목별 사용자 조회 오류: {e}")
            return []
    
    @staticmethod
    async def get_all_users_count():
        try:
            count = await db.users.count_documents({})
            return count
        except Exception as e:
            print(f"사용자 수 조회 오류: {e}")
            return 0
    
    @staticmethod
    async def get_user_info(user_id: str):
        try:
            user_doc = await db.users.find_one({"user_id": user_id})
            return user_doc
        except Exception as e:
            print(f"사용자 정보 조회 오류: {e}")
            return None
    
    
class AnalysisDB:
    @staticmethod
    async def save_analysis(ticker: str, analysis_data: Dict[str, Any]) -> bool:
        try:
            document = {
                "ticker": ticker.upper(),
                "timestamp": datetime.now(timezone.utc),
                "quant_analysis": analysis_data.get("quant", ""),
                "fundamental_analysis": analysis_data.get("fundamental", ""),
                "news_analysis": analysis_data.get("news", ""),
                "final_recommendation": analysis_data.get("final", ""),
                "error": analysis_data.get("error", None)
            }
            
            await analyses_collection.update_one(
                {"ticker": ticker.upper()},
                {"$set": document},
                upsert=True
            )
            return True
        except Exception as e:
            print(f"분석 결과 저장 오류: {e}")
            return False
    
    @staticmethod
    async def get_analysis(ticker: str, max_age_hours: int = 1) -> Optional[Dict[str, Any]]:
        try:
            cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
            
            document = await analyses_collection.find_one({
                "ticker": ticker.upper(),
                "timestamp": {"$gte": datetime.fromtimestamp(cutoff_time, tz=timezone.utc)}
            })
            
            if document:
                return {
                    "timestamp": document["timestamp"].timestamp(),
                    "quant": document.get("quant_analysis", ""),
                    "fundamental": document.get("fundamental_analysis", ""),
                    "news": document.get("news_analysis", ""),
                    "final": document.get("final_recommendation", ""),
                    "error": document.get("error", None)
                }
            return None
        except Exception as e:
            print(f"분석 결과 조회 오류: {e}")
            return None
    
    @staticmethod
    async def delete_old_analyses(days: int = 7):
        try:
            cutoff_time = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)
            result = await analyses_collection.delete_many({
                "timestamp": {"$lt": datetime.fromtimestamp(cutoff_time, tz=timezone.utc)}
            })
            print(f"삭제된 오래된 분석 결과: {result.deleted_count}개")
            return result.deleted_count
        except Exception as e:
            print(f"오래된 분석 결과 삭제 오류: {e}")
            return 0

async def test_connection():
    try:
        await client.admin.command('ping')
        print("MongoDB 연결 성공")
        return True
    except Exception as e:
        print(f"MongoDB 연결 실패: {e}")
        return False 