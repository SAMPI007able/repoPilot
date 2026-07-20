from pydantic import BaseModel, Field


class CodeMethod(BaseModel):
    name: str


class CodeClass(BaseModel):
    name: str


class ImportReference(BaseModel):
    module: str
    resolved: str | None = None
    kind: str


class ParsedFile(BaseModel):
    path: str
    file: str
    source_code: str
    existing_tests: list[str] = Field(default_factory=list)
    is_test_file: bool = False
    classes: list[CodeClass] = Field(default_factory=list)
    functions: list[CodeMethod] = Field(default_factory=list)
    imports: list[ImportReference] = Field(default_factory=list)


class ParsedFileSummary(BaseModel):
    path: str
    classes: int
    functions: int
    imports: int
    existing_tests: int


class RepositoryStatistics(BaseModel):
    files: int
    typescript: int
    javascript: int


class RepositoryMetadata(BaseModel):
    repository: str
    statistics: RepositoryStatistics
    testFramework: str | None = None
    packageInfo: "PackageIntelligence | None" = None
    documentation: list["DocumentationAsset"] = Field(default_factory=list)
    parsedFiles: list[ParsedFileSummary] = Field(default_factory=list)
    parsed_file_details: list[ParsedFile] = Field(default_factory=list, exclude=True)
    relationships: list["GraphRelationship"] = Field(default_factory=list, exclude=True)


class GraphRelationship(BaseModel):
    source: str
    target: str
    module: str
    kind: str


class GenerationContext(BaseModel):
    target: str
    test_type: str
    target_source: str
    classes: list[CodeClass] = Field(default_factory=list)
    imports: list[ImportReference] = Field(default_factory=list)
    methods: list[CodeMethod] = Field(default_factory=list)
    dependencies: list["DependencySummary"] = Field(default_factory=list)
    existing_tests: list[str] = Field(default_factory=list)
    test_framework: str | None = None
    package_info: "PackageIntelligence | None" = None
    documentation: list["DocumentationAsset"] = Field(default_factory=list)


class DependencySummary(BaseModel):
    name: str
    reason: str
    source: str
    path: str | None = None


class PackageIntelligence(BaseModel):
    testFramework: str | None = None
    dependencies: dict[str, str] = Field(default_factory=dict)
    devDependencies: dict[str, str] = Field(default_factory=dict)
    scripts: dict[str, str] = Field(default_factory=dict)
    typescriptVersion: str | None = None
    reactVersion: str | None = None
    vueVersion: str | None = None


class DocumentationAsset(BaseModel):
    path: str
    source: str
