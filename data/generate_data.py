"""
Run from the project root:
    python data/generate_data.py

This creates realistic stores, products, 6 months of sales history,
and triggers the ML model to generate alerts + forecasts.
"""

import os
import sys
import django
import random
from datetime import date, timedelta

# ── Setup Django ──────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartstock.settings')
django.setup()

from core.models import Store, Category, Product, SalesRecord, RestockAlert, ForecastResult

# ── Clear existing data ───────────────────────────────────
print("Clearing old data...")
ForecastResult.objects.all().delete()
RestockAlert.objects.all().delete()
SalesRecord.objects.all().delete()
Product.objects.all().delete()
Category.objects.all().delete()
Store.objects.all().delete()

# ── Stores ────────────────────────────────────────────────
print("Creating stores...")
stores = [
    Store.objects.create(name="SmartStock - Koramangala", location="Koramangala, Bangalore"),
    Store.objects.create(name="SmartStock - Indiranagar", location="Indiranagar, Bangalore"),
]

# ── Categories ────────────────────────────────────────────
print("Creating categories...")
categories = {
    "Electronics":    Category.objects.create(name="Electronics"),
    "Groceries":      Category.objects.create(name="Groceries"),
    "Clothing":       Category.objects.create(name="Clothing"),
    "Stationery":     Category.objects.create(name="Stationery"),
    "Home & Kitchen": Category.objects.create(name="Home & Kitchen"),
}

# ── Products ──────────────────────────────────────────────
print("Creating products...")
products_data = [
    # (name, sku, category, store, stock, reorder, max, price)
    ("USB-C Charging Cable",  "EL001", "Electronics",    0, 12,  20, 150, 299.00),
    ("Wireless Earbuds",      "EL002", "Electronics",    0, 45,  20, 100, 1499.00),
    ("Phone Stand",           "EL003", "Electronics",    0, 85,  25, 120, 399.00),
    ("LED Desk Lamp",         "EL004", "Electronics",    0, 5,   20, 80,  799.00),
    ("Basmati Rice 5kg",      "GR001", "Groceries",      0, 110, 30, 300, 459.00),
    ("Sunflower Oil 1L",      "GR002", "Groceries",      0, 8,   25, 200, 189.00),
    ("Instant Noodles (12pk)","GR003", "Groceries",      0, 65,  40, 250, 149.00),
    ("Green Tea 100bags",     "GR004", "Groceries",      0, 18,  20, 150, 299.00),
    ("Cotton T-Shirt (M)",    "CL001", "Clothing",       0, 30,  15, 100, 399.00),
    ("Denim Jeans (32)",      "CL002", "Clothing",       0, 7,   10, 80,  1299.00),
    ("Formal Shirt (L)",      "CL003", "Clothing",       0, 22,  12, 60,  899.00),
    ("A4 Notebook 200pg",     "ST001", "Stationery",     0, 75,  30, 200, 129.00),
    ("Ball Pen (10-pack)",    "ST002", "Stationery",     0, 180, 50, 300, 89.00),
    ("Sticky Notes Set",      "ST003", "Stationery",     0, 40,  20, 150, 149.00),
    ("Non-stick Pan 24cm",    "HK001", "Home & Kitchen", 0, 15,  10, 60,  899.00),
    ("Water Bottle 1L",       "HK002", "Home & Kitchen", 0, 55,  20, 100, 349.00),
]

products = []
for (name, sku, cat_name, store_idx, stock, reorder, max_s, price) in products_data:
    # vary stock across stores
    s1_stock = stock + random.randint(-5, 30)
    s2_stock = stock + random.randint(-5, 30)

    for i, store in enumerate(stores):
        s = s1_stock if i == 0 else s2_stock
        p = Product.objects.create(
            name=name,
            sku=f"{sku}-S{i+1}",
            category=categories[cat_name],
            store=store,
            current_stock=max(0, s),
            reorder_point=reorder,
            max_stock=max_s,
            unit_price=price,
        )
        products.append(p)

# ── Sales history (180 days) ──────────────────────────────
print("Generating 180 days of sales history...")
today = date.today()
start_date = today - timedelta(days=180)

# Base daily sales rates per product type
base_sales = {
    "EL": (2, 8),    "GR": (5, 20),
    "CL": (1, 6),    "ST": (3, 15),
    "HK": (1, 5),
}

for product in products:
    prefix = product.sku[:2]
    low, high = base_sales.get(prefix, (2, 8))
    current = start_date
    while current <= today:
        # Weekend boost
        weekend_mult = 1.4 if current.weekday() >= 5 else 1.0
        # Month-end boost
        month_end_mult = 1.2 if current.day >= 25 else 1.0
        qty = max(0, int(random.randint(low, high) * weekend_mult * month_end_mult))
        if qty > 0:
            SalesRecord.objects.create(
                product=product,
                date=current,
                quantity_sold=qty,
                revenue=qty * float(product.unit_price),
            )
        current += timedelta(days=1)

print(f"Created {SalesRecord.objects.count()} sales records")

# ── Update current stock based on sales ──────────────────
print("Updating stock levels...")
for product in products:
    prefix = product.sku[:2]
    low, high = base_sales.get(prefix, (2, 8))
    # Simulate: started with max stock, sold down over 180 days
    total_sold = SalesRecord.objects.filter(product=product).aggregate(
        total=__import__('django.db.models', fromlist=['Sum']).Sum('quantity_sold')
    )['total'] or 0
    simulated_stock = max(0, product.max_stock - (total_sold % product.max_stock))
    product.current_stock = simulated_stock
    product.save()

print("Data generation complete!")
print(f"  Stores: {Store.objects.count()}")
print(f"  Products: {Product.objects.count()}")
print(f"  Sales records: {SalesRecord.objects.count()}")
print("\nNow run:  python ml/run_ml.py")
