from rest_framework import serializers

from apps.contacts.models import Contact, UploadedFile


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = "__all__"
        read_only_fields = ["id", "source_file", "tenant_id", "created_at", "updated_at"]


class ContactListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "college",
            "email_status",
            "extra_fields",
            "created_at",
        ]


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    tags = serializers.CharField(required=False, allow_blank=True)

    ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}

    def validate_file(self, value):
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f'Unsupported file type ".{extension}". Allowed: {", ".join(sorted(self.ALLOWED_EXTENSIONS))}.'
            )
        return value


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = "__all__"
        read_only_fields = [
            "id",
            "total_rows",
            "processed_rows",
            "valid_rows",
            "invalid_rows",
            "column_mapping",
            "upload_status",
            "created_at",
        ]
