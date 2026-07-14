from rest_framework import serializers

from apps.accounts.fields import TenantUserField

from .models import PayrollLine, PayrollRun, SalaryRecord


class SalaryRecordSerializer(serializers.ModelSerializer):
    staff = TenantUserField()
    staff_email = serializers.CharField(source="staff.email", read_only=True)

    class Meta:
        model = SalaryRecord
        fields = ["id", "staff", "staff_email", "base_salary", "effective_date", "notes", "created_at"]
        read_only_fields = ["created_at"]


class PayrollLineSerializer(serializers.ModelSerializer):
    staff_email = serializers.CharField(source="staff.email", read_only=True, default=None)

    class Meta:
        model = PayrollLine
        fields = ["id", "staff", "staff_email", "amount"]
        read_only_fields = fields


class PayrollRunSerializer(serializers.ModelSerializer):
    lines = PayrollLineSerializer(many=True, read_only=True)
    processed_by_email = serializers.CharField(source="processed_by.email", read_only=True, default=None)

    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "period_start",
            "period_end",
            "processed_by",
            "processed_by_email",
            "total_paid",
            "lines",
            "created_at",
        ]
        read_only_fields = fields


class ProcessPayrollSerializer(serializers.Serializer):
    period_start = serializers.DateField()
    period_end = serializers.DateField()
