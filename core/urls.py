from django.urls import path
from . import views

urlpatterns = [
    path('',                  views.dashboard,       name='dashboard'),
    path('inventory/',        views.inventory,       name='inventory'),
    path('alerts/',           views.alerts,          name='alerts'),
    path('forecast/',         views.forecast,        name='forecast'),
    path('product/<int:pk>/', views.product_detail,  name='product_detail'),
    path('alerts/resolve/<int:pk>/', views.resolve_alert, name='resolve_alert'),
    path('run-ml/',           views.run_ml_view,     name='run_ml'),
    path('upload-csv/',       views.upload_csv,      name='upload_csv'),
]
