from fastapi import FastAPI

from app.api.router import router
from app.core.config import get_settings

app = FastAPI(title="FreeSelfTrack API", version="0.1.0")
app.include_router(router, prefix=get_settings().api_prefix)
