from .models import ActivityLog

def log_activity(request, action, target=None, organization=None, metadata=None):
    ActivityLog.objects.create(
        actor=request.user if request and request.user.is_authenticated else None,
        actor_role_snapshot=getattr(request.user.role, 'name', None) if request and getattr(request.user, 'role', None) else None,
        organization=organization or (getattr(request.user, 'organization', None) if request else None),
        action=action,
        target_type=type(target).__name__ if target else None,
        target_id=target.id if target else None,
        target_label=str(target) if target else None,
        metadata=metadata or {},
        ip_address=request.META.get('REMOTE_ADDR') if request and hasattr(request, 'META') else None,
    )
