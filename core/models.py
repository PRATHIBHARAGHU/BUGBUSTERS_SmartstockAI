from django.db import models


class Store(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Product(models.Model):
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    current_stock = models.IntegerField(default=0)
    reorder_point = models.IntegerField(default=20)   # alert fires below this
    max_stock = models.IntegerField(default=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def stock_status(self):
        if self.current_stock <= 0:
            return "out_of_stock"
        elif self.current_stock <= self.reorder_point:
            return "low"
        elif self.current_stock >= self.max_stock * 0.9:
            return "overstock"
        return "ok"

    @property
    def stock_percentage(self):
        return min(int((self.current_stock / self.max_stock) * 100), 100)


class SalesRecord(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sales')
    date = models.DateField()
    quantity_sold = models.IntegerField()
    revenue = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} - {self.date} - {self.quantity_sold} units"

    class Meta:
        ordering = ['-date']


class RestockAlert(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('resolved', 'Resolved'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='alerts')
    alert_date = models.DateTimeField(auto_now_add=True)
    current_stock = models.IntegerField()
    recommended_qty = models.IntegerField()
    reason = models.TextField()          # explainable AI text
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    predicted_days_until_stockout = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Alert: {self.product.name} @ {self.alert_date.date()}"

    class Meta:
        ordering = ['-alert_date']


class ForecastResult(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='forecasts')
    forecast_date = models.DateField()
    predicted_sales = models.FloatField()
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Forecast: {self.product.name} on {self.forecast_date}"

    class Meta:
        ordering = ['forecast_date']
