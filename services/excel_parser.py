import pandas as pd


class FileParsingError(Exception):
    """Raised when a file cannot be parsed."""
    pass


class ExcelParser:
    """Service for parsing CSV, XLSX, and XLS files into DataFrames."""

    def read_file(self, file_path: str, file_format: str) -> pd.DataFrame:
        """
        Read a file into a pandas DataFrame based on the given format.

        Args:
            file_path: Absolute path to the file on disk.
            file_format: One of 'csv', 'xlsx', or 'xls'.

        Returns:
            A cleaned pandas DataFrame with stripped column names and string values.

        Raises:
            FileParsingError: If the file format is unsupported or the file cannot be read.
        """
        try:
            if file_format == 'csv':
                df = pd.read_csv(file_path)
            elif file_format == 'xlsx':
                df = pd.read_excel(file_path, engine='openpyxl')
            elif file_format == 'xls':
                df = pd.read_excel(file_path, engine='xlrd')
            else:
                raise FileParsingError(f'Unsupported file format: {file_format}')
        except FileParsingError:
            raise
        except Exception as e:
            raise FileParsingError(f'Failed to parse file: {str(e)}') from e

        # Strip whitespace from column names
        df.columns = df.columns.str.strip()

        # Convert all columns to string to avoid type assignment errors during validation
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace('nan', pd.NA)
            df[col] = df[col].replace('None', pd.NA)

        return df
