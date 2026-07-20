from app.models.code_models import GraphRelationship, ParsedFile


class GraphService:
    def build_relationships(self, parsed_files: list[ParsedFile]) -> list[GraphRelationship]:
        relationships: list[GraphRelationship] = []

        for parsed_file in parsed_files:
            for import_reference in parsed_file.imports:
                if import_reference.kind != "local" or not import_reference.resolved:
                    continue

                relationships.append(
                    GraphRelationship(
                        source=parsed_file.path,
                        target=import_reference.resolved,
                        module=import_reference.module,
                        kind=import_reference.kind,
                    )
                )

        return relationships

    def get_outgoing_relationships(
        self,
        relationships: list[GraphRelationship],
        source_path: str,
    ) -> list[GraphRelationship]:
        return [relationship for relationship in relationships if relationship.source == source_path]
