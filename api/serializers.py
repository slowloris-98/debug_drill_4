from rest_framework import serializers

from core.models import Candidate, ScoreReport, WebhookEndpoint


class ScoreReportSerializer(serializers.ModelSerializer):
    candidate_ref = serializers.CharField(source="candidate.external_ref", read_only=True)
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    assessment_name = serializers.CharField(source="assessment.name", read_only=True)

    class Meta:
        model = ScoreReport
        fields = (
            "id",
            "partner_ref",
            "candidate_ref",
            "candidate_name",
            "assessment",
            "assessment_name",
            "raw_score",
            "status",
            "graded_at",
            "published_at",
            "updated_at",
        )
        read_only_fields = ("graded_at", "published_at", "updated_at")


class ScoreReportIngestSerializer(serializers.Serializer):
    """Payload a grading partner posts when it has finished marking."""

    partner_ref = serializers.CharField(max_length=64)
    candidate_ref = serializers.CharField(max_length=64)
    assessment = serializers.IntegerField()
    raw_score = serializers.CharField(max_length=8)

    def validate_candidate_ref(self, value):
        organization = self.context["organization"]
        if not Candidate.objects.filter(
            organization=organization, external_ref=value
        ).exists():
            raise serializers.ValidationError("No candidate with that reference.")
        return value


class WebhookEndpointSerializer(serializers.ModelSerializer):
    events = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEndpoint
        fields = ("id", "url", "events", "active", "created_at")
        read_only_fields = ("created_at",)

    def get_events(self, endpoint):
        return list(endpoint.events)
