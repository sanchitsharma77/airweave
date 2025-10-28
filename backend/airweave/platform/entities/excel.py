"""Microsoft Excel entity schemas.

Entity schemas for Microsoft Excel objects based on Microsoft Graph API:
 - Workbook (Excel file)
 - Worksheet (individual sheets/tabs)
 - Table (structured data tables within worksheets)

Reference:
  https://learn.microsoft.com/en-us/graph/api/resources/excel
  https://learn.microsoft.com/en-us/graph/api/resources/workbook
  https://learn.microsoft.com/en-us/graph/api/resources/worksheet
  https://learn.microsoft.com/en-us/graph/api/resources/table
"""

from typing import Any, Dict, List, Optional

from airweave.platform.entities._airweave_field import AirweaveField
from airweave.platform.entities._base import BaseEntity


class ExcelWorkbookEntity(BaseEntity):
    """Schema for a Microsoft Excel workbook (file).

    Represents the Excel file itself with metadata.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/driveitem
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the workbook/file ID)
    # - breadcrumbs (empty - workbooks are top-level)
    # - name (from workbook name without extension)
    # - created_at (from created_datetime)
    # - updated_at (from last_modified_datetime)

    # API fields
    file_name: str = AirweaveField(
        ..., description="The full file name including extension.", embeddable=True
    )
    web_url: Optional[str] = AirweaveField(
        None, description="URL to open the workbook in Excel Online.", embeddable=False
    )
    size: Optional[int] = AirweaveField(
        None, description="Size of the file in bytes.", embeddable=False
    )
    created_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who created the workbook.", embeddable=True
    )
    last_modified_by: Optional[Dict[str, Any]] = AirweaveField(
        None, description="Identity of the user who last modified the workbook.", embeddable=True
    )
    parent_reference: Optional[Dict[str, Any]] = AirweaveField(
        None,
        description="Information about the parent folder/drive location.",
        embeddable=False,
    )
    drive_id: Optional[str] = AirweaveField(
        None, description="ID of the drive containing this workbook.", embeddable=False
    )
    description: Optional[str] = AirweaveField(
        None, description="Description of the workbook if available.", embeddable=True
    )


class ExcelWorksheetEntity(BaseEntity):
    """Schema for a Microsoft Excel worksheet (sheet/tab).

    Represents individual sheets within an Excel workbook.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/worksheet
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the worksheet ID)
    # - breadcrumbs (workbook breadcrumb)
    # - name (from worksheet name)
    # - created_at (None - worksheets don't have creation timestamp)
    # - updated_at (from last_modified_datetime)

    # API fields
    workbook_id: str = AirweaveField(
        ..., description="ID of the parent workbook.", embeddable=False
    )
    workbook_name: str = AirweaveField(
        ..., description="Name of the parent workbook.", embeddable=True
    )
    position: Optional[int] = AirweaveField(
        None,
        description="The zero-based position of the worksheet within the workbook.",
        embeddable=False,
    )
    visibility: Optional[str] = AirweaveField(
        None,
        description="The visibility of the worksheet (Visible, Hidden, VeryHidden).",
        embeddable=False,
    )
    range_address: Optional[str] = AirweaveField(
        None,
        description="The address of the used range (e.g., 'A1:Z100').",
        embeddable=False,
    )
    cell_content: Optional[str] = AirweaveField(
        None,
        description="Formatted text representation of the cell content in the used range.",
        embeddable=True,
    )
    row_count: Optional[int] = AirweaveField(
        None, description="Number of rows with data in the worksheet.", embeddable=False
    )
    column_count: Optional[int] = AirweaveField(
        None, description="Number of columns with data in the worksheet.", embeddable=False
    )
    last_modified_datetime: Optional[Any] = AirweaveField(
        None,
        description="Timestamp at which the worksheet was last modified.",
        embeddable=False,
    )


class ExcelTableEntity(BaseEntity):
    """Schema for a Microsoft Excel table.

    Represents structured data tables within worksheets.

    Reference:
        https://learn.microsoft.com/en-us/graph/api/resources/table
    """

    # Base fields are inherited and set during entity creation:
    # - entity_id (the table ID)
    # - breadcrumbs (workbook and worksheet breadcrumbs)
    # - name (from table name)
    # - created_at (None - tables don't have creation timestamp)
    # - updated_at (from last_modified_datetime)

    # API fields
    workbook_id: str = AirweaveField(
        ..., description="ID of the parent workbook.", embeddable=False
    )
    workbook_name: str = AirweaveField(
        ..., description="Name of the parent workbook.", embeddable=True
    )
    worksheet_id: str = AirweaveField(
        ..., description="ID of the parent worksheet.", embeddable=False
    )
    worksheet_name: str = AirweaveField(
        ..., description="Name of the parent worksheet.", embeddable=True
    )
    display_name: Optional[str] = AirweaveField(
        None, description="Display name of the table.", embeddable=True
    )
    show_headers: Optional[bool] = AirweaveField(
        None, description="Indicates whether the header row is visible.", embeddable=False
    )
    show_totals: Optional[bool] = AirweaveField(
        None, description="Indicates whether the total row is visible.", embeddable=False
    )
    style: Optional[str] = AirweaveField(
        None, description="Style name of the table.", embeddable=False
    )
    highlight_first_column: Optional[bool] = AirweaveField(
        None,
        description="Indicates whether the first column contains special formatting.",
        embeddable=False,
    )
    highlight_last_column: Optional[bool] = AirweaveField(
        None,
        description="Indicates whether the last column contains special formatting.",
        embeddable=False,
    )
    row_count: Optional[int] = AirweaveField(
        None, description="Number of rows in the table.", embeddable=False
    )
    column_count: Optional[int] = AirweaveField(
        None, description="Number of columns in the table.", embeddable=False
    )
    column_names: Optional[List[str]] = AirweaveField(
        default_factory=list,
        description="Names of the columns in the table.",
        embeddable=True,
    )
    table_data: Optional[str] = AirweaveField(
        None,
        description="The actual table data as formatted text (rows and columns).",
        embeddable=True,
    )
    last_modified_datetime: Optional[Any] = AirweaveField(
        None,
        description="Timestamp at which the table was last modified.",
        embeddable=False,
    )
