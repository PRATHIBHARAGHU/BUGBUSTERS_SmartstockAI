from django.contrib import admin
from .models import Store, Category, Product, SalesRecord, RestockAlert, ForecastResult

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'store', 'current_stock', 'reorder_point', 'stock_status']
    list_filter  = ['category', 'store']
    search_fields = ['name', 'sku']

@admin.register(SalesRecord)
class SalesRecordAdmin(admin.ModelAdmin):
    list_display = ['product', 'date', 'quantity_sold', 'revenue']
    list_filter  = ['date']

@admin.register(RestockAlert)
class RestockAlertAdmin(admin.ModelAdmin):
    list_display = ['product', 'alert_date', 'current_stock', 'recommended_qty', 'status']
    list_filter  = ['status']

@admin.register(ForecastResult)
class ForecastResultAdmin(admin.ModelAdmin):
    list_display = ['product', 'forecast_date', 'predicted_sales']
