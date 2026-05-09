import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=32, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, default='Nigeria', blank=True)
    preferred_categories = models.JSONField(default=list, blank=True)
    preferred_languages = models.JSONField(default=list, blank=True)
    preferred_age_groups = models.JSONField(default=list, blank=True)
    max_distance_km = models.PositiveIntegerField(null=True, blank=True)
    email_notifications = models.BooleanField(default=True)
    event_reminders = models.BooleanField(default=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


class AuthToken(models.Model):
    key = models.CharField(max_length=64, unique=True, editable=False)
    user = models.ForeignKey(User, related_name='auth_tokens', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for_user(cls, user):
        return cls.objects.create(user=user, key=secrets.token_hex(32))

    def __str__(self):
        return f'{self.user_id}:{self.key[:8]}'


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Event(models.Model):
    PRICING_CHOICES = (
        ('free', 'Free'),
        ('paid', 'Paid'),
    )
    APPROVAL_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    organizer = models.CharField(max_length=255, blank=True)
    date = models.DateTimeField()
    location = models.CharField(max_length=255)
    pricing = models.CharField(max_length=20, choices=PRICING_CHOICES)
    category = models.CharField(max_length=80)
    event_type = models.CharField(max_length=80)
    language = models.CharField(max_length=80)
    age_group = models.CharField(max_length=80)
    created_by = models.ForeignKey(User, related_name='events', on_delete=models.CASCADE)
    approval_status = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default='approved')
    image = models.FileField(upload_to='events/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class EventLike(models.Model):
    user = models.ForeignKey(User, related_name='event_likes', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, related_name='likes', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='unique_event_like'),
        ]


class EventSave(models.Model):
    user = models.ForeignKey(User, related_name='event_saves', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, related_name='saves', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='unique_event_save'),
        ]

# Create your models here.
