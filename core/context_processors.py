from core.models import RestockAlert

def alert_count(request):
    try:
        count = RestockAlert.objects.filter(status='pending').count()
    except Exception:
        count = 0
    return {'pending_alert_count': count}
