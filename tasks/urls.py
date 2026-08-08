from django.urls import path

from tasks import views

app_name = "tasks"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="list"),
    # Task CRUD
    path("task/add/", views.TaskCreateView.as_view(), name="task_add"),
    path("task/<int:pk>/", views.TaskDetailView.as_view(), name="detail"),
    path("task/<int:pk>/edit/", views.TaskUpdateView.as_view(), name="task_edit"),
    path("task/<int:pk>/delete/", views.TaskDeleteView.as_view(), name="task_delete"),
    path("task/<int:pk>/toggle-done/", views.toggle_done, name="task_toggle_done"),
]
