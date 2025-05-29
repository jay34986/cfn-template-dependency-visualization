"""A tool to visualize CloudFormation template dependencies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cfn_flip import to_json
from colorama import Fore, Style, init

# Colorama Initialization
init(autoreset=True)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CloudFormation template dependency visualization tool",
        prog=None,
    )
    parser.add_argument(
        "-d",
        "--directory",
        default=".",
        help="Directory to search for CFn templates (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        default=None,
        help="File name to save the output to (e.g. result.md). \
            If not specified, only standard output will be used.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Output detailed logs",
    )
    return parser.parse_args(args=sys.argv[1:])


def find_cfn_templates(directory: str) -> list[str]:
    """Find all CloudFormation template files (.yaml, .yml) in the specified directory recursively."""  # noqa: E501
    target_dir = Path(directory)
    return list(target_dir.glob("*.yml")) + list(target_dir.glob("*.yaml"))


def find_imports(obj: dict[str, any] | list[any], imports: set[str]) -> None:
    """Recursively find all Fn::ImportValue references in the given object."""
    target_key = "Fn::ImportValue"
    if isinstance(obj, dict):  # In the case of dictionary type
        for key, value in obj.items():
            if key == target_key:
                imports.add(value)
            find_imports(value, imports)  # Recursive Search
    elif isinstance(obj, list):  # In the case of list type
        for item in obj:
            find_imports(item, imports)


def extract_exports_and_imports(filepath: str) -> dict:
    """Extract exported and imported values from a CloudFormation template file."""
    with Path(filepath).open(encoding="utf-8") as f:
        try:
            data = to_json(f.read(), clean_up=True)  # Convert YAML to JSON
        except json.decoder.JSONDecodeError as e:
            print(  # noqa: T201
                Fore.RED
                + Style.BRIGHT
                + f"[ERROR] Failed to parse YAML in {filepath} : {e}",
            )
            sys.exit(1)
    exports = set()
    imports = set()

    # Convert JSON to Python dictionary
    parsed_data = json.loads(data)

    # Extract Export Name from Outputs section
    key_to_find = "Outputs"
    if key_to_find in parsed_data:
        outputs = parsed_data.get(key_to_find)

        for v in outputs.values():
            export = v.get("Export", {}).get("Name")
            if export:
                exports.add(export)

    # Fn::ImportValue reference extraction
    find_imports(parsed_data, imports)
    return {"exports": exports, "imports": imports}


def collect_template_info(templates: list[str], *, verbose: bool = False) -> dict:
    """Collect export/import info from each template."""
    template_info = {}
    if verbose:
        print(f"Exploration Templates: {templates}")  # noqa: T201
    for path in templates:
        info = extract_exports_and_imports(path)
        template_info[path] = info
    return template_info


def build_dependency_graph(template_info: dict) -> tuple[dict, list]:
    """Build dependency graph nodes and edges."""
    nodes = {}
    for path, info in template_info.items():
        for export in info["exports"]:
            nodes[export] = path
    edges = []
    for path, info in template_info.items():
        for imp in info["imports"]:
            if imp in nodes:
                edges.append((path, nodes[imp], imp))
            else:
                edges.append((path, "(unknown)", imp))
    return nodes, edges


def check_self_reference(template_info: dict) -> None:
    """Warn if a template imports its own export."""
    for path, info in template_info.items():
        for imp in info["imports"]:
            if imp in info["exports"]:
                print(  # noqa: T201
                    Fore.YELLOW
                    + Style.BRIGHT
                    + f"[WARNING] {path} references its own Cfn template's Export({imp}) using Fn::ImportValue or !ImportValue.",  # noqa: E501
                    file=sys.stderr,
                )


def generate_mermaid_text(edges: list, output_file: str | None = None) -> None:
    """Generate and output Mermaid diagram text."""
    mermaid_lines = ["# CFn template dependency\n\n```mermaid", "graph BT"]
    for src, dst, imp in edges:
        mermaid_lines.append(f"    {Path(src).name}-->|{imp}|{Path(dst).name}")
    mermaid_lines.append("```\n")
    mermaid_text = "\n".join(mermaid_lines)
    if output_file:
        with Path(output_file).open("w", encoding="utf-8") as f:
            f.write(mermaid_text)
        print(f"Mermaid notation has been output to {output_file}.")  # noqa: T201
    else:
        print(mermaid_text)  # noqa: T201


def main() -> None:
    """Run the CloudFormation dependency visualization tool."""
    args = parse_args()
    templates = find_cfn_templates(args.directory)
    template_info = collect_template_info(templates, verbose=args.verbose)
    _, edges = build_dependency_graph(template_info)
    check_self_reference(template_info)
    generate_mermaid_text(edges, args.output_file)


if __name__ == "__main__":
    main()
