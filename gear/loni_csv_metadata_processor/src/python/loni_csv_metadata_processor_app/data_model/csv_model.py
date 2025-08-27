"""
CSV Data Model for representing and validating CSV data.
"""
import csv
from enum import Enum

from pydantic import BaseModel


class CSVType(Enum):
    """
    Defines the types of CSV files that can be processed.
    """

    MRI = "mri"
    PET = "pet"
    BASE = "base"


class CSVRecord(BaseModel):
    """
    Base class for CSV records.

    Attributes:
        id: Unique identifier for the record
        record_type: Type of the CSV record (MRI, PET, or BASE)
    """

    # Common fields for all CSV types
    id: str
    record_type: CSVType = CSVType.BASE

    class Config:
        """Pydantic configuration."""

        extra = "allow"  # Allow additional fields beyond what's defined


class MRIRecord(CSVRecord):
    """
    Record type for MRI CSV files.

    Contains fields specific to MRI records with field_a1 and field_a2 as
    required fields. Additional fields can be dynamically added as this uses
    Pydantic's 'extra=allow' config.
    """

    # Required fields specific to MRI
    # typing will be specified in the full model

    field_a1 = None
    field_a2 = None

    # Optional fields
    field_a3 = None

    record_type: CSVType = CSVType.MRI


class PETRecord(CSVRecord):
    """
    Record type for PET CSV files.

    Contains fields specific to PET records with field_b1 and field_b2 as
    required fields. Additional fields can be dynamically added as this uses
    Pydantic's 'extra=allow' config.
    """

    # Required fields specific to PET
    # typing will be specified in the full model
    field_b1 = None
    field_b2 = None

    # Optional fields
    field_b3 = None

    record_type: CSVType = CSVType.PET


class CSVDataModel:
    """
    Represents a single-row CSV file with validation capabilities.

    This class handles loading a CSV file, determining its type (MRI or PET),
    and creating the appropriate record instance based on the headers.
    """

    def __init__(self, csv_path):
        """
        Initialize the CSV data model.

        Args:
            csv_path: Path to the CSV file to process.
        """
        self.csv_path = csv_path
        self.record = None

        # Mapping of column patterns to CSV types
        # can be initialized from the Record class keys
        self.TYPE_INDICATORS = {
            CSVType.MRI: {"field_a1", "field_a2"},
            CSVType.PET: {"field_b1", "field_b2"},
        }

    def determine_record_class(self, headers):
        """
        Determine the record class based on CSV headers.

        Examines the headers against the TYPE_INDICATORS mapping to identify
        whether the CSV represents an MRI or PET record.

        Args:
            headers: List of column headers from the CSV file.

        Returns:
            The appropriate record class (MRIRecord or PETRecord).
            Defaults to MRIRecord if type cannot be determined.
        """
        headers_set = set(headers)

        # Check headers against required columns for each type
        for csv_type, required_columns in self.TYPE_INDICATORS.items():
            if required_columns.issubset(headers_set):
                # Return the appropriate record class based on the CSV type
                if csv_type == CSVType.MRI:
                    return MRIRecord
                elif csv_type == CSVType.PET:
                    return PETRecord

        # Default to MRIRecord for outline purposes
        return MRIRecord

    def _load_csv_data(self):
        """
        Load the CSV data from the file.

        Opens the CSV file and reads the headers and the first row of data.
        This method only processes the first row, as the model is designed
        for single-row CSV files.

        Returns:
            Tuple of (headers, row_data) where headers is a list of column names
            and row_data is a dictionary mapping column names to values.
        """
        with open(self.csv_path, "r", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            headers = reader.fieldnames or []

            # Read the first row only
            rows = list(reader)
            row_data = rows[0] if rows else {}

            return headers, row_data

    def load(self):
        """
        Load the CSV file and create the appropriate record instance.

        This method loads the data from the CSV file, determines the record type
        based on the headers, and initializes the appropriate record instance.
        The record can be retrieved using the get_record() method.
        """
        # Load the CSV data
        headers, row_data = self._load_csv_data()

        # Determine the record class directly from the headers
        record_class = self.determine_record_class(headers)

        # Create the record instance
        self.record = record_class(**row_data)

    def get_record(self):
        """
        Get the record from the CSV file.

        This method should be called after load() to retrieve the created record.

        Returns:
            The CSV record (MRIRecord or PETRecord instance) or None if the file
            has not been loaded yet.
        """
        return self.record
