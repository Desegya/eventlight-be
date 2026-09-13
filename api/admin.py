from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .models import Category, Event, EventLike, EventSave, Notification, RSVP, User
from .services import notify_event_cancelled, notify_event_status_change


admin.site.site_header = 'EventLight Admin'
admin.site.site_title = 'EventLight Admin'
admin.site.index_title = 'Operations'


class RSVPInline(admin.TabularInline):
    model = RSVP
    fields = ('user', 'created_at')
    readonly_fields = ('user', 'created_at')
    extra = 0
    ordering = ('-created_at',)

    def has_add_permission(self, request, obj=None):
        return False


class EventLikeInline(admin.TabularInline):
    model = EventLike
    fields = ('user', 'created_at')
    readonly_fields = ('user', 'created_at')
    extra = 0
    verbose_name = 'like'
    verbose_name_plural = 'likes'

    def has_add_permission(self, request, obj=None):
        return False


class EventSaveInline(admin.TabularInline):
    model = EventSave
    fields = ('user', 'created_at')
    readonly_fields = ('user', 'created_at')
    extra = 0
    verbose_name = 'save'
    verbose_name_plural = 'saves'

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = [
        *UserAdmin.fieldsets,
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
        (
            'Activity',
            {
                'fields': (
                    'events_created_count',
                    'events_liked_count',
                    'events_saved_count',
                    'events_attending_count',
                    'unread_notifications_count',
                )
            },
        ),
    ]
    readonly_fields = (
        'events_created_count',
        'events_liked_count',
        'events_saved_count',
        'events_attending_count',
        'unread_notifications_count',
    )
    list_display = (
        'id',
        'email',
        'username',
        'first_name',
        'last_name',
        'events_created_count',
        'events_attending_count',
        'is_staff',
        'is_active',
    )
    list_filter = ('is_staff', 'is_active', 'email_notifications', 'event_reminders', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)

    @admin.display(description='Created')
    def events_created_count(self, obj):
        return obj.events.count()

    @admin.display(description='Liked')
    def events_liked_count(self, obj):
        return obj.event_likes.count()

    @admin.display(description='Saved')
    def events_saved_count(self, obj):
        return obj.event_saves.count()

    @admin.display(description='Attending')
    def events_attending_count(self, obj):
        return obj.event_rsvps.count()

    @admin.display(description='Unread notifications')
    def unread_notifications_count(self, obj):
        return obj.notifications.filter(is_read=False).count()


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Display', {'fields': ('name', 'slug', 'icon', 'description')}),
        ('Visibility', {'fields': ('sort_order', 'is_active')}),
        ('Stats', {'fields': ('approved_events_count', 'total_events_count', 'created_at', 'updated_at')}),
    )
    readonly_fields = ('approved_events_count', 'total_events_count', 'created_at', 'updated_at')
    list_display = (
        'id',
        'name',
        'slug',
        'icon',
        'sort_order',
        'approved_events_count',
        'total_events_count',
        'is_active',
    )
    list_display_links = ('id', 'name')
    list_editable = ('icon', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug', 'description')
    ordering = ('sort_order', 'name')
    actions = ('activate_categories', 'deactivate_categories')

    @admin.display(description='Approved events')
    def approved_events_count(self, obj):
        return obj.events.filter(approval_status='approved').count()

    @admin.display(description='Total events')
    def total_events_count(self, obj):
        return obj.events.count()

    @admin.action(description='Activate selected categories')
    def activate_categories(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Activated {updated} categories.', messages.SUCCESS)

    @admin.action(description='Deactivate selected categories')
    def deactivate_categories(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated {updated} categories.', messages.SUCCESS)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Basics', {'fields': ('title', 'description', 'organizer', 'category', 'image', 'image_preview')}),
        ('Schedule', {'fields': ('date', 'end_date')}),
        ('Location', {'fields': ('location', 'location_lat', 'location_lng')}),
        ('Pricing and capacity', {'fields': ('pricing', 'ticket_price', 'capacity', 'rsvp_count_display', 'is_full_display')}),
        ('Audience', {'fields': ('language', 'age_group')}),
        ('Review', {'fields': ('approval_status', 'rejection_reason', 'is_featured')}),
        ('Ownership and audit', {'fields': ('created_by', 'created_at', 'updated_at')}),
        ('Engagement', {'fields': ('likes_count_display', 'saves_count_display')}),
    )
    readonly_fields = (
        'created_by',
        'created_at',
        'updated_at',
        'image_preview',
        'rsvp_count_display',
        'likes_count_display',
        'saves_count_display',
        'is_full_display',
    )
    list_display = (
        'id',
        'title',
        'approval_status',
        'is_featured',
        'category',
        'date',
        'organizer',
        'rsvp_count_display',
        'capacity',
        'is_full_display',
        'created_by',
    )
    list_display_links = ('id', 'title')
    list_editable = ('approval_status', 'is_featured')
    list_filter = ('approval_status', 'pricing', 'category', 'language', 'age_group', 'is_featured', 'date')
    search_fields = ('title', 'description', 'organizer', 'location', 'created_by__email', 'created_by__first_name', 'created_by__last_name')
    autocomplete_fields = ('category',)
    date_hierarchy = 'date'
    ordering = ('-created_at',)
    actions = (
        'approve_events',
        'reject_events',
        'mark_pending',
        'feature_events',
        'unfeature_events',
    )
    inlines = (RSVPInline, EventLikeInline, EventSaveInline)

    @admin.display(description='Cover preview')
    def image_preview(self, obj):
        if not obj or not obj.image:
            return 'No image uploaded'
        return format_html('<img src="{}" style="max-width: 280px; max-height: 180px; border-radius: 6px;" />', obj.image.url)

    @admin.display(description='RSVPs')
    def rsvp_count_display(self, obj):
        return obj.rsvps.count() if obj and obj.id else 0

    @admin.display(description='Likes')
    def likes_count_display(self, obj):
        return obj.likes.count() if obj and obj.id else 0

    @admin.display(description='Saves')
    def saves_count_display(self, obj):
        return obj.saves.count() if obj and obj.id else 0

    @admin.display(description='Full?', boolean=True)
    def is_full_display(self, obj):
        return obj.is_full if obj and obj.id else False

    def save_model(self, request, obj, form, change):
        old_status = None
        if change and obj.id:
            old_status = Event.objects.filter(id=obj.id).values_list('approval_status', flat=True).first()
        if not change or not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if old_status and old_status != obj.approval_status:
            notify_event_status_change(obj)

    def delete_model(self, request, obj):
        notify_event_cancelled(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for event in queryset:
            notify_event_cancelled(event)
        super().delete_queryset(request, queryset)

    @admin.action(description='Approve selected events')
    def approve_events(self, request, queryset):
        updated = 0
        for event in queryset.exclude(approval_status='approved').select_related('created_by'):
            event.approval_status = 'approved'
            event.save(update_fields=['approval_status', 'updated_at'])
            notify_event_status_change(event)
            updated += 1
        self.message_user(request, f'Approved {updated} events.', messages.SUCCESS)

    @admin.action(description='Reject selected events')
    def reject_events(self, request, queryset):
        updated = 0
        for event in queryset.exclude(approval_status='rejected').select_related('created_by'):
            event.approval_status = 'rejected'
            if not event.rejection_reason:
                event.rejection_reason = 'Rejected by admin review.'
            event.save(update_fields=['approval_status', 'rejection_reason', 'updated_at'])
            notify_event_status_change(event)
            updated += 1
        self.message_user(request, f'Rejected {updated} events.', messages.WARNING)

    @admin.action(description='Move selected events back to pending')
    def mark_pending(self, request, queryset):
        updated = queryset.exclude(approval_status='pending').update(approval_status='pending')
        self.message_user(request, f'Moved {updated} events to pending.', messages.INFO)

    @admin.action(description='Feature selected events')
    def feature_events(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'Featured {updated} events.', messages.SUCCESS)

    @admin.action(description='Unfeature selected events')
    def unfeature_events(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f'Unfeatured {updated} events.', messages.INFO)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Message', {'fields': ('user', 'type', 'title', 'body', 'detail', 'event')}),
        ('State', {'fields': ('is_read', 'created_at')}),
    )
    readonly_fields = ('created_at',)
    list_display = ('id', 'title', 'type', 'user', 'event', 'is_read', 'created_at')
    list_display_links = ('id', 'title')
    list_editable = ('is_read',)
    list_filter = ('type', 'is_read', 'created_at')
    search_fields = ('title', 'body', 'detail', 'user__email', 'event__title')
    autocomplete_fields = ('user', 'event')
    date_hierarchy = 'created_at'
    actions = ('mark_read', 'mark_unread')

    @admin.action(description='Mark selected notifications as read')
    def mark_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'Marked {updated} notifications as read.', messages.SUCCESS)

    @admin.action(description='Mark selected notifications as unread')
    def mark_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f'Marked {updated} notifications as unread.', messages.INFO)


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'user', 'created_at')
    list_filter = ('created_at', 'event__category')
    search_fields = ('event__title', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('event', 'user')
    date_hierarchy = 'created_at'


@admin.register(EventLike)
class EventLikeAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'user', 'created_at')
    list_filter = ('created_at', 'event__category')
    search_fields = ('event__title', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('event', 'user')
    date_hierarchy = 'created_at'


@admin.register(EventSave)
class EventSaveAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'user', 'created_at')
    list_filter = ('created_at', 'event__category')
    search_fields = ('event__title', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('event', 'user')
    date_hierarchy = 'created_at'


