from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Max, Count
from django.contrib.auth import get_user_model
from .models import ChatMessage
from .serializers import ChatMessageSerializer

User = get_user_model()


class ChatConversationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        # Super admins don't belong to a tenant organization and cannot use tenant chat
        if not org or user.is_platform_super_admin:
            return Response([])

        # Strict Tenant Isolation: Only get active non-superadmin users in the user's organization
        target_users = User.objects.filter(
            is_active=True,
            organization=org,
            is_platform_super_admin=False
        ).exclude(id=user.id).distinct()

        contacts = []
        for u in target_users:
            last_msg = ChatMessage.objects.filter(
                organization=org,
                sender__in=[user, u],
                recipient__in=[user, u]
            ).order_by('-created_at').first()

            unread_cnt = ChatMessage.objects.filter(
                organization=org,
                sender=u,
                recipient=user,
                is_read=False
            ).count()

            is_org_admin = bool(u.role and u.role.is_admin_role) or u.is_staff

            contacts.append({
                'id': u.id,
                'full_name': u.full_name,
                'email': u.email,
                'avatar_initials': u.avatar_initials,
                'job_title': u.job_title or (u.role.name if u.role else 'Member'),
                'role_name': u.role.name if u.role else 'Member',
                'last_message': last_msg.message if last_msg else '',
                'last_message_at': last_msg.created_at.isoformat() if last_msg else None,
                'unread_count': unread_cnt,
                'is_admin': is_org_admin
            })

        # Sort contacts by latest message timestamp (messages first, then alphabetical)
        contacts.sort(key=lambda x: (x['last_message_at'] or '', x['full_name']), reverse=True)
        return Response(contacts)


class ChatMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organization

        if not org or user.is_platform_super_admin:
            return Response([])

        with_user_id = request.query_params.get('with_user')
        if not with_user_id:
            return Response([])

        try:
            with_user_id = int(with_user_id)
        except ValueError:
            raise ValidationError({'with_user': 'Invalid user ID'})

        # Tenant isolation check: with_user MUST belong to the same organization and not be superadmin
        with_user = User.objects.filter(
            pk=with_user_id,
            is_active=True,
            organization=org,
            is_platform_super_admin=False
        ).first()

        if not with_user:
            return Response([])

        # Mark incoming unread messages as read
        ChatMessage.objects.filter(
            organization=org,
            sender=with_user,
            recipient=user,
            is_read=False
        ).update(is_read=True)

        messages = ChatMessage.objects.filter(
            organization=org,
            sender__in=[user, with_user],
            recipient__in=[user, with_user]
        ).order_by('created_at')

        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request):
        user = request.user
        org = user.organization

        if not org or user.is_platform_super_admin:
            return Response({'detail': 'Internal Messenger is restricted to organization tenant users.'}, status=403)

        recipient_id = request.data.get('recipient_id')
        message_text = request.data.get('message', '').strip()

        if not recipient_id:
            raise ValidationError({'recipient_id': 'Recipient user ID is required.'})
        if not message_text:
            raise ValidationError({'message': 'Message text cannot be empty.'})

        # Tenant isolation check: recipient MUST belong to the same organization and not be superadmin
        recipient = User.objects.filter(
            pk=recipient_id,
            is_active=True,
            organization=org,
            is_platform_super_admin=False
        ).first()

        if not recipient:
            raise ValidationError({'recipient_id': 'Recipient user not found in your organization.'})

        chat_msg = ChatMessage.objects.create(
            organization=org,
            sender=user,
            recipient=recipient,
            message=message_text
        )

        # Create notification for the recipient
        try:
            from master_setup.models import Notification
            sender_name = user.full_name or user.username
            snippet = message_text[:80] + ('...' if len(message_text) > 80 else '')
            Notification.objects.create(
                recipient=recipient,
                title=f"New Message from {sender_name}",
                message=f'{sender_name} sent you a message: "{snippet}"',
                type="chat"
            )
        except Exception as err:
            print("Failed to create chat notification:", err)

        serializer = ChatMessageSerializer(chat_msg)
        return Response(serializer.data, status=201)
