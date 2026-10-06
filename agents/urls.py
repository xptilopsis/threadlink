from django.urls import path

from agents import views

app_name = "agents"

urlpatterns = [
    path("agents/requirement/run/", views.requirement_run_view, name="requirement_run"),
    path("agents/bom-selection/run/", views.bom_selection_run_view, name="bom_selection_run"),
    path("agents/traceability/run/", views.traceability_run_view, name="traceability_run"),
]