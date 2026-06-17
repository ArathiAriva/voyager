from fastapi import APIRouter, HTTPException
from app.models.chat import ChatRequest, ChatResponse, Message
from app.claude import get_client, get_model

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are Voyager, an AI travel companion. "
    "Help users plan trips, discover destinations, build itineraries, and get local tips. "
    "Be concise, warm, and enthusiastic about travel."
)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    client = get_client()
    try:
        response = await client.chat.completions.create(
            model=get_model(),
            messages=[{"role": "system", "content": SYSTEM_PROMPT}]
            + [{"role": m.role, "content": m.content} for m in request.messages],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    content = response.choices[0].message.content or ""
    return ChatResponse(message=Message(role="assistant", content=content))
