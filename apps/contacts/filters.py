import django_filters

from apps.contacts.models import Contact


class ContactFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="email_status", lookup_expr="exact")
    college = django_filters.CharFilter(field_name="college", lookup_expr="icontains")
    source_file = django_filters.UUIDFilter(field_name="source_file_id")
    tenant_id = django_filters.UUIDFilter(field_name="tenant_id")

    class Meta:
        model = Contact
        fields = ["status", "college", "source_file", "tenant_id"]
