from django.urls import path

from . import views

urlpatterns = [
    path('auth/register/', views.register),
    path('auth/login/', views.login),
    path('auth/logout/', views.logout),
    path('auth/user/', views.current_user),
    path('auth/password/change/', views.change_password),
    path('auth/password/reset/', views.password_reset),
    path('auth/password/reset/confirm/', views.password_reset_confirm),
    path('categories/', views.categories_collection),
    path('events/', views.events_collection),
    path('events/liked/', views.liked_events),
    path('events/saved/', views.saved_events),
    path('events/my-events/', views.my_events),
    path('events/<int:event_id>/', views.event_detail),
    path('events/<int:event_id>/like/', views.toggle_like),
    path('events/<int:event_id>/save/', views.toggle_save),
]
