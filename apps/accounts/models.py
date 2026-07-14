from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.OWNER)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """A staff member of a café. Platform-level superusers (no café) are
    also instances of this model, with cafe=None.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        WAITER = "waiter", "Waiter"
        CHEF = "chef", "Chef"
        CASHIER = "cashier", "Cashier"

    username = models.CharField(max_length=150, unique=False, blank=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, blank=True)
    cafe = models.ForeignKey(
        "tenants.Cafe", on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )
    branch = models.ForeignKey(
        "tenants.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    def clean(self):
        super().clean()
        if self.cafe_id and self.role and self.role != self.Role.OWNER and not self.branch_id:
            raise ValidationError({"branch": "Staff below Owner must be assigned to a branch."})
        if self.branch_id and self.cafe_id and self.branch.tenant_id != self.cafe_id:
            raise ValidationError({"branch": "Branch must belong to the user's café."})
        if self.cafe_id is None and not self.is_superuser and self.role:
            raise ValidationError({"cafe": "Café staff must belong to a café."})

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_waiter(self):
        return self.role == self.Role.WAITER

    @property
    def is_chef(self):
        return self.role == self.Role.CHEF

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER
