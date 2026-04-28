import csv
import io
import subprocess
import sys
from datetime import date, timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, F
from django.contrib import messages

from .models import Product, SalesRecord, RestockAlert, ForecastResult, Store, Category


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
def dashboard(request):
    products = Product.objects.select_related('category', 'store')

    total_products = products.count()
    low_stock = products.filter(current_stock__lte=F('reorder_point')).count()
    out_of_stock = products.filter(current_stock=0).count()
    pending_alerts = RestockAlert.objects.filter(status='pending').count()

    since = date.today() - timedelta(days=30)

    revenue_30d = SalesRecord.objects.filter(date__gte=since).aggregate(
        total=Sum('revenue')
    )['total'] or 0

    cat_revenue = (
        SalesRecord.objects.filter(date__gte=since)
        .values('product__category__name')
        .annotate(total=Sum('revenue'))
    )

    cat_labels = [r['product__category__name'] for r in cat_revenue]
    cat_values = [float(r['total']) for r in cat_revenue]

    daily_sales = (
        SalesRecord.objects.filter(date__gte=since)
        .values('date')
        .annotate(total=Sum('quantity_sold'))
        .order_by('date')
    )

    day_labels = [str(r['date']) for r in daily_sales]
    day_values = [r['total'] for r in daily_sales]

    top_products = (
        SalesRecord.objects.filter(date__gte=since)
        .values('product__name')
        .annotate(total_qty=Sum('quantity_sold'))
        .order_by('-total_qty')[:5]
    )

    top_labels = [p['product__name'] for p in top_products]
    top_values = [p['total_qty'] for p in top_products]

    return render(request, 'dashboard.html', {
        'total_products': total_products,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'pending_alerts': pending_alerts,
        'revenue_30d': revenue_30d,
        'cat_labels': cat_labels,
        'cat_values': cat_values,
        'day_labels': day_labels,
        'day_values': day_values,
        'top_labels': top_labels,
        'top_values': top_values,
    })


# ─────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────
def inventory(request):
    products = Product.objects.select_related('category', 'store').all()

    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    store = request.GET.get('store', '')
    status = request.GET.get('status', '')

    if search:
        products = products.filter(name__icontains=search)
    if category:
        products = products.filter(category__id=category)
    if store:
        products = products.filter(store__id=store)

    if status == 'low':
        products = products.filter(current_stock__lte=F('reorder_point'), current_stock__gt=0)
    elif status == 'out':
        products = products.filter(current_stock=0)
    elif status == 'ok':
        products = products.filter(current_stock__gt=F('reorder_point'))

    return render(request, 'inventory.html', {
        'products': products,
        'categories': Category.objects.all(),
        'stores': Store.objects.all(),
        'search': search,
        'selected_cat': category,
        'selected_store': store,
        'selected_status': status,
    })


# ─────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────
def alerts(request):
    pending = RestockAlert.objects.filter(status='pending').select_related('product')
    ordered = RestockAlert.objects.filter(status='ordered').select_related('product')
    resolved = RestockAlert.objects.filter(status='resolved').select_related('product')[:10]

    return render(request, 'alerts.html', {
        'pending': pending,
        'ordered': ordered,
        'resolved': resolved,
        'pending_count': pending.count(),
    })


def resolve_alert(request, pk):
    alert = get_object_or_404(RestockAlert, pk=pk)
    alert.status = request.POST.get('action', 'resolved')
    alert.save()
    messages.success(request, "Alert updated.")
    return redirect('alerts')


# ─────────────────────────────────────────────
# FORECAST
# ─────────────────────────────────────────────
def forecast(request):
    products = Product.objects.all()
    selected = request.GET.get('product')

    return render(request, 'forecast.html', {
        'products': products,
        'selected_id': int(selected) if selected else None,
    })


# ─────────────────────────────────────────────
# PRODUCT DETAIL
# ─────────────────────────────────────────────
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)

    sales = SalesRecord.objects.filter(product=product).order_by('-date')[:30]

    return render(request, 'product_detail.html', {
        'product': product,
        'sales': sales,
    })


# ─────────────────────────────────────────────
# RUN ML ENGINE
# ─────────────────────────────────────────────
def run_ml_view(request):
    if request.method == 'POST':
        try:
            result = subprocess.run(
                [sys.executable, 'ml/run_ml.py'],
                capture_output=True,
                text=True,
                timeout=120
            )
            messages.success(request, "ML Engine executed successfully.")
        except Exception as e:
            messages.error(request, str(e))

    return redirect('alerts')


# ─────────────────────────────────────────────
# FIXED CSV UPLOAD (IMPORTANT)
# Supports BOTH:
# 1. Product import
# 2. Sales import
# ─────────────────────────────────────────────
def upload_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):

        file = request.FILES['csv_file']
        decoded = file.read().decode('utf-8-sig')  # FIX: handles encoding issues
        reader = csv.DictReader(io.StringIO(decoded))

        product_count = 0
        sales_count = 0

        for row in reader:

            # Normalize keys (VERY IMPORTANT FIX)
            row = {k.strip().lower(): v for k, v in row.items() if k}

            # ─── PRODUCT IMPORT ───
            if 'name' in row and 'price' in row and ('stock' in row or 'quantity' in row) and 'sku' in row:

                Product.objects.update_or_create(
                    sku=row['sku'].strip(),
                    defaults={
                        'name': row['name'].strip(),
                        'unit_price': float(row['price']),
                        'current_stock': int(row['stock']),
                    }
                )
                product_count += 1

            # ─── SALES IMPORT ───
            elif 'sku' in row and 'date' in row and 'quantity_sold' in row:

                try:
                    product = Product.objects.get(sku=row['sku'].strip())

                    SalesRecord.objects.update_or_create(
                        product=product,
                        date=row['date'],
                        defaults={
                            'quantity_sold': int(row['quantity_sold']),
                            'revenue': int(row['quantity_sold']) * float(product.unit_price),
                        }
                    )
                    sales_count += 1

                except Product.DoesNotExist:
                    continue

        messages.success(
            request,
            f"Upload complete: {product_count} products, {sales_count} sales imported."
        )

        return redirect('inventory')

    return render(request, 'upload_csv.html')