from django.urls import path

from agents import views

app_name = "agents"

urlpatterns = [
    path("agents/requirement/run/", views.requirement_run_view, name="requirement_run"),
]