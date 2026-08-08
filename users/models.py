from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    # Platform-level super admin — NOT org-scoped, sees all orgs.
    # This is a flag, not a Role, because a Role always belongs to one Organization
    # and super-admins don't belong to one.
    is_platform_super_admin = models.BooleanField(default=False)

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='users'
    )
    department = models.ForeignKey(
        'organizations.Department', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users'
    )
    role = models.ForeignKey(
        'organizations.Role', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users'
    )

    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    # Gamification fields
    job_title = models.CharField(max_length=255, blank=True, default='')
    region = models.CharField(max_length=100, blank=True, default='')
    points = models.IntegerField(default=0)
    streak_days = models.IntegerField(default=0)
    level = models.IntegerField(default=1)
    badges = models.JSONField(default=list, blank=True)

    # Theme preference
    THEME_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]
    theme_preference = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default='dark'
    )

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.is_platform_super_admin = True
            self.is_staff = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} - {self.role.name if self.role else 'no role'}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def avatar_initials(self):
        parts = self.full_name.split()
        return "".join(p[0].upper() for p in parts[:2]) if parts else self.username[:2].upper()


class ChatMessage(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='chat_messages'
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='received_messages'
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Chat ({self.sender.username} -> {self.recipient.username}): {self.message[:30]}"


