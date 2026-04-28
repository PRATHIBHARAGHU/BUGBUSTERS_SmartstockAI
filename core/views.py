import csv
import io
import subprocess
import sys
from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Sum, Count, Avg, F
from django.http import JsonResponse
from django.contrib import messages
from .models import Product, SalesRecord, RestockAlert, ForecastResult, Store, Category


# ── Dashboard ─────────────────────────────────────────────
def dashboard(request):
    products = Product.objects.select_related('category', 'store')
    total_products = products.count()
    low_stock      = products.filter(current_stock__lte=F('reorder_point')).count()
    out_of_stock   = products.filter(current_stock=0).count()
    pending_alerts = RestockAlert.objects.filter(status='pending').count()

    # Total revenue last 30 days
    since = date.today() - timedelta(days=30)
    revenue_30d = SalesRecord.objects.filter(date__gte=since).aggregate(
        total=Sum('revenue'))['total'] or 0

    # Revenue by category (for pie chart)
    cat_revenue = (
        SalesRecord.objects.filter(date__gte=since)
        .values('product__category__name')
        .annotate(total=Sum('revenue'))
        .order_by('-total')
    )
    cat_labels  = [r['product__category__name'] for r in cat_revenue]
    cat_values  = [float(r['total']) for r in cat_revenue]

    # Daily sales last 14 days (for line chart)
    since_14 = date.today() - timedelta(days=14)
    daily_sales = (
        SalesRecord.objects.filter(date__gte=since_14)
        .values('date')
        .annotate(total=Sum('quantity_sold'))
        .order_by('date')
    )
    day_labels = [str(r['date']) for r in daily_sales]
    day_values = [r['total'] for r in daily_sales]

    # Recent alerts
    recent_alerts = RestockAlert.objects.filter(
        status='pending').select_related('product')[:5]

    # Top 5 selling products last 30 days
    top_products = (
        SalesRecord.objects.filter(date__gte=since)
        .values('product__name')
        .annotate(total_qty=Sum('quantity_sold'))
        .order_by('-total_qty')[:5]
    )
    top_labels = [p['product__name'] for p in top_products]
    top_values = [p['total_qty'] for p in top_products]

    context = {
        'total_products': total_products,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'pending_alerts': pending_alerts,
        'revenue_30d': revenue_30d,
        'cat_labels': cat_labels,
        'cat_values': cat_values,
        'day_labels': day_labels,
        'day_values': day_values,
        'recent_alerts': recent_alerts,
        'top_labels': top_labels,
        'top_values': top_values,
    }
    return render(request, 'dashboard.html', context)


# ── Inventory List ────────────────────────────────────────
def inventory(request):
    products = Product.objects.select_related('category', 'store').all()

    # Filters
    search   = request.GET.get('search', '')
    category = request.GET.get('category', '')
    store    = request.GET.get('store', '')
    status   = request.GET.get('status', '')

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

    categories = Category.objects.all()
    stores     = Store.objects.all()

    context = {
        'products': products,
        'categories': categories,
        'stores': stores,
        'search': search,
        'selected_cat': category,
        'selected_store': store,
        'selected_status': status,
    }
    return render(request, 'inventory.html', context)


# ── Alerts ────────────────────────────────────────────────
def alerts(request):
    pending  = RestockAlert.objects.filter(status='pending').select_related('product__store', 'product__category')
    ordered  = RestockAlert.objects.filter(status='ordered').select_related('product__store', 'product__category')
    resolved = RestockAlert.objects.filter(status='resolved').select_related('product__store', 'product__category')[:10]

    context = {
        'pending': pending,
        'ordered': ordered,
        'resolved': resolved,
        'pending_count': pending.count(),
    }
    return render(request, 'alerts.html', context)


def resolve_alert(request, pk):
    alert = get_object_or_404(RestockAlert, pk=pk)
    action = request.POST.get('action', 'resolved')
    alert.status = action
    alert.save()
    messages.success(request, f"Alert marked as {action}.")
    return redirect('alerts')


# ── Forecast ──────────────────────────────────────────────
def forecast(request):
    products  = Product.objects.select_related('category', 'store').all()
    selected  = request.GET.get('product', None)
    sel_product = None
    chart_labels = []
    chart_actual = []
    chart_forecast = []

    if selected:
        sel_product = get_object_or_404(Product, pk=selected)

        # Actual last 14 days
        since = date.today() - timedelta(days=14)
        actual = SalesRecord.objects.filter(
            product=sel_product, date__gte=since).order_by('date')
        for s in actual:
            chart_labels.append(str(s.date))
            chart_actual.append(s.quantity_sold)

        # Forecasts next 7 days
        forecasts = ForecastResult.objects.filter(
            product=sel_product,
            forecast_date__gte=date.today()
        ).order_by('forecast_date')
        for f in forecasts:
            chart_labels.append(str(f.forecast_date))
            chart_actual.append(None)
            chart_forecast.append(round(f.predicted_sales, 1))

    context = {
        'products': products,
        'selected_id': int(selected) if selected else None,
        'sel_product': sel_product,
        'chart_labels': chart_labels,
        'chart_actual': chart_actual,
        'chart_forecast': chart_forecast,
    }
    return render(request, 'forecast.html', context)


# ── Product Detail ────────────────────────────────────────
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    sales   = SalesRecord.objects.filter(product=product).order_by('-date')[:30]
    alerts  = RestockAlert.objects.filter(product=product).order_by('-alert_date')[:5]
    forecasts = ForecastResult.objects.filter(
        product=product, forecast_date__gte=date.today()).order_by('forecast_date')

    since = date.today() - timedelta(days=30)
    total_sold_30d = SalesRecord.objects.filter(
        product=product, date__gte=since).aggregate(t=Sum('quantity_sold'))['t'] or 0

    chart_labels   = [str(s.date) for s in reversed(list(sales))]
    chart_values   = [s.quantity_sold for s in reversed(list(sales))]

    context = {
        'product': product,
        'sales': sales,
        'alerts': alerts,
        'forecasts': forecasts,
        'total_sold_30d': total_sold_30d,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
    }
    return render(request, 'product_detail.html', context)


# ── Run ML from UI ────────────────────────────────────────
def run_ml_view(request):
    if request.method == 'POST':
        try:
            result = subprocess.run(
                [sys.executable, 'ml/run_ml.py'],
                capture_output=True, text=True, timeout=120
            )
            output = result.stdout + result.stderr
            messages.success(request, f"ML engine ran successfully! {output}")
        except Exception as e:
            messages.error(request, f"ML engine error: {str(e)}")
    return redirect('alerts')


# ── Upload CSV ────────────────────────────────────────────
def upload_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        try:
            decoded = csv_file.read().decode('utf-8')
            reader  = csv.DictReader(io.StringIO(decoded))
            count   = 0
            for row in reader:
                # Expected columns: sku, date (YYYY-MM-DD), quantity_sold
                try:
                    product = Product.objects.get(sku=row['sku'].strip())
                    SalesRecord.objects.update_or_create(
                        product=product,
                        date=row['date'].strip(),
                        defaults={
                            'quantity_sold': int(row['quantity_sold']),
                            'revenue': int(row['quantity_sold']) * float(product.unit_price),
                        }
                    )
                    count += 1
                except Product.DoesNotExist:
                    pass
            messages.success(request, f"Imported {count} sales records. Run ML to refresh forecasts.")
        except Exception as e:
            messages.error(request, f"CSV error: {str(e)}")
        return redirect('inventory')
    return render(request, 'upload_csv.html')
