from django.urls import path

from tasks.views import TaskListView

app_name = "tasks"

urlpatterns = [
    path("", TaskListView.as_view(), name="list"),
]
