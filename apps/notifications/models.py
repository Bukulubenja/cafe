from django.db import models

from apps.core.models import BranchModel


class NotificationLog(BranchModel):
    """A record of a WhatsApp notification attempt (readme: receipts to
    customers, daily sales summaries to the owner, low-stock alerts to the
    manager, purchase orders to suppliers). Kept regardless of backend, so
    there's a real audit trail even while WHATSAPP_BACKEND is the console
    stub (no real provider configured yet).
    """

    class NotificationType(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        DAILY_SUMMARY = "daily_summary", "Daily Summary"
        LOW_STOCK = "low_stock", "Low Stock Alert"
        PURCHASE_ORDER = "purchase_order", "Purchase Order"

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    recipient_phone = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices)
    object_repr = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_notification_type_display()} -> {self.recipient_phone} ({self.status})"
