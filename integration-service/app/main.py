from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request, Response

from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Integration Service",
    version="1.0.0",
    description="Middleware between partners/ERP and Fineract (assessment).",
    lifespan=lifespan,
)
register_exception_handlers(app)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = cid
    response: Response = await call_next(request)
    response.headers["X-Correlation-Id"] = cid
    return response


app.include_router(router)
