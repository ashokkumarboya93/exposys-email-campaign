class ColumnRecognizer:
    """
    Service for recognizing column names from uploaded files and mapping
    them to known contact field types: email, name, phone, college.
    Unrecognized columns are mapped to 'extra'.
    """

    EMAIL_KEYWORDS = [
        'email', 'mail', 'gmail', 'email_id', 'emailid', 'e-mail', 'email address',
    ]
    NAME_KEYWORDS = [
        'name', 'full_name', 'fullname', 'student_name', 'candidate_name', 'applicant_name',
    ]
    PHONE_KEYWORDS = [
        'phone', 'mobile', 'contact', 'number', 'mob', 'phone_no', 'mobile_no', 'contact_no',
    ]
    COLLEGE_KEYWORDS = [
        'college', 'institution', 'university', 'campus', 'institute', 'school', 'org',
    ]

    # Ordered so that more specific field types are checked first
    FIELD_KEYWORD_MAP = [
        ('email', EMAIL_KEYWORDS),
        ('name', NAME_KEYWORDS),
        ('phone', PHONE_KEYWORDS),
        ('college', COLLEGE_KEYWORDS),
    ]

    def _normalize(self, column_name: str) -> str:
        """
        Normalize a column name for comparison:
        lowercase, strip whitespace, replace spaces with underscores.
        """
        return column_name.lower().strip().replace(' ', '_')

    def _match_field(self, normalized_name: str) -> str:
        """
        Attempt to match a normalized column name against known keyword lists.

        Returns the recognized field name ('email', 'name', 'phone', 'college')
        or 'extra' if no match is found.
        """
        for field_name, keywords in self.FIELD_KEYWORD_MAP:
            for keyword in keywords:
                normalized_keyword = keyword.replace(' ', '_')
                if normalized_name == normalized_keyword:
                    return field_name
                # Also match if the column name contains the keyword
                if normalized_keyword in normalized_name:
                    return field_name
        return 'extra'

    def recognize(self, columns: list[str]) -> dict:
        """
        Recognize a list of column names and map each to a known field type.

        Args:
            columns: List of original column name strings from the uploaded file.

        Returns:
            A dict mapping each original column name to its recognized field type.
            Example:
                {
                    'Email ID': 'email',
                    'Full Name': 'name',
                    'Mobile': 'phone',
                    'University': 'college',
                    'City': 'extra',
                }
        """
        result = {}
        assigned_fields = set()

        for col in columns:
            normalized = self._normalize(col)
            field = self._match_field(normalized)

            # Prevent duplicate assignment of core fields
            if field != 'extra' and field in assigned_fields:
                result[col] = 'extra'
            else:
                result[col] = field
                if field != 'extra':
                    assigned_fields.add(field)

        return result
