"""The voice WebSocket (docs/VOICE_PROTOCOL.md). Not part of the OpenAPI contract (FastAPI does not list WebSocket routes)."""
from uuid import UUID

from fastapi import APIRouter, WebSocket

from ..voice.session import VoiceSession

router = APIRouter(tags=["voice"])


@router.websocket("/student/sessions/{sid}/voice")
async def voice(ws: WebSocket, sid: str):
    try:
        session_id = UUID(sid)
    except ValueError:
        await ws.close(code=4403)
        return
    if ws.app.state.settings.contract_stub:
        await ws.close(code=4400)
        return
    await VoiceSession(ws, session_id, ws.app.state).run()
