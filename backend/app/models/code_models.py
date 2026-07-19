from pydantic import BaseModel, Field


class CodeMethod(BaseModel):
    name: str


class CodeClass(BaseModel):
    name: str


class ImportReference(BaseModel):
    path: str


class ParsedFile(BaseModel):
    path: str
    file: str
    classes: list[CodeClass] = Field(default_factory=list)
    functions: list[CodeMethod] = Field(default_factory=list)
    imports: list[ImportReference] = Field(default_factory=list)


class ParsedFileSummary(BaseModel):
    path: str
    classes: int
    functions: int
    imports: int


class RepositoryStatistics(BaseModel):
    files: int
    typescript: int
    javascript: int


class RepositoryMetadata(BaseModel):
    repository: str
    statistics: RepositoryStatistics
    parsedFiles: list[ParsedFileSummary] = Field(default_factory=list)
