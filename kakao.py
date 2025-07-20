from fastapi import FastAPI, Request
import uvicorn

app = FastAPI()

@app.get("/")
async def root(request: Request):
    return {"message": "Kakao Test!"}

@app.post("/chat/")
async def chat(request: Request):
    data = await request.json()
    print(data)
    return 


if __name__ == '__main__':
    uvicorn.run('kakao:app', port=8000, reload=True)
