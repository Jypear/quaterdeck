"""DRF ModelViewSets for all Quaterdeck resources."""

from typing import ClassVar

from rest_framework.viewsets import ModelViewSet

from budget.models import (
    Account,
    IncomeStream,
    OneOffOutgoing,
    Outgoing,
    OutgoingCategory,
    Pot,
    PotEntry,
    Transfer,
)
from budget.serializers import (
    AccountSerializer,
    IncomeStreamSerializer,
    OneOffOutgoingSerializer,
    OutgoingCategorySerializer,
    OutgoingSerializer,
    PotEntrySerializer,
    PotSerializer,
    TransferSerializer,
)
from notes.models import Note
from notes.serializers import NoteSerializer
from projects.models import Project
from projects.serializers import ProjectSerializer
from tasks.models import Task
from tasks.serializers import TaskSerializer
from webhooks.models import WebhookDelivery, WebhookEndpoint
from webhooks.serializers import WebhookDeliverySerializer, WebhookEndpointSerializer


class AccountViewSet(ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer


class IncomeStreamViewSet(ModelViewSet):
    queryset = IncomeStream.objects.select_related("account")
    serializer_class = IncomeStreamSerializer


class TransferViewSet(ModelViewSet):
    queryset = Transfer.objects.select_related("from_account", "to_account")
    serializer_class = TransferSerializer


class OutgoingCategoryViewSet(ModelViewSet):
    queryset = OutgoingCategory.objects.all()
    serializer_class = OutgoingCategorySerializer


class OutgoingViewSet(ModelViewSet):
    queryset = Outgoing.objects.select_related("category", "account")
    serializer_class = OutgoingSerializer


class OneOffOutgoingViewSet(ModelViewSet):
    queryset = OneOffOutgoing.objects.select_related("account", "linked_pot")
    serializer_class = OneOffOutgoingSerializer


class PotViewSet(ModelViewSet):
    queryset = Pot.objects.select_related("linked_project", "linked_one_off")
    serializer_class = PotSerializer


class PotEntryViewSet(ModelViewSet):
    queryset = PotEntry.objects.select_related("pot")
    serializer_class = PotEntrySerializer


class ProjectViewSet(ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer


class TaskViewSet(ModelViewSet):
    queryset = Task.objects.select_related("linked_project")
    serializer_class = TaskSerializer


class NoteViewSet(ModelViewSet):
    queryset = Note.objects.select_related("linked_project")
    serializer_class = NoteSerializer


class WebhookEndpointViewSet(ModelViewSet):
    queryset = WebhookEndpoint.objects.all()
    serializer_class = WebhookEndpointSerializer


class WebhookDeliveryViewSet(ModelViewSet):
    http_method_names: ClassVar[list[str]] = ["get", "head", "options"]  # read-only — a log, not editable
    queryset = WebhookDelivery.objects.select_related("endpoint")
    serializer_class = WebhookDeliverySerializer
