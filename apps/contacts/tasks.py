import os
import re
import uuid
import csv
from pathlib import Path

import polars as pl
from celery import shared_task
from django.conf import settings
from django.db.models import F, Q

from apps.contacts.models import Contact, UploadedFile

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _detect_columns(columns: list[str]) -> dict[str, str]:
    normalized = {col: col.strip().lower() for col in columns}
    mapping: dict[str, str] = {}

    for col, key in normalized.items():
        if "email" in key:
            mapping[col] = "email"
        elif "name" in key:
            mapping[col] = "name"
        elif "phone" in key or "mobile" in key:
            mapping[col] = "phone"
        elif "college" in key or "organization" in key or "company" in key:
            mapping[col] = "college"
        else:
            mapping[col] = "extra"

    return mapping


@shared_task(
    bind=True,
    max_retries=0,
    queue="file_processing",
    name="apps.contacts.tasks.process_uploaded_file",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=360,
)
def process_uploaded_file(self, file_id: str, tags: str = ""):
    try:
        file_record = UploadedFile.objects.get(id=uuid.UUID(file_id))
    except UploadedFile.DoesNotExist:
        return

    # Load existing emails for O(1) duplicate checks using native Python sets
    existing_emails: set[str] = set(
        Contact.objects.filter(is_valid=True).values_list("email", flat=True)
    )

    try:
        # Load the data into Polars DataFrame for extreme performance
        if file_record.file_format == "csv":
            df = pl.read_csv(file_record.stored_path, infer_schema_length=0) # Read everything as string
        else:
            df = pl.read_excel(file_record.stored_path)

        # Ensure all column names are strings
        df.columns = [str(c) for c in df.columns]
        
        column_map = _detect_columns(list(df.columns))
        UploadedFile.objects.filter(id=file_record.id).update(column_mapping=column_map)

        email_col = next((k for k, v in column_map.items() if v == "email"), None)
        name_col = next((k for k, v in column_map.items() if v == "name"), None)
        phone_col = next((k for k, v in column_map.items() if v == "phone"), None)
        college_col = next((k for k, v in column_map.items() if v == "college"), None)
        extra_cols = [k for k, v in column_map.items() if v == "extra"]

        if not email_col:
            raise ValueError("No email column detected in the uploaded file.")

        # Polars Data-Cleaning
        df = df.with_columns(
            pl.col(email_col).str.strip_chars().str.to_lowercase().alias("_clean_email")
        )
        
        # Filter valid emails using regex
        valid_df = df.filter(pl.col("_clean_email").str.contains(EMAIL_PATTERN))
        invalid_count = df.height - valid_df.height
        
        # Extract rows as dictionaries for fast iteration
        rows = valid_df.to_dicts()

        total_rows = df.height
        total_duplicates = 0
        new_contacts = []

        for row in rows:
            email = row["_clean_email"]
            if not email or email in existing_emails:
                total_duplicates += 1
                continue
            
            existing_emails.add(email)

            extra_fields = {"tags": tags} if tags else {}
            for col in extra_cols:
                val = row.get(col)
                if val is not None and str(val).strip():
                    extra_fields[col] = str(val).strip()

            contact = Contact(
                source_file=file_record,
                name=str(row.get(name_col) or "").strip() if name_col else "",
                email=email,
                phone=str(row.get(phone_col) or "").strip() if phone_col else None,
                college=str(row.get(college_col) or "").strip() if college_col else None,
                extra_fields=extra_fields,
                email_status="pending",
                is_valid=True,
            )
            new_contacts.append(contact)

        # Batch insert using Django Bulk Create for db-speed
        if new_contacts:
            Contact.objects.bulk_create(new_contacts, batch_size=5000, ignore_conflicts=True)

        valid_count = len(new_contacts)

        UploadedFile.objects.filter(id=file_record.id).update(
            processed_rows=total_rows,
            total_rows=total_rows,
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            duplicate_rows=total_duplicates,
            upload_status="completed",
        )
    except Exception:
        UploadedFile.objects.filter(id=file_record.id).update(upload_status="failed")
        raise


@shared_task(
    bind=True,
    queue="bulk_ops",
    name="apps.contacts.tasks.bulk_delete_contacts",
    acks_late=True,
    reject_on_worker_lost=True,
)
def bulk_delete_contacts(self, payload: dict):
    queryset = Contact.objects.filter(is_valid=True)
    contact_ids = payload.get("contact_ids")
    filters = payload.get("filter")

    if contact_ids:
        queryset = queryset.filter(id__in=contact_ids)
    elif filters:
        if filters.get("status"):
            queryset = queryset.filter(email_status=filters["status"])
        if filters.get("college"):
            queryset = queryset.filter(college__icontains=filters["college"])
        if filters.get("source_file"):
            queryset = queryset.filter(source_file_id=filters["source_file"])
        if filters.get("search"):
            term = filters["search"].strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term)
                    | Q(email__icontains=term)
                    | Q(college__icontains=term)
                )

    deleted, _ = queryset.delete()
    return {"deleted": deleted}


@shared_task(
    bind=True,
    queue="bulk_ops",
    name="apps.contacts.tasks.generate_contacts_export",
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_contacts_export(self, payload: dict):
    queryset = Contact.objects.filter(is_valid=True).only(
        "name", "email", "phone", "college", "email_status", "created_at"
    )

    contact_ids = payload.get("contact_ids")
    filters = payload.get("filter")

    if contact_ids:
        queryset = queryset.filter(id__in=contact_ids)
    elif filters:
        if filters.get("status"):
            queryset = queryset.filter(email_status=filters["status"])
        if filters.get("college"):
            queryset = queryset.filter(college__icontains=filters["college"])
        if filters.get("source_file"):
            queryset = queryset.filter(source_file_id=filters["source_file"])
        if filters.get("search"):
            term = filters["search"].strip()
            if term:
                queryset = queryset.filter(
                    Q(name__icontains=term)
                    | Q(email__icontains=term)
                    | Q(college__icontains=term)
                )

    export_dir = Path(settings.MEDIA_ROOT) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"contacts_export_{uuid.uuid4().hex}.csv"
    file_path = export_dir / filename

    with open(file_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Name", "Email", "Phone", "College", "Status", "Imported At"])
        for contact in queryset.iterator(chunk_size=5000):
            writer.writerow(
                [
                    contact.name,
                    contact.email,
                    contact.phone or "",
                    contact.college or "",
                    contact.email_status,
                    contact.created_at.strftime("%Y-%m-%d %H:%M:%S") if contact.created_at else "",
                ]
            )

    return {
        "download_url": f"{settings.MEDIA_URL}exports/{filename}",
        "filename": filename,
        "count": queryset.count(),
    }
