from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.storage.db import init_db

app = FastAPI(title=settings.app_name)
app.include_router(router)
app.mount("/web", StaticFiles(directory="web", html=True), name="web")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
