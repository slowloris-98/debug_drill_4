"""Event fan-out.

A published score report queues one delivery for every active endpoint
subscribed to `result.published`.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from core.models import ScoreReport, WebhookDelivery, WebhookEndpoint


@receiver(post_save, sender=ScoreReport)
def queue_result_published(sender, instance, created, **kwargs):
    if instance.status != ScoreReport.PUBLISHED:
        return

    endpoints = WebhookEndpoint.objects.filter(
        organization_id=instance.organization_id, active=True
    )
    for endpoint in endpoints:
        if WebhookEndpoint.RESULT_PUBLISHED not in endpoint.events:
            continue
        WebhookDelivery.objects.get_or_create(
            endpoint=endpoint,
            report=instance,
            event_type=WebhookEndpoint.RESULT_PUBLISHED,
            defaults={"created_at": timezone.now()},
        )
