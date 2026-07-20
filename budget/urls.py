from django.urls import path

from budget import views

app_name = "budget"

urlpatterns = [
    path("", views.BudgetOverviewView.as_view(), name="overview"),
    path("accounts/", views.AccountListView.as_view(), name="accounts"),
    path("pots/", views.PotListView.as_view(), name="pots"),
    path("timeline/", views.TimelineView.as_view(), name="timeline"),
    path("flow/", views.FlowView.as_view(), name="flow"),
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
    # Transfer CRUD
    path("transfer/add/", views.TransferCreateView.as_view(), name="transfer_add"),
    path("transfer/<int:pk>/edit/", views.TransferUpdateView.as_view(), name="transfer_edit"),
    path("transfer/<int:pk>/delete/", views.TransferDeleteView.as_view(), name="transfer_delete"),
    # One-off outgoing CRUD
    path("oneoff/add/", views.OneOffOutgoingCreateView.as_view(), name="oneoff_add"),
    path("oneoff/<int:pk>/edit/", views.OneOffOutgoingUpdateView.as_view(), name="oneoff_edit"),
    path("oneoff/<int:pk>/delete/", views.OneOffOutgoingDeleteView.as_view(), name="oneoff_delete"),
    # Outgoing category CRUD
    path("category/add/", views.OutgoingCategoryCreateView.as_view(), name="category_add"),
    path("category/<int:pk>/edit/", views.OutgoingCategoryUpdateView.as_view(), name="category_edit"),
    path("category/<int:pk>/delete/", views.OutgoingCategoryDeleteView.as_view(), name="category_delete"),
    # Pot CRUD
    path("pot/add/", views.PotCreateView.as_view(), name="pot_add"),
    path("pot/<int:pk>/edit/", views.PotUpdateView.as_view(), name="pot_edit"),
    path("pot/<int:pk>/delete/", views.PotDeleteView.as_view(), name="pot_delete"),
    # Per-period logging
    path("outgoing/<int:outgoing_id>/log-variance/", views.log_variance, name="log_variance"),
    path("pot/<int:pot_id>/log-entry/", views.log_pot_entry, name="log_pot_entry"),
    path("pot/<int:pot_id>/accept-contribution/", views.accept_pot_contribution, name="accept_pot_contribution"),
]
