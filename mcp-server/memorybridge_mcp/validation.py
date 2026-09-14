"""
memorybridge_mcp.validation
----------------------------
Input validation utilities for MCP tools.

Centralizes validation logic to ensure consistent error messages and
prevent invalid inputs from reaching the database layer.
"""

from uuid import UUID


def validate_uuid(value: str, param_name: str = "id") -> str:
    """
    Validate that a string is a valid UUID format.
    
    Args:
        value: The string to validate
        param_name: Parameter name for error message
        
    Returns:
        The original string if valid
        
    Raises:
        ValueError: If the string is not a valid UUID
    """
    if not value or not value.strip():
        raise ValueError(f"{param_name} cannot be empty")
    
    try:
        UUID(value)
        return value
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"{param_name} must be a valid UUID format. "
            f"Received: {value!r}"
        ) from exc


def validate_max_length(value: str, max_len: int, param_name: str) -> str:
    """
    Validate that a string does not exceed maximum length.
    
    Args:
        value: The string to validate
        max_len: Maximum allowed length
        param_name: Parameter name for error message
        
    Returns:
        The original string if valid
        
    Raises:
        ValueError: If the string exceeds max_len
    """
    if len(value) > max_len:
        raise ValueError(
            f"{param_name} exceeds maximum length of {max_len} characters. "
            f"Received: {len(value)} characters"
        )
    return value
