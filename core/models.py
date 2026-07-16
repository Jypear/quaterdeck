"""Core models — singleton Settings for the Quaterdeck instance."""

import secrets

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
    ai_web_search = models.BooleanField(
        default=False,
        help_text="Let the AI search the web when enriching notes. Anthropic and OpenAI only — ignored by Ollama.",
    )
    ai_system_prompt = models.TextField(
        blank=True,
        default="",
        help_text="Sent as a system prompt on every AI request — e.g. your location, currency, or units, "
        "so suggestions and web-searched prices make sense for you.",
    )

    # Webhooks
    webhook_inbound_secret = EncryptedCharField(
        blank=True,
        default="",
        help_text="HMAC secret external services must sign inbound webhook requests with.",
    )

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    def __str__(self) -> str:
        return "Quaterdeck Settings"

    @classmethod
    def get(cls) -> "Settings":
        """Return the singleton Settings row, creating it if absent.

        Auto-generates the inbound webhook signing secret on first access so
        there's always a usable secret without a separate setup step.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        if not obj.webhook_inbound_secret:
            obj.webhook_inbound_secret = secrets.token_hex(32)
            obj.save(update_fields=["webhook_inbound_secret"])
        return obj
