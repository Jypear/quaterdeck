"""DRF ModelViewSets for all Quaterdeck resources."""

from rest_framework.viewsets import ModelViewSet

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
from budget.serializers import (
    AccountSerializer,
    IncomeStreamSerializer,
    OneOffOutgoingSerializer,
    OutgoingCategorySerializer,
    OutgoingSerializer,
    OutgoingVarianceSerializer,
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


class OutgoingVarianceViewSet(ModelViewSet):
    queryset = OutgoingVariance.objects.select_related("outgoing")
    serializer_class = OutgoingVarianceSerializer


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
