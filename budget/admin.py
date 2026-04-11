from django.contrib import admin

from budget.models import (
    Account,
    IncomeStream,
    OneOffOutgoing,
    Outgoing,
    OutgoingCategory,
    OutgoingVariance,
    Pot,
    PotEntry,
    Transfer,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "is_active")
    list_filter = ("account_type", "is_active")


@admin.register(IncomeStream)
class IncomeStreamAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "frequency", "account")
    list_filter = ("frequency", "account")


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("name", "from_account", "to_account", "amount", "frequency")


@admin.register(OutgoingCategory)
class OutgoingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Outgoing)
class OutgoingAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "category", "frequency", "account")
    list_filter = ("category", "frequency", "account")


@admin.register(OutgoingVariance)
class OutgoingVarianceAdmin(admin.ModelAdmin):
    list_display = ("outgoing", "period_start", "actual_amount")
    list_filter = ("period_start",)


@admin.register(OneOffOutgoing)
class OneOffOutgoingAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "due_date", "account", "linked_pot")


@admin.register(Pot)
class PotAdmin(admin.ModelAdmin):
    list_display = ("name", "target_amount", "target_date", "monthly_target")


@admin.register(PotEntry)
class PotEntryAdmin(admin.ModelAdmin):
    list_display = ("pot", "period_start", "actual_amount")
