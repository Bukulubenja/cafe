from django.contrib import admin

from .models import PayrollLine, PayrollRun, SalaryRecord


@admin.register(SalaryRecord)
class SalaryRecordAdmin(admin.ModelAdmin):
    list_display = ("staff", "branch", "base_salary", "effective_date")
    list_filter = ("branch",)


class PayrollLineInline(admin.TabularInline):
    model = PayrollLine
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("branch", "period_start", "period_end", "total_paid", "processed_by")
    list_filter = ("branch",)
    inlines = [PayrollLineInline]
