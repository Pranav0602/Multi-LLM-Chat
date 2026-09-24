"""FastAPI entrypoint — plan sections 2, 19, 21."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine, ensure_chat_type_column
from .routers import conversations, groups

# Import models so Base.metadata is populated before create_all.
from . import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        ensure_chat_type_column()
    except Exception as exc:
        # Never block startup: a dead DB must not turn /health into a 502.
        print(f"WARNING: database init failed: {exc}", flush=True)
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(groups.router)
app.include_router(groups.model_router)
app.include_router(conversations.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "docs": "/docs", "health": "/health"}
