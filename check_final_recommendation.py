import asyncio
import os
from dotenv import load_dotenv
import motor.motor_asyncio

load_dotenv()

# MongoDB 클라이언트 설정
client = motor.motor_asyncio.AsyncIOMotorClient(
    os.getenv('MONGO_URI', 'mongodb://localhost:27017')
)
db = client.alphatalk

async def check_final_recommendations():
    """최종 추천 내용 전체 확인"""
    print("=== 최종 추천 내용 상세 확인 ===\n")
    
    analyses_cursor = db.analyses.find({}).sort("timestamp", -1)
    
    async for analysis in analyses_cursor:
        ticker = analysis.get('ticker', 'N/A')
        timestamp = analysis.get('timestamp', 'N/A')
        final_rec = analysis.get('final_recommendation', '')
        
        print(f"🔍 {ticker} ({timestamp})")
        print("=" * 60)
        
        if final_rec and final_rec.strip():
            print(final_rec)
        else:
            print("❌ 최종 추천 내용이 비어있습니다!")
        
        print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(check_final_recommendations()) 