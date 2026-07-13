from django.urls import path

from webhooks import views

app_name = "webhooks"

urlpatterns = [
    path("", views.WebhookEndpointListView.as_view(), name="list"),
    # Endpoint CRUD
    path("add/", views.WebhookEndpointCreateView.as_view(), name="endpoint_add"),
    path("<int:pk>/edit/", views.WebhookEndpointUpdateView.as_view(), name="endpoint_edit"),
    path("<int:pk>/delete/", views.WebhookEndpointDeleteView.as_view(), name="endpoint_delete"),
    # Delivery log
    path("deliveries/", views.WebhookDeliveryListView.as_view(), name="deliveries"),
    # External-facing inbound receiver
    path("inbound/", views.inbound, name="inbound"),
]
