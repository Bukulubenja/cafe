from django.contrib import admin

from .models import Branch, Cafe


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(Cafe)
class CafeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BranchInline]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "is_active", "created_at")
    list_filter = ("tenant", "is_active")
