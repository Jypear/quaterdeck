from django.urls import path

from budget.views import AccountListView, BudgetOverviewView, PotListView

app_name = "budget"

urlpatterns = [
    path("", BudgetOverviewView.as_view(), name="overview"),
    path("accounts/", AccountListView.as_view(), name="accounts"),
    path("pots/", PotListView.as_view(), name="pots"),
]
