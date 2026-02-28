from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Founder OS API")

app.include_router(router)

@app.get("/")
def root():
    return {"message": "Founder OS API running"}