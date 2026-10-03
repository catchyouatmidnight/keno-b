"""One resident multilingual Laya checkpoint, local files only."""
import asyncio
import os
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from laya import Router
from pydantic import BaseModel, ConfigDict, Field


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: dict
    questions: dict
    model: str = "multilingual"
    max_len: int = Field(default=1024, ge=64, le=1024)
    head_max_len: int = Field(default=256, ge=64, le=256)


@asynccontextmanager
async def lifespan(app):
    torch.set_num_threads(int(os.environ.get("LAYA_THREADS", "2")))
    torch.set_num_interop_threads(1)
    app.state.router = Router(models={"multilingual": "/models/laya"}, device="cpu", max_loaded=1, default="multilingual")
    app.state.router.load("multilingual")
    app.state.lock = asyncio.Lock()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/systemone")
async def predict(value: DecisionRequest):
    if value.model != "multilingual" or len(value.questions) > 4 or len(str(value.state)) > 10000:
        raise HTTPException(422, "Decision exceeds the local router limits")
    async with app.state.lock:
        try:
            return await asyncio.to_thread(app.state.router.predict, value.state, value.questions,
                                           model="multilingual", max_len=value.max_len, head_max_len=value.head_max_len)
        except Exception:
            raise HTTPException(503, "Local decision failed")
