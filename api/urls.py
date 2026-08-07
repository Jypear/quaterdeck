"""DRF API router — registers all resource viewsets."""

from rest_framework.routers import DefaultRouter

from api.views import (
    AccountViewSet,
    IncomeStreamViewSet,
    NoteViewSet,
    OneOffOutgoingViewSet,
    OutgoingCategoryViewSet,
    OutgoingViewSet,
    PotEntryViewSet,
    PotViewSet,
    ProjectViewSet,
    TaskViewSet,
    TransferViewSet,
    WebhookDeliveryViewSet,
    WebhookEndpointViewSet,
)

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("income-streams", IncomeStreamViewSet, basename="income-stream")
router.register("transfers", TransferViewSet, basename="transfer")
router.register("outgoing-categories", OutgoingCategoryViewSet, basename="outgoing-category")
router.register("outgoings", OutgoingViewSet, basename="outgoing")
router.register("one-off-outgoings", OneOffOutgoingViewSet, basename="one-off-outgoing")
router.register("pots", PotViewSet, basename="pot")
router.register("pot-entries", PotEntryViewSet, basename="pot-entry")
router.register("projects", ProjectViewSet, basename="project")
router.register("tasks", TaskViewSet, basename="task")
router.register("notes", NoteViewSet, basename="note")
router.register("webhook-endpoints", WebhookEndpointViewSet, basename="webhook-endpoint")
router.register("webhook-deliveries", WebhookDeliveryViewSet, basename="webhook-delivery")

urlpatterns = router.urls
