"""
Django admin registration for the activity record.

Registered rather than left out because there is no API for it in this phase:
if an operator cannot read the rows, the model is unevidenced code. Read-only
by design -- an append-only record that can be edited from a web form is not
append-only -- and the account is shown as a link so "whose activity is this?"
is answerable from the changelist.
"""

from django.contrib import admin

from .models import ActivityEvent


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "object_type", "object_id", "summary")
    list_filter = ("action", "object_type")
    search_fields = ("user__email", "summary")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def get_readonly_fields(self, request, obj=None):
        # Every field. Grants no edit affordance rather than hiding the form,
        # so an operator still sees what was recorded.
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
