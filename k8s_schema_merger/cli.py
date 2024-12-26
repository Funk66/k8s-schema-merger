from argparse import ArgumentParser, Namespace
from os import getenv
from pathlib import Path
from re import match

from kubernetes import client, config

from .core import (
    get_builtin_schemas,
    get_crds_from_catalog,
    get_crds_from_k8s,
    write_index_file,
)

DATA_HOME = Path(getenv("XDG_DATA_HOME", "~/.local/share")).expanduser()
VERSION_REGEX = r"(v)?(\d\.)?(\d\d)(\.\d)?"


def validate_input(args: Namespace):
    if not args.output_dir.exists():
        if not args.output_dir.parent.exists():
            raise FileNotFoundError(
                f"The dir {args.output_dir.parent} does not exist. Use the '--output-dir' argument to specify an alternative path."
            )
        args.output_dir.mkdir()

    if args.version and not match(VERSION_REGEX, args.version):
        raise ValueError(f"Wrong version format: {args.version}")

    if not args.crds or not args.version:
        try:
            config.load_kube_config()
        except config.config_exception.ConfigException:
            raise RuntimeError("You don't seem to have K8s credentials configured")


def main():
    parser = ArgumentParser(description="K8s Schema Merger")
    parser.add_argument(
        "crds",
        nargs="*",
        help="CRD schemas to be merged",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output dir",
        type=Path,
        default=DATA_HOME / "k8s-schema-merger",
    )
    parser.add_argument(
        "-e", "--extend", help="Extend the existing schemas instead of replacing them"
    )
    parser.add_argument(
        "-v",
        "--version",
        help="Target Kubernetes schema version (e.g. 'v1.32.0' or just '1.32')",
    )
    args = parser.parse_args()

    validate_input(args)

    if version := args.version:
        if version_str := match(VERSION_REGEX, args.version):
            version = version_str.group(3)
    else:
        version_api = client.VersionApi()
        version_info = version_api.get_code()
        version = version_info.minor[:2]
        print(f"Detected version {version_info.major}.{version_info.minor}")

    all_file = args.output_dir / "all.json"
    definitions_file = args.output_dir / "_definitions.json"
    if args.extend:
        assert (
            all_file.exists() and definitions_file.exists()
        ), f"No pre-existing schemas available in {args.output_dir}. Run again without the --extend flag first."
    else:
        for item in args.output_dir.iterdir():
            if item.is_file() or item.is_symlink():
                item.unlink()
        print("Downloading built-in schemas")
        get_builtin_schemas(version, all_file, definitions_file)

    if args.crds:
        print("Downloading CRD schemas from the public catalog")
        get_crds_from_catalog(args.crds, args.output_dir)
    else:
        print("Generating CRD schemas from the cluster")
        get_crds_from_k8s(args.output_dir)
    write_index_file(all_file)
    print("Finished generating schemas")


if __name__ == "__main__":
    main()
