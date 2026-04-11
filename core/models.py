"""Core models — singleton Settings for the Quaterdeck instance."""

from django.db import models

from core.fields import EncryptedCharField


class Settings(models.Model):
    """Singleton model storing instance-wide configuration."""

    class BudgetMode(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    class AiProvider(models.TextChoices):
        NONE = "none", "None"
        ANTHROPIC = "anthropic", "Anthropic (Claude)"
        OPENAI = "openai", "OpenAI"
        OLLAMA = "ollama", "Ollama (local)"

    # Display / locale
    currency = models.CharField(max_length=3, default="GBP")

    # Budget window
    budget_mode = models.CharField(max_length=10, choices=BudgetMode, default=BudgetMode.MONTHLY)
    budget_start_day = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of week (1-7) for weekly mode; day of month (1-31) for monthly/yearly.",
    )

    # Auth gate
    require_login = models.BooleanField(
        default=False,
        help_text="When True, the entire app requires a Django session login.",
    )

    # AI provider
    ai_provider = models.CharField(max_length=20, choices=AiProvider, default=AiProvider.NONE)
    ai_api_key = EncryptedCharField(blank=True, default="")
    ai_model = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    def __str__(self) -> str:
        return "Quaterdeck Settings"

    @classmethod
    def get(cls) -> "Settings":
        """Return the singleton Settings row, creating it if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
