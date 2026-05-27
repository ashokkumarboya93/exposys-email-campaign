import re

import pandas as pd

# Pre-compiled email regex for performance
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


class DataValidator:
    """
    Service for validating contact data from an uploaded DataFrame.

    Checks email format, duplicate emails, name presence, and phone normalization.
    Returns a tuple of (valid_df, invalid_rows_list).
    """

    def _find_column_for_field(self, column_map: dict, field: str) -> str | None:
        """
        Find the original column name mapped to a given field type.

        Args:
            column_map: Dict mapping original column names to field types.
            field: The field type to search for (e.g. 'email', 'name', 'phone').

        Returns:
            The original column name or None if not found.
        """
        for col_name, field_type in column_map.items():
            if field_type == field:
                return col_name
        return None

    def _is_valid_email(self, email: str) -> bool:
        """Check if an email matches the expected format."""
        if not email or not isinstance(email, str):
            return False
        return bool(EMAIL_REGEX.match(email.strip()))

    def _is_valid_name(self, name) -> bool:
        """Check if a name is present and non-empty."""
        if name is None or (isinstance(name, float) and pd.isna(name)):
            return False
        if pd.isna(name):
            return False
        name_str = str(name).strip()
        return len(name_str) > 0 and name_str.lower() != 'nan'

    def _normalize_phone(self, phone) -> str | None:
        """
        Normalize a phone number by stripping +, -, spaces.
        Returns the last 10 digits if valid, else None.
        """
        if phone is None or (isinstance(phone, float) and pd.isna(phone)):
            return None
        if pd.isna(phone):
            return None

        phone_str = str(phone).strip()
        if phone_str.lower() == 'nan' or phone_str == '':
            return None

        # Strip common formatting characters
        cleaned = phone_str.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

        # Remove any trailing decimal (e.g. "9876543210.0" from pandas int->float conversion)
        if '.' in cleaned:
            cleaned = cleaned.split('.')[0]

        if not cleaned.isdigit():
            return None

        # Normalize to last 10 digits (handle country codes)
        if len(cleaned) >= 10:
            return cleaned[-10:]

        return cleaned

    def validate(self, df: pd.DataFrame, column_map: dict) -> tuple[pd.DataFrame, list]:
        """
        Validate every row in the DataFrame against the column map.

        Validation rules:
        1. Email must match the regex pattern.
        2. Email must not be a duplicate.
        3. Name must be present and non-empty.
        4. Phone (if present) must be all digits after stripping formatting;
           normalized to last 10 digits.

        Args:
            df: The pandas DataFrame to validate.
            column_map: Dict mapping original column names to recognized field types.

        Returns:
            A tuple of:
            - valid_df: DataFrame of valid rows with a 'status' column set to 'pending'.
            - invalid_rows: List of dicts with 'row', 'email', and 'reason' keys.
        """
        email_col = self._find_column_for_field(column_map, 'email')
        name_col = self._find_column_for_field(column_map, 'name')
        phone_col = self._find_column_for_field(column_map, 'phone')

        valid_indices = []
        invalid_rows = []
        seen_emails = set()

        for idx, row in df.iterrows():
            row_number = idx + 1  # 1-indexed row number for user-friendly reporting
            email_value = str(row.get(email_col, '')).strip() if email_col else ''
            reasons = []

            # 1. Validate email format
            if not email_col:
                reasons.append('No email column found')
            elif not self._is_valid_email(email_value):
                reasons.append('Invalid email format')

            # 2. Check for duplicate email
            if email_col and email_value:
                email_lower = email_value.lower()
                if email_lower in seen_emails:
                    reasons.append('Duplicate email')
                else:
                    seen_emails.add(email_lower)

            # 3. Validate name
            if name_col:
                name_value = row.get(name_col)
                if not self._is_valid_name(name_value):
                    reasons.append('Name is empty or missing')

            # 4. Validate and normalize phone
            if phone_col:
                phone_value = row.get(phone_col)
                normalized_phone = self._normalize_phone(phone_value)
                if phone_value is not None and not pd.isna(phone_value):
                    phone_str = str(phone_value).strip()
                    if phone_str.lower() != 'nan' and phone_str != '':
                        if normalized_phone is None:
                            reasons.append('Invalid phone number')
                        else:
                            df.at[idx, phone_col] = normalized_phone

            if reasons:
                invalid_rows.append({
                    'row': row_number,
                    'email': email_value if email_value else '',
                    'reason': '; '.join(reasons),
                })
            else:
                valid_indices.append(idx)

        valid_df = df.loc[valid_indices].copy()
        valid_df['status'] = 'pending'

        return valid_df, invalid_rows
