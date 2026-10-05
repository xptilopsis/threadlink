from django.urls import path

from traceability import views

app_name = "traceability"

urlpatterns = [
    path("trace/serial/<str:sn>/", views.serial_trace, name="serial_trace"),
]