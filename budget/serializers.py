"""DRF serializers for the budget app."""

from rest_framework import serializers

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


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = "__all__"


class IncomeStreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncomeStream
        fields = "__all__"


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = "__all__"


class OutgoingCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OutgoingCategory
        fields = "__all__"


class OutgoingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Outgoing
        fields = "__all__"


class OutgoingVarianceSerializer(serializers.ModelSerializer):
    delta = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OutgoingVariance
        fields = "__all__"


class OneOffOutgoingSerializer(serializers.ModelSerializer):
    class Meta:
        model = OneOffOutgoing
        fields = "__all__"


class PotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pot
        fields = "__all__"


class PotEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PotEntry
        fields = "__all__"
