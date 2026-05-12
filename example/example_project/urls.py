from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("healthz/", views.healthz, name="healthz"),
    path(
        "preview/<str:variant>/",
        views.preview_blocked,
        name="preview-blocked",
    ),
    path(
        "preview/<str:variant>/indefinite/",
        views.preview_blocked_indefinite,
        name="preview-blocked-indefinite",
    ),
]
