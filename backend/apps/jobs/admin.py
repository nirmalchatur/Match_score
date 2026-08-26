from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "title",
        "match_score",
        "decision",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "decision",
    )

    search_fields = (
        "company",
        "title",
        "url",
    )