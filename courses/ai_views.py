from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ai_chat(request):
    """
    POST /api/courses/ai/chat/
    Body: {"message": "hello"}
    Returns a dynamic response for now, avoiding any static/hardcoded medical terminology.
    """
    message = request.data.get('message', '').strip()
    user = request.user
    org_name = user.organization.name if user.organization else "the platform"
    
    if not message:
        return Response({"reply": "Please ask a question."})
        
    reply = f"Hello {user.first_name or user.username}, I am your AI assistant for {org_name}. I received your message: '{message}'. Note: Full LLM integration is pending, but I am ready to be connected!"
    
    return Response({"reply": reply})
