from pydantic import BaseModel, Field
from sqlalchemy import inspect


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool


class ForeignKeyInfo(BaseModel):
    columns: list[str]
    references_table: str
    references_columns: list[str]


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)

    @property
    def table_names(self) -> set[str]:
        return {table.name for table in self.tables}


def get_database_schema(engine, schema_name="public") -> DatabaseSchema:

    inspector = inspect(engine)

    schema = DatabaseSchema()

    tables = inspector.get_table_names(
        schema=schema_name
    )

    for table_name in tables:

        table = TableInfo(name=table_name)

        columns = inspector.get_columns(
            table_name,
            schema=schema_name
        )

        for column in columns:

            table.columns.append(ColumnInfo(
                name=column["name"],
                type=str(column["type"]),
                nullable=column["nullable"]
            ))

        pk = inspector.get_pk_constraint(
            table_name,
            schema=schema_name
        )

        table.primary_key = pk.get(
            "constrained_columns",
            []
        )

        foreign_keys = inspector.get_foreign_keys(
            table_name,
            schema=schema_name
        )

        for fk in foreign_keys:

            table.foreign_keys.append(ForeignKeyInfo(
                columns=fk["constrained_columns"],
                references_table=fk["referred_table"],
                references_columns=fk["referred_columns"]
            ))

        schema.tables.append(table)

    return schema


def schema_to_text(schema: DatabaseSchema):

    output = []

    for table in schema.tables:

        output.append(
            f"TABLE: {table.name}"
        )

        output.append("COLUMNS:")

        for column in table.columns:

            nullable = (
                "NULL"
                if column.nullable
                else "NOT NULL"
            )

            output.append(
                f"  - {column.name} "
                f"{column.type} {nullable}"
            )

        if table.primary_key:

            output.append(
                "PRIMARY KEY: "
                + ", ".join(table.primary_key)
            )

        for fk in table.foreign_keys:

            for column, ref_column in zip(
                fk.columns,
                fk.references_columns
            ):

                output.append(
                    f"FOREIGN KEY: "
                    f"{column} -> "
                    f"{fk.references_table}."
                    f"{ref_column}"
                )

        output.append("")

    return "\n".join(output)
