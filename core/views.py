import csv
import io
import os
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

    # FIX: recent alerts for dashboard panel
    recent_alerts = (
        RestockAlert.objects.filter(status='pending')
        .select_related('product')
        .order_by('-alert_date')[:5]
    )

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
        'recent_alerts': recent_alerts,
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
# FORECAST  — FIXED
# ─────────────────────────────────────────────
def forecast(request):
    products = Product.objects.all()
    selected = request.GET.get('product')
    sel_product = None
    forecasts = []
    chart_labels = []
    chart_actual = []
    chart_forecast = []

    if selected:
        sel_product = get_object_or_404(Product, pk=selected)

        # Last 14 days actual sales
        since = date.today() - timedelta(days=14)
        actual_qs = (
            SalesRecord.objects
            .filter(product=sel_product, date__gte=since)
            .order_by('date')
        )
        actual_dict = {str(r.date): r.quantity_sold for r in actual_qs}

        # Build 14-day actual labels + values
        for i in range(14):
            d = str(since + timedelta(days=i))
            chart_labels.append(d)
            chart_actual.append(actual_dict.get(d, 0))

        # Next 7 days forecast from DB
        forecasts = list(
            ForecastResult.objects
            .filter(product=sel_product, forecast_date__gte=date.today())
            .order_by('forecast_date')[:7]
        )

        # FIX: append forecast dates to labels BEFORE return
        for f in forecasts:
            chart_labels.append(str(f.forecast_date))
            chart_actual.append(None)
            chart_forecast.append(round(f.predicted_sales, 1))

    return render(request, 'forecast.html', {
        'products': products,
        'selected_id': int(selected) if selected else None,
        'sel_product': sel_product,
        'forecasts': forecasts,
        'chart_labels': chart_labels,
        'chart_actual': chart_actual,
        'chart_forecast': chart_forecast,
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
# RUN ML ENGINE — FIXED working directory
# ─────────────────────────────────────────────
def run_ml_view(request):
    WRITE_ALLOWED = ['ForecastResult', 'RestockAlert']
    if request.method == 'POST':
        try:
            # FIX: get the project root directory so ml/run_ml.py is found correctly
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ml_script = os.path.join(project_root, 'ml', 'run_ml.py')

            result = subprocess.run(
                [sys.executable, ml_script],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=project_root,   # FIX: set working directory explicitly
            )

            if result.returncode == 0:
                alert_count = RestockAlert.objects.filter(status='pending').count()
                messages.success(
                    request,
                    f"✅ AI Engine ran successfully! {alert_count} restock alerts generated."
                )
            else:
                # Show the actual error so you can debug
                messages.error(request, f"AI Engine error: {result.stderr[:300]}")

        except subprocess.TimeoutExpired:
            messages.error(request, "AI Engine timed out. Try again.")
        except Exception as e:
            messages.error(request, f"Could not run AI Engine: {str(e)}")

    return redirect('alerts')


# ─────────────────────────────────────────────
# CSV UPLOAD — cleaned up (no duplicate message)
# ─────────────────────────────────────────────
def upload_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):

        file = request.FILES['csv_file']
        decoded = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))

        product_count = 0
        sales_count = 0

        for row in reader:
            row = {k.strip().lower(): v for k, v in row.items() if k}

            # ─── PRODUCT IMPORT ───
            if 'name' in row and 'price' in row and ('stock' in row or 'quantity' in row) and 'sku' in row:
                Product.objects.update_or_create(
                    sku=row['sku'].strip(),
                    defaults={
                        'name': row['name'].strip(),
                        'unit_price': float(row['price']),
                        'current_stock': int(row.get('stock', row.get('quantity', 0))),
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
            f"✅ Upload complete: {product_count} products, {sales_count} sales records imported."
        )
        return redirect('inventory')

    return render(request, 'upload_csv.html')