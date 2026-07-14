from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "tenant", "branch", "actor", "action")
    list_filter = ("tenant", "branch", "action")
    ordering = ("-created_at",)
    readonly_fields = ("tenant", "branch", "actor", "action", "object_repr", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
