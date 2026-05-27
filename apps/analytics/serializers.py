from rest_framework import serializers

from apps.analytics.models import Analytics


class AnalyticsSerializer(serializers.ModelSerializer):
    """Full serializer for the Analytics model."""

    class Meta:
        model = Analytics
        fields = [
            'id',
            'campaign',
            'date',
            'total_sent',
            'total_failed',
            'total_pending',
            'success_rate',
            'delivery_rate',
            'college_distribution',
            'created_at',
        ]
        read_only_fields = fields


class DashboardKPISerializer(serializers.Serializer):
    """Serializer describing the key performance indicators returned by the dashboard."""

    total_contacts = serializers.IntegerField()
    total_campaigns = serializers.IntegerField()
    emails_sent = serializers.IntegerField()
    emails_failed = serializers.IntegerField()
    emails_pending = serializers.IntegerField()
    success_rate = serializers.DecimalField(max_digits=7, decimal_places=2)
    delivery_rate = serializers.DecimalField(max_digits=7, decimal_places=2)
    today_sent = serializers.IntegerField()


class DashboardResponseSerializer(serializers.Serializer):
    """
    Top-level response schema for the analytics dashboard endpoint.
    Used primarily for Swagger/ReDoc documentation.
    """

    kpi = DashboardKPISerializer()
    status_distribution = serializers.DictField()
    daily_trend = serializers.ListField()
    campaign_performance = serializers.ListField()
    college_distribution = serializers.DictField()
    best_template = serializers.DictField(allow_null=True)
