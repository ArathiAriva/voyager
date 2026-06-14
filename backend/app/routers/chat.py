from fastapi import APIRouter
from app.models.chat import ChatRequest, ChatResponse, Message

router = APIRouter(prefix="/chat", tags=["chat"])

# Placeholder responses until the LLM is wired in (Month 1)
STUB_REPLIES = [
    "That sounds like a wonderful destination! I'd love to help you plan it.",
    "Great question. I'm still learning your travel preferences — tell me more about what you enjoy.",
    "I can help with itineraries, local tips, and packing lists. What would you like to start with?",
    "Based on your past trips, I think you'd love somewhere with culture and good food. Have you considered Portugal?",
    "I'll remember this for your next trip. Memory systems are coming in Month 2!",
]

_reply_index = 0


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    global _reply_index
    reply = STUB_REPLIES[_reply_index % len(STUB_REPLIES)]
    _reply_index += 1
    return ChatResponse(message=Message(role="assistant", content=reply))
