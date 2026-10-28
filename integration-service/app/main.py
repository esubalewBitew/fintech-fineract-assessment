from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.db.session import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Integration Service", version="1.0.0", lifespan=lifespan)
app.include_router(router)
