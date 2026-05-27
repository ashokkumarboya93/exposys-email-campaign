import csv
import os
import re
import uuid
from pathlib import Path

import pandas as pd
from celery import shared_task
from django.conf import settings
from django.db.models import F, Q

from apps.contacts.models import Contact, UploadedFile

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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


def _iter_chunks(file_path: str, file_format: str, chunk_size: int = 5000):
    if file_format == "csv":
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            yield chunk
        return

    dataframe = pd.read_excel(file_path)
    for start in range(0, len(dataframe), chunk_size):
        yield dataframe.iloc[start : start + chunk_size]


def _chunk_to_contacts(chunk: pd.DataFrame, column_map: dict[str, str], file_record: UploadedFile, tags: str = ""):
    email_col = next((k for k, v in column_map.items() if v == "email"), None)
    name_col = next((k for k, v in column_map.items() if v == "name"), None)
    phone_col = next((k for k, v in column_map.items() if v == "phone"), None)
    college_col = next((k for k, v in column_map.items() if v == "college"), None)
    extra_cols = [k for k, v in column_map.items() if v == "extra"]

    contacts = []
    valid = 0
    invalid = 0

    for _, row in chunk.iterrows():
        email = str(row.get(email_col, "")).strip() if email_col else ""
        if not email or email.lower() == "nan" or not EMAIL_PATTERN.match(email):
            invalid += 1
            continue

        extra_fields = {}
        if tags:
            extra_fields["tags"] = tags

        for col in extra_cols:
            value = row.get(col)
            if pd.notna(value) and str(value).strip():
                extra_fields[col] = str(value).strip()

        contact = Contact(
            source_file=file_record,
            name=str(row.get(name_col, "")).strip() if name_col and pd.notna(row.get(name_col)) else "",
            email=email,
            phone=str(row.get(phone_col, "")).strip() if phone_col and pd.notna(row.get(phone_col)) else None,
            college=str(row.get(college_col, "")).strip() if college_col and pd.notna(row.get(college_col)) else None,
            extra_fields=extra_fields,
            email_status="pending",
            is_valid=True,
        )
        contacts.append(contact)
        valid += 1

    return contacts, valid, invalid


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

    total_rows = 0
    total_duplicates = 0
    first_chunk = True
    column_map: dict[str, str] = {}

    # Pre-load ALL existing emails into a set for O(1) duplicate checks.
    # Even at 100k contacts, a set of email strings is ~20MB in RAM — totally fine.
    existing_emails: set[str] = set(
        Contact.objects.filter(is_valid=True).values_list("email", flat=True)
    )

    try:
        for chunk in _iter_chunks(file_record.stored_path, file_record.file_format, chunk_size=5000):
            if first_chunk:
                column_map = _detect_columns(list(chunk.columns))
                UploadedFile.objects.filter(id=file_record.id).update(column_mapping=column_map)
                first_chunk = False

            contacts, valid_count, invalid_count = _chunk_to_contacts(chunk, column_map, file_record, tags=tags)

            # ── Duplicate detection ──
            new_contacts = []
            chunk_duplicates = 0
            for contact in contacts:
                email_lower = contact.email.lower().strip()
                if email_lower in existing_emails:
                    chunk_duplicates += 1
                else:
                    existing_emails.add(email_lower)  # Track so intra-file dupes are caught too
                    new_contacts.append(contact)

            total_duplicates += chunk_duplicates

            if new_contacts:
                Contact.objects.bulk_create(new_contacts, batch_size=1000, ignore_conflicts=True)

            processed_rows = len(chunk)
            total_rows += processed_rows
            UploadedFile.objects.filter(id=file_record.id).update(
                processed_rows=F("processed_rows") + processed_rows,
                valid_rows=F("valid_rows") + len(new_contacts),
                invalid_rows=F("invalid_rows") + invalid_count,
            )

        UploadedFile.objects.filter(id=file_record.id).update(
            total_rows=total_rows,
            upload_status="completed",
            duplicate_rows=total_duplicates,
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

    updated = queryset.update(is_valid=False)
    return {"deleted": updated}


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
        for contact in queryset.iterator(chunk_size=2000):
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
