from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuthToken, Event, EventLike, EventSave, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            'Profile',
            {
                'fields': (
                    'phone_number',
                    'street_address',
                    'city',
                    'state',
                    'country',
                    'preferred_categories',
                    'preferred_languages',
                    'preferred_age_groups',
                    'max_distance_km',
                    'email_notifications',
                    'event_reminders',
                )
            },
        ),
    )
    list_display = ('id', 'email', 'username', 'first_name', 'last_name', 'is_staff')
    ordering = ('email',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'date', 'location', 'created_by', 'approval_status')
    list_filter = ('approval_status', 'pricing', 'category', 'language', 'age_group')
    search_fields = ('title', 'description', 'location')


admin.site.register(AuthToken)
admin.site.register(EventLike)
admin.site.register(EventSave)

# Register your models here.
