"""Budget views — stubs to be fleshed out."""

from django.views.generic import TemplateView


class BudgetOverviewView(TemplateView):
    template_name = "budget/overview.html"


class AccountListView(TemplateView):
    template_name = "budget/accounts.html"


class PotListView(TemplateView):
    template_name = "budget/pots.html"
