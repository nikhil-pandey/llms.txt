class LlmsTxtError(Exception):
    """Base exception for all llms-txt errors"""


class DiscoveryError(LlmsTxtError):
    """Error during package/documentation discovery"""



class FetchError(LlmsTxtError):
    """Error during content fetching"""


class ProcessingError(LlmsTxtError):
    """Error during documentation processing"""


class StorageError(LlmsTxtError):
    """Error during storage operations"""
