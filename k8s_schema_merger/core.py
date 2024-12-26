import json
from os import walk
from pathlib import Path
from shutil import copy
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any, Iterable
from urllib.request import urlopen
from zipfile import ZipFile

from kubernetes import client

K8S_SCHEMAS_URL = (
    "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/refs/heads/master"
)


def get_builtin_schemas(version: str, all_file: Path, definitions_file: Path) -> None:
    versioned_url = f"{K8S_SCHEMAS_URL}/v1.{version}.0-standalone-strict"
    with (
        urlopen(f"{versioned_url}/all.json") as response,
        open(all_file, "wb") as output_file,
    ):
        output_file.write(response.read())
    with (
        urlopen(f"{versioned_url}/_definitions.json") as response,
        open(definitions_file, "wb") as output_file,
    ):
        output_file.write(response.read())


def get_crds_from_k8s(output_dir: Path) -> None:
    api_instance = client.ApiextensionsV1Api()
    crds = api_instance.list_custom_resource_definition()
    for crd in crds.items:
        spec = crd.spec
        kind = spec.names.kind
        if schema := spec.versions[0].schema:
            print(f" - {kind}")
            assert schema.open_apiv3_schema
            schema = additional_properties(schema.open_apiv3_schema.to_dict())
            schema = replace_int_or_string(schema)
            schema = add_enum_attribute(schema, kind)
            with open(output_dir / f"{kind}.json", "w") as output_file:
                output_file.write(json.dumps(schema, indent=2, sort_keys=True))


def get_crds_from_catalog(groups: Iterable[str], output_dir: Path) -> None:
    error = None
    tmp_file_path = None
    try:
        with TemporaryDirectory() as extract_to:
            with urlopen(
                "https://github.com/datreeio/CRDs-catalog/archive/refs/heads/main.zip"
            ) as response:
                with NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(response.read())
                    tmp_file_path = tmp_file.name
            with ZipFile(tmp_file_path, "r") as zip_ref:
                zip_ref.extractall(extract_to)

            for crd in groups:
                crd_dir = Path(f"{extract_to}/CRDs-catalog-main/{crd}")
                if not crd_dir.exists():
                    print(f"The API group {crd} does not exist in the CRD catalog")
                    continue
                for file in crd_dir.iterdir():
                    schema = json.loads(file.read_text())
                    kind = str(file.name).split("_")[0]
                    schema = add_enum_attribute(
                        schema, kind
                    )  # TODO: `kind` should be camel-cased for this to work
                    with open(output_dir / f"{kind}.json", "w") as output_file:
                        output_file.write(json.dumps(schema, indent=2, sort_keys=True))
    except Exception as e:
        error = e
    finally:
        if tmp_file_path:
            Path(tmp_file_path).unlink()
    if error:
        raise RuntimeError(f"Failed to download and extract the CRD catalog: {error}")


def additional_properties(data: Any) -> Any:
    "This recreates the behaviour of kubectl at https://github.com/kubernetes/kubernetes/blob/225b9119d6a8f03fcbe3cc3d590c261965d928d0/pkg/kubectl/validation/schema.go#L312"
    if isinstance(data, dict):
        data = {key: value for key, value in data.items() if value is not None}
        for key, value in data.items():
            data[key] = additional_properties(value)
        if "additional_properties" in data:
            data["additionalProperties"] = data["additional_properties"]
            del data["additional_properties"]
        if "properties" in data and "additionalProperties" not in data:
            data["additionalProperties"] = False
    return data


def replace_int_or_string(data: Any) -> dict[str, Any]:
    new = {}
    try:
        for k, v in iter(data.items()):
            new_v = v
            if isinstance(v, dict):
                if "format" in v and v["format"] == "int-or-string":
                    new_v = {"oneOf": [{"type": "string"}, {"type": "integer"}]}
                else:
                    new_v = replace_int_or_string(v)
            elif isinstance(v, list):
                new_v = list()
                for x in v:
                    new_v.append(replace_int_or_string(x))
            else:
                new_v = v
            new[k] = new_v
        return new
    except AttributeError:
        return data


def add_enum_attribute(schema: dict[str, Any], kind: str) -> dict[str, Any]:
    schema["properties"]["kind"]["enum"] = [kind]
    return schema


def allow_null_optional_fields(
    data: Any, parent: Any = None, grand_parent: Any = None, _=None
) -> dict[str, Any]:
    new = {}
    try:
        for k, v in iter(data.items()):
            new_v = v
            if isinstance(v, dict):
                new_v = allow_null_optional_fields(v, data, parent, k)
            elif isinstance(v, list):
                new_v = list()
                for x in v:
                    new_v.append(allow_null_optional_fields(x, v, parent, k))
            elif isinstance(v, str):
                is_non_null_type = k == "type" and v != "null"
                has_required_fields = grand_parent and "required" in grand_parent
                if is_non_null_type and not has_required_fields:
                    new_v = [v, "null"]
            new[k] = new_v
        return new
    except AttributeError:
        return data


def write_index_file(all_file: Path) -> None:
    with open(all_file) as file:
        refs = json.load(file)["oneOf"]
        index = {ref["$ref"] for ref in refs}
    for _, _, files in walk(all_file.parent):
        for file in files:
            if file not in ["all.json", "_definitions.json"]:
                index.add(file.split(".")[0] + ".json")
    with open(all_file, "w") as output_file:
        refs = sorted([{"$ref": ref} for ref in index], key=lambda x: x["$ref"])
        output_file.write(json.dumps({"oneOf": refs}, indent=2, sort_keys=True))
