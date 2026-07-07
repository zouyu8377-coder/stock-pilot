class TushareConfigError(RuntimeError):
    """Raised when Tushare is requested without safe backend configuration."""


class TushareRequestError(RuntimeError):
    """Raised for sanitized Tushare request failures."""
