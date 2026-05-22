from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.storage.db import init_db

# main.py 阅读地图：
# 1. 创建 FastAPI app。
# 2. include_router(router) 注册 routes.py 里的所有后端接口。
# 3. mount("/web", ...) 挂载静态前端页面。
# 4. 启动时调用 init_db()，确保 SQLite 表和教学数据准备好。


app = FastAPI(title=settings.app_name)
app.include_router(router)
app.mount("/web", StaticFiles(directory="web", html=True), name="web")


# 启动钩子：后端启动时初始化数据库。
@app.on_event("startup")
def on_startup() -> None:
    init_db()
