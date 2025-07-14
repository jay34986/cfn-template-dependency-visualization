"""A tool to visualize CloudFormation template dependencies."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

from cfn_flip import to_json
from colorama import Fore, Style, init

# Shared regex patterns
DYNAMIC_REF_PATTERN = re.compile(r"\{\{resolve:.*?}}")
# Also supports secretsmanager:${MySecret}:SecretString:username
DYN_NODE_PATTERN = re.compile(r"\{\{resolve:(ssm|ssm-secure|secretsmanager):(.+?)}}")


def normalize_dynamic_node(node: str) -> str:
    """Convert ${Var} to $Var for Mermaid node names."""
    # Replace all ${Var} with $Var, including nested and multiple variables
    # This also supports cases like ${MySecret}:SecretString:${username}
    # Example: converts a dynamic reference with variables to normalized form
    #   -> '$MySecret:SecretString:$username'
    # Remove any remaining '{' or '}' that are not part of the dynamic reference
    normalized = re.sub(r"\$\{([A-Za-z0-9_]+)\}", r"$\1", node)
    # Remove any unmatched '{' or '}' (e.g. from broken parsing)
    return normalized.replace("{", "").replace("}", "")


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
    parser.add_argument(
        "-D",
        "--direction",
        default="LR",
        choices=["LR", "BT"],
        help=(
            "Direction of Mermaid diagram (LR: Left to right, BT: Bottom to top). "
            "Default: LR"
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Show program version and exit",
    )
    return parser.parse_args(args=sys.argv[1:])


PACKAGE_NAME = "cfn-template-dependency-visualization"


def print_version_and_exit() -> None:
    """Print the package version and exit."""
    try:
        pkg_version = importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        pkg_version = "unknown"
    sys.stdout.write(f"{PACKAGE_NAME} {pkg_version}\n")
    sys.exit(0)


def find_cfn_templates(directory: str) -> list[str]:
    """Find all CloudFormation template files (.yaml, .yml) in the specified directory recursively."""  # noqa: E501
    target_dir = Path(directory)
    return list(target_dir.glob("*.yml")) + list(target_dir.glob("*.yaml"))


def find_imports(obj: dict[str, Any] | list[Any], imports: set[str]) -> None:
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


def find_dynamic_references(obj: object, dynamics: set[str]) -> None:
    """Recursively find all dynamic references ({{resolve:...}}) in the given object.

    AWS: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
    """
    if isinstance(obj, dict):
        for value in obj.values():
            find_dynamic_references(value, dynamics)
    elif isinstance(obj, list):
        for item in obj:
            find_dynamic_references(item, dynamics)
    elif isinstance(obj, str):
        for match in DYNAMIC_REF_PATTERN.findall(obj):
            dynamics.add(match)


def extract_exports_and_imports(filepath: str) -> dict:
    """Extract dependencies from a CloudFormation template file.

    Extract exported, imported values, and dynamic references from a CloudFormation
    template file.
    Returns a dict with keys 'exports', 'imports', and 'dynamics'.
    """
    with Path(filepath).open(encoding="utf-8") as f:
        try:
            data = to_json(f.read(), clean_up=True)  # Convert YAML to JSON
        except json.JSONDecodeError as e:
            print(  # noqa: T201
                Fore.RED
                + Style.BRIGHT
                + f"[ERROR] Failed to parse YAML in {filepath} : {e}",
                file=sys.stderr,
            )
            sys.exit(1)
    exports = set()
    imports = set()
    dynamics = set()

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
    # Dynamic reference extraction
    find_dynamic_references(parsed_data, dynamics)
    return {"exports": exports, "imports": imports, "dynamics": dynamics}


def collect_template_info(templates: list[str], *, verbose: bool = False) -> dict:
    """Collect export/import/dynamic info from each template."""
    template_info = {}
    if verbose:
        print(f"Exploration Templates: {templates}")  # noqa: T201
    for path in templates:
        info = extract_exports_and_imports(path)
        template_info[path] = info
    return template_info


def build_dependency_graph(template_info: dict) -> tuple[dict, list]:
    """Build dependency graph nodes and edges (including dynamic references)."""
    nodes = {}
    for path, info in template_info.items():
        for export in info["exports"]:
            nodes[export] = path
    edges = []
    for path, info in template_info.items():
        for imp in info["imports"]:
            if imp in nodes:
                edges.append((path, nodes[imp], imp, "import"))
            else:
                edges.append((path, "(unknown)", imp, "import"))
        # Since the dynamic reference is an external resource reference,
        # dst is the dynamic reference name itself.
        # AWS: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
        edges.extend((path, dyn, dyn, "dynamic") for dyn in info.get("dynamics", set()))
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


def generate_mermaid_text(
    edges: list,
    output_file: str | Path | None = None,
    direction: str = "LR",
) -> None:
    """Generate and output Mermaid diagram text.

    Dynamic references are output in cylindrical form.
    AWS: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/dynamic-references.html
    Mermaid: https://mermaid.js.org/syntax/flowchart.html#cylindrical-shape
    """
    mermaid_lines = ["# CFn template dependency\n\n```mermaid", f"graph {direction}"]
    edge_lines = []
    for src, dst, imp, typ in edges:
        src_name = Path(src).name if src not in ("(unknown)",) else src
        if typ == "dynamic":
            # Try to extract service and parameter part from dynamic reference
            m = DYN_NODE_PATTERN.fullmatch(imp)
            if m:
                label = m.group(1)
                node = normalize_dynamic_node(m.group(2))
            else:
                # Try to match more complex patterns for dynamic references
                dyn_match = re.fullmatch(
                    r"\{\{resolve:(ssm|ssm-secure|secretsmanager):(.+?)}}",
                    imp,
                )
                if dyn_match:
                    label = dyn_match.group(1)
                    node = normalize_dynamic_node(dyn_match.group(2))
                else:
                    label = "dynamic"
                    node = normalize_dynamic_node(imp)
            edge_lines.append(f"    {src_name}-->|{label}|{node}[({node})]")
        else:
            dst_name = Path(dst).name if dst not in ("(unknown)",) else dst
            edge_lines.append(f"    {src_name}-->|{imp}|{dst_name}")
    edge_lines.sort()
    mermaid_lines.extend(edge_lines)
    mermaid_lines.append("```\n")
    mermaid_text = "\n".join(mermaid_lines)
    if output_file:
        try:
            with Path(output_file).open("w", encoding="utf-8") as f:
                f.write(mermaid_text)
        except IsADirectoryError:
            print(  # noqa: T201
                Fore.RED + Style.BRIGHT + f"[ERROR] Is a directory: {output_file}",
                file=sys.stderr,
            )
            sys.exit(2)
        except FileNotFoundError:
            print(  # noqa: T201
                Fore.RED
                + Style.BRIGHT
                + f"[ERROR] Output directory not found: {output_file}",
                file=sys.stderr,
            )
            sys.exit(3)
        except PermissionError:
            print(  # noqa: T201
                Fore.RED
                + Style.BRIGHT
                + f"[ERROR] Permission denied when writing to: {output_file}",
                file=sys.stderr,
            )
            sys.exit(4)
        print(f"Mermaid notation has been output to {output_file}.")  # noqa: T201
    else:
        print(mermaid_text)  # noqa: T201


def main() -> None:
    """Run the CloudFormation dependency visualization tool."""
    args = parse_args()
    if getattr(args, "version", False):
        print_version_and_exit()
    templates = find_cfn_templates(args.directory)
    template_info = collect_template_info(templates, verbose=args.verbose)
    _, edges = build_dependency_graph(template_info)
    check_self_reference(template_info)
    generate_mermaid_text(edges, args.output_file, direction=args.direction)


if __name__ == "__main__":
    main()
