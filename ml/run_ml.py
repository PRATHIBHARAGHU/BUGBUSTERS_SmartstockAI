"""
Run from the project root:
    python ml/run_ml.py

This script:
1. Trains a demand forecasting model per product (Linear Regression on time series)
2. Predicts next 7 days of sales
3. Generates restock alerts with explainable AI text
4. Saves all results to the database
"""

import os
import sys
import django
import numpy as np
from datetime import date, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartstock.settings')
django.setup()

from core.models import Product, SalesRecord, RestockAlert, ForecastResult
from sklearn.linear_model import LinearRegression

print("Running SmartStock AI forecasting engine...\n")

# Clear old forecasts and alerts
ForecastResult.objects.all().delete()
RestockAlert.objects.all().delete()

today = date.today()
products = Product.objects.all()

for product in products:
    sales_qs = SalesRecord.objects.filter(product=product).order_by('date')
    if sales_qs.count() < 14:
        continue  # need at least 2 weeks of data

    # ── Build feature matrix ──────────────────────────────
    dates = [s.date for s in sales_qs]
    quantities = [s.quantity_sold for s in sales_qs]
    base_date = dates[0]

    X = np.array([(d - base_date).days for d in dates]).reshape(-1, 1)
    y = np.array(quantities)

    # ── Train model ───────────────────────────────────────
    model = LinearRegression()
    model.fit(X, y)

    # ── Predict next 7 days ───────────────────────────────
    forecast_dates = [today + timedelta(days=i+1) for i in range(7)]
    X_future = np.array([(d - base_date).days for d in forecast_dates]).reshape(-1, 1)
    predictions = model.predict(X_future)
    predictions = np.clip(predictions, 0, None)  # no negative sales

    # Save forecasts
    for fd, pred in zip(forecast_dates, predictions):
        ForecastResult.objects.create(
            product=product,
            forecast_date=fd,
            predicted_sales=round(float(pred), 2),
        )

    # ── Compute alert metrics ─────────────────────────────
    avg_daily_sales = float(np.mean(y[-30:]))  # last 30 days avg
    total_predicted_7d = float(sum(predictions))

    # Recent trend (last 7 days vs previous 7 days)
    recent_avg = float(np.mean(y[-7:])) if len(y) >= 7 else avg_daily_sales
    prev_avg   = float(np.mean(y[-14:-7])) if len(y) >= 14 else avg_daily_sales
    trend_pct  = ((recent_avg - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0

    # Days until stockout
    days_until_stockout = None
    if avg_daily_sales > 0:
        days_until_stockout = int(product.current_stock / avg_daily_sales)

    # ── Recommended restock qty ───────────────────────────
    # Cover next 30 days of predicted demand + safety buffer
    recommended_qty = max(0, int(total_predicted_7d * (30/7) - product.current_stock) + 20)

    # ── Decide if alert needed ────────────────────────────
    needs_alert = (
        product.current_stock <= product.reorder_point or
        (days_until_stockout is not None and days_until_stockout <= 7)
    )

    if needs_alert and recommended_qty > 0:
        # ── Explainable AI reason ─────────────────────────
        reason_parts = []

        if product.current_stock <= 0:
            reason_parts.append(f"⚠️ Product is OUT OF STOCK (0 units remaining).")
        else:
            reason_parts.append(
                f"Current stock is {product.current_stock} units, "
                f"which is {'below' if product.current_stock < product.reorder_point else 'at'} "
                f"the reorder point of {product.reorder_point} units."
            )

        reason_parts.append(
            f"Average daily sales over the last 30 days: {avg_daily_sales:.1f} units/day."
        )

        if days_until_stockout is not None:
            reason_parts.append(
                f"At this rate, stock will run out in approximately {days_until_stockout} day(s)."
            )

        reason_parts.append(
            f"AI forecast predicts {total_predicted_7d:.0f} units sold in the next 7 days."
        )

        if abs(trend_pct) >= 10:
            direction = "increased" if trend_pct > 0 else "decreased"
            reason_parts.append(
                f"Demand has {direction} by {abs(trend_pct):.0f}% compared to the previous week."
            )

        reason_parts.append(
            f"Recommended restock: {recommended_qty} units to cover 30 days of predicted demand."
        )

        reason = " ".join(reason_parts)

        RestockAlert.objects.create(
            product=product,
            current_stock=product.current_stock,
            recommended_qty=recommended_qty,
            reason=reason,
            predicted_days_until_stockout=days_until_stockout,
        )

alert_count = RestockAlert.objects.count()
forecast_count = ForecastResult.objects.count()

print(f"✓ Forecasts generated: {forecast_count}")
print(f"✓ Restock alerts created: {alert_count}")
print("\nML engine done. Start the server:  python manage.py runserver")
