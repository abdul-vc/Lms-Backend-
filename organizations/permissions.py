from rest_framework.permissions import BasePermission


class IsOrgScoped(BasePermission):
    """
    Platform super-admins pass through untouched (see everything).
    Everyone else must belong to an organization; object-level check
    compares obj's org to the requesting user's org.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_platform_super_admin:
            return True
        if request.user.organization_id is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied({'error': 'account_frozen', 'message': 'Kindly contact admin for assistance.'})

        # Live Organization status check — blocks mid-session requests immediately if org is frozen
        if request.user.organization and request.user.organization.status == 'Inactive':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied({'error': 'account_frozen', 'message': 'Kindly contact admin for assistance.'})

        # Live User active status check
        if not request.user.is_active:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied({'error': 'account_frozen', 'message': 'Kindly contact admin for assistance.'})

        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_platform_super_admin:
            return True
        obj_org_id = getattr(obj, 'organization_id', None)
        # Module/Lesson/Block/Tree fallback: traverse the FK chain to reach the org
        if obj_org_id is None and hasattr(obj, 'course'):
            obj_org_id = getattr(obj.course, 'organization_id', None)
        if obj_org_id is None and hasattr(obj, 'module'):
            obj_org_id = getattr(obj.module.course, 'organization_id', None)
        if obj_org_id is None and hasattr(obj, 'block'):
            obj_org_id = getattr(obj.block, 'organization_id', None)
        if obj_org_id is None and hasattr(obj, 'tree'):
            obj_org_id = getattr(obj.tree, 'organization_id', None)
        if obj_org_id != request.user.organization_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(f"IsOrgScoped.has_object_permission Failed. is_super: {request.user.is_platform_super_admin}, obj_org: {obj_org_id}, user_org: {request.user.organization_id}")
        return True
