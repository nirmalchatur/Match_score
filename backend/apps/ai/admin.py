"""
Django admin registration for AI runs.

Operational, not user-facing: this is where "what did the last ten tailoring
runs actually do" gets answered when a user reports that tailoring "just does
not work". Read-only, and deliberately so -- a run row is evidence, and an
editable one is not.
"""

from django.contrib import admin

from .models import AIRun


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "operation",
        "provider",
        "model",
        "status",
        "validation_status",
        "failure_category",
        "duration_ms",
    )
    list_filter = ("status", "operation", "provider", "failure_category")
    search_fields = ("user__email", "error_code", "model")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
