from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from debate_pipeline import DEFAULT_MODEL, run_debate, stream_debate

app = FastAPI(title="DebateRAG Demo")


class DebateRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: list[str] = Field(..., min_length=1)
    model: str | None = None
    top_k: int = Field(6, ge=1, le=20)
    rounds: int = Field(2, ge=1, le=4)


@app.post("/api/debate")
async def debate_endpoint(payload: DebateRequest):
    model_name = payload.model or DEFAULT_MODEL
    try:
        result = run_debate(
            documents=payload.documents,
            query=payload.query,
            model_name=model_name,
            top_k=payload.top_k,
            rounds=payload.rounds,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws/debate")
async def debate_websocket(ws: WebSocket):
    await ws.accept()
    try:
        try:
            payload = await asyncio.wait_for(ws.receive_json(), timeout=5)
        except asyncio.TimeoutError:
            await ws.send_json(
                {
                    "event": "error",
                    "detail": "No payload received. Send JSON after connecting.",
                }
            )
            await ws.close()
            return
        request = DebateRequest(**payload)
        model_name = request.model or DEFAULT_MODEL
        await ws.send_json({"event": "ready"})

        await ws.send_json({"event": "ready"})
        await asyncio.sleep(0)

        queue: asyncio.Queue[dict] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def run_pipeline():
            try:
                for event in stream_debate(
                    documents=request.documents,
                    query=request.query,
                    model_name=model_name,
                    top_k=request.top_k,
                    rounds=request.rounds,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:  # pragma: no cover - defensive
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"event": "error", "detail": f"Pipeline error: {exc}"},
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, {"event": "_done"})

        pipeline_task = asyncio.create_task(asyncio.to_thread(run_pipeline))

        while True:
            event = await queue.get()
            if event.get("event") == "_done":
                break
            await ws.send_json(event)

        await pipeline_task
        await ws.close()
    except WebSocketDisconnect:
        return
    except ValidationError as exc:
        await ws.send_json({"event": "error", "detail": exc.errors()})
    except ValueError as exc:
        await ws.send_json({"event": "error", "detail": str(exc)})
    except RuntimeError as exc:
        await ws.send_json({"event": "error", "detail": str(exc)})
    except Exception as exc:  # pragma: no cover - safety net
        await ws.send_json({"event": "error", "detail": f"Unexpected error: {exc}"})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("web/index.html")


app.mount("/web", StaticFiles(directory="web"), name="web")
