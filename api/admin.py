from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms

from .models import AuthToken, Category, Event, EventLike, EventSave, User


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


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug', 'description')


class EventAdminForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        empty_label='Select a category',
    )

    class Meta:
        model = Event
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.category:
            self.fields['category'].initial = Category.objects.filter(
                slug=self.instance.category
            ).first()

    def clean_category(self):
        category = self.cleaned_data['category']
        return category.slug


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ('id', 'title', 'organizer', 'category', 'date', 'location', 'created_by', 'approval_status')
    list_filter = ('approval_status', 'pricing', 'category', 'language', 'age_group')
    readonly_fields = ('created_by',)
    search_fields = ('title', 'description', 'organizer', 'location')

    def save_model(self, request, obj, form, change):
        if not change or not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


admin.site.register(AuthToken)
admin.site.register(EventLike)
admin.site.register(EventSave)

# Register your models here.
