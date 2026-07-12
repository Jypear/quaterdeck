from django.urls import path

from budget import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetOverviewView.as_view(), name="overview"),
    path("accounts/", views.AccountListView.as_view(), name="accounts"),
    path("pots/", views.PotListView.as_view(), name="pots"),
    # Account CRUD
    path("account/add/", views.AccountCreateView.as_view(), name="account_add"),
    path("account/<int:pk>/edit/", views.AccountUpdateView.as_view(), name="account_edit"),
    path("account/<int:pk>/delete/", views.AccountDeleteView.as_view(), name="account_delete"),
    # Income CRUD
    path("income/add/", views.IncomeStreamCreateView.as_view(), name="income_add"),
    path("income/<int:pk>/edit/", views.IncomeStreamUpdateView.as_view(), name="income_edit"),
    path("income/<int:pk>/delete/", views.IncomeStreamDeleteView.as_view(), name="income_delete"),
    # Outgoing CRUD
    path("outgoing/add/", views.OutgoingCreateView.as_view(), name="outgoing_add"),
    path("outgoing/<int:pk>/edit/", views.OutgoingUpdateView.as_view(), name="outgoing_edit"),
    path("outgoing/<int:pk>/delete/", views.OutgoingDeleteView.as_view(), name="outgoing_delete"),
    # Per-period logging
    path("outgoing/<int:outgoing_id>/log-variance/", views.log_variance, name="log_variance"),
    path("pot/<int:pot_id>/log-entry/", views.log_pot_entry, name="log_pot_entry"),
]
