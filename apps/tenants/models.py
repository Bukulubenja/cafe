from django.db import models
from django.utils.text import slugify


class Cafe(models.Model):
    """A tenant: one café/restaurant business account.

    A Cafe may operate multiple physical Branches under one owner login,
    one staff pool, and one shared menu/recipe catalogue.
    """

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Branch(models.Model):
    """A physical location belonging to a Cafe (tenant)."""

    tenant = models.ForeignKey(Cafe, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_branch_name_per_cafe"),
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"
