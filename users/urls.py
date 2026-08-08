from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import UserListCreateView, UserDetailView, LearnerDashboardStatsView, SuperAdminListCreateView
from .auth_views import LoginView, MeView, ChangePasswordView, RegisterView, ForgotPasswordView, ResetPasswordConfirmView, UpdateThemePreferenceView

from .chat_views import ChatConversationsView, ChatMessageListCreateView

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('auth/reset-password/', ResetPasswordConfirmView.as_view(), name='auth-reset-password'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', MeView.as_view(), name='auth-me'),
    path('auth/theme/', UpdateThemePreferenceView.as_view(), name='auth-theme'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('me/learner-stats/', LearnerDashboardStatsView.as_view(), name='learner-stats'),
    path('chat/conversations/', ChatConversationsView.as_view(), name='chat-conversations'),
    path('chat/messages/', ChatMessageListCreateView.as_view(), name='chat-messages'),
    path('super-admins/', SuperAdminListCreateView.as_view(), name='super-admin-list-create'),
    path('super-admins/<int:pk>/', SuperAdminListCreateView.as_view(), name='super-admin-detail'),
    path('', UserListCreateView.as_view(), name='user-list-create'),
    path('<int:pk>/', UserDetailView.as_view(), name='user-detail'),
]
