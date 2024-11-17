from enum import Enum


class RegistryType(str, Enum):
    PYPI = "pypi"
    NPM = "npm"
    CARGO = "cargo"
    NUGET = "nuget"
    OTHER = "other"


class SourceType(str, Enum):
    GITHUB = "github"
    HTTP = "http"


class DocFormat(str, Enum):
    MKDOCS = "mkdocs"
    SPHINX = "sphinx"
    PLAIN = "plain"
    OTHER = "other"
