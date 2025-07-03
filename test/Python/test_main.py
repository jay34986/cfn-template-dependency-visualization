"""Unit tests for main.py CloudFormation template utilities."""

import io
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).parent.parent.parent / "src" / "cfntdv"))

from main import (
    build_dependency_graph,
    check_self_reference,
    collect_template_info,
    extract_exports_and_imports,
    find_cfn_templates,
    find_imports,
    generate_mermaid_text,
    parse_args,
)


def test_parse_args_default() -> None:
    """Test parse_args() with default arguments."""
    original_argv = sys.argv
    sys.argv = [sys.argv[0]]  # sys.argvを修正する
    try:
        args = parse_args()
        assert args.directory == "."  # noqa: S101
        assert args.output_file is None  # noqa: S101
        assert args.verbose is False  # noqa: S101
        assert args.direction == "LR"  # noqa: S101
    finally:
        sys.argv = original_argv  # sys.argvを元に戻す


def test_parse_args_custom() -> None:
    """Test parse_args() with custom arguments."""
    sys.argv = [
        "main.py",
        "-d",
        "/path/to/dir",
        "-o",
        "output.md",
        "-v",
        "-D",
        "BT",
    ]
    args = parse_args()
    assert args.directory == "/path/to/dir"  # noqa: S101
    assert args.output_file == "output.md"  # noqa: S101
    assert args.verbose is True  # noqa: S101
    assert args.direction == "BT"  # noqa: S101


def test_find_cfn_templates() -> None:
    """Test that find_cfn_templates finds CloudFormation template files (.yaml) in a directory."""  # noqa: E501
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "subdir").mkdir(parents=True)
        path1 = Path(tmpdir) / "a.yaml"
        Path(path1).open("w").close()
        found = find_cfn_templates(tmpdir)
        assert path1 in found  # noqa: S101


def create_yaml(path: str, content: dict) -> None:
    """Create a YAML file at the given path with the provided content."""
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.dump(content, f, allow_unicode=True)


def test_find_imports() -> None:
    """Test the find_imports function."""
    imports = set()
    obj = {
        "Fn::ImportValue": "MyExport",
        "Resources": {
            "MyRes": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": {"Fn::ImportValue": "MyExport"}},
            },
        },
    }
    find_imports(obj, imports)
    assert "MyExport" in imports  # noqa: S101


def test_extract_exports_and_imports_basic() -> None:
    """Test extracting exports and imports from a basic CloudFormation template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Export/Importのあるテンプレート
        path = Path(tmpdir) / "sample.yaml"
        content = {
            "Outputs": {"ExportedValue": {"Export": {"Name": "MyExport"}}},
            "Resources": {
                "MyRes": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": {"Fn::ImportValue": "MyExport"}},
                },
            },
        }
        create_yaml(path, content)
        result = extract_exports_and_imports(path)
        assert "MyExport" in result["exports"]  # noqa: S101
        assert "MyExport" in result["imports"]  # noqa: S101


def test_extract_exports_and_imports_no_outputs() -> None:
    """Test extracting exports and imports from a CloudFormation template with no Outputs section."""  # noqa: E501
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "noexport.yaml"
        content = {
            "Resources": {"MyRes": {"Type": "AWS::S3::Bucket", "Properties": {}}},
        }
        create_yaml(path, content)
        result = extract_exports_and_imports(path)
        assert result["exports"] == set()  # noqa: S101
        assert result["imports"] == set()  # noqa: S101


def test_extract_exports_and_imports_importvalue_list() -> None:
    """Test extracting exports and imports from a CloudFormation template with a list of Fn::ImportValue imports."""  # noqa: E501
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "list.yaml"
        content = {
            "Resources": {
                "MyRes": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "Tags": [
                            {"Fn::ImportValue": "TagExport1"},
                            {"Fn::ImportValue": "TagExport2"},
                        ],
                    },
                },
            },
        }
        create_yaml(path, content)
        result = extract_exports_and_imports(path)
        assert "TagExport1" in result["imports"]  # noqa: S101
        assert "TagExport2" in result["imports"]  # noqa: S101


def test_extract_exports_and_imports_dynamic_reference() -> None:
    """Test extracting dynamic references from a CloudFormation template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dynamic.yaml"
        content = {
            "Resources": {
                "MyRes": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketName": "{{resolve:ssm-secure:MyParam:1}}",
                        "Tags": [
                            {"Key": "foo", "Value": "{{resolve:ssm:TagParam:latest}}"},
                        ],
                    },
                },
            },
        }
        create_yaml(path, content)
        result = extract_exports_and_imports(path)
        assert "{{resolve:ssm-secure:MyParam:1}}" in result["dynamics"]  # noqa: S101
        assert "{{resolve:ssm:TagParam:latest}}" in result["dynamics"]  # noqa: S101


EXPECTED_TEMPLATE_COUNT = 2


def test_collect_template_info() -> None:
    """Test the collect_template_info function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample YAML files
        template1_path = Path(tmpdir) / "template1.yaml"
        template1_content = {"Outputs": {"Export1": {"Export": {"Name": "Export1"}}}}
        with template1_path.open("w") as f:
            yaml.dump(template1_content, f)

        template2_path = Path(tmpdir) / "template2.yaml"
        template2_content = {"Resources": {"MyRes": {"Type": "AWS::S3::Bucket"}}}
        with template2_path.open("w") as f:
            yaml.dump(template2_content, f)

        # Call collect_template_info
        templates = [str(template1_path), str(template2_path)]
        template_info = collect_template_info(templates)

        # Assert expected results
        assert isinstance(template_info, dict)  # noqa: S101
        assert len(template_info) == EXPECTED_TEMPLATE_COUNT  # noqa: S101
        for path, info in template_info.items():
            assert isinstance(path, str)  # noqa: S101
            assert isinstance(info, dict)  # noqa: S101
            assert "exports" in info  # noqa: S101
            assert "imports" in info  # noqa: S101


EXPECTED_NODE_COUNT = 2
EXPECTED_EDGE_COUNT = 2


def test_build_dependency_graph() -> None:
    """Test the build_dependency_graph function."""
    template_info = {
        "template1.yaml": {"exports": ["Export1"], "imports": []},
        "template2.yaml": {"exports": ["Export2"], "imports": ["Export1"]},
        "template3.yaml": {"exports": [], "imports": ["Export2"]},
    }
    nodes, edges = build_dependency_graph(template_info)
    assert isinstance(nodes, dict)  # noqa: S101
    assert len(nodes) == EXPECTED_NODE_COUNT  # noqa: S101
    assert "Export1" in nodes  # noqa: S101
    assert "Export2" in nodes  # noqa: S101
    assert isinstance(edges, list)  # noqa: S101
    assert len(edges) == EXPECTED_EDGE_COUNT  # noqa: S101
    assert (  # noqa: S101
        "template2.yaml",
        "template1.yaml",
        "Export1",
        "import",
    ) in edges
    assert (  # noqa: S101
        "template3.yaml",
        "template2.yaml",
        "Export2",
        "import",
    ) in edges


def test_check_self_reference() -> None:
    """Test the check_self_reference function."""
    template_info = {
        "template1.yaml": {"exports": ["Export1"], "imports": ["Export1"]},
        "template2.yaml": {"exports": ["Export2"], "imports": []},
    }
    captured_output = io.StringIO()
    sys.stderr = captured_output
    check_self_reference(template_info)
    sys.stderr = sys.__stderr__
    assert "WARNING" in captured_output.getvalue()  # noqa: S101
    assert "template1.yaml" in captured_output.getvalue()  # noqa: S101
    assert "Export1" in captured_output.getvalue()  # noqa: S101


def test_check_self_reference_no_warning() -> None:
    """Test the check_self_reference function with no self-reference."""
    template_info = {
        "template1.yaml": {"exports": ["Export1"], "imports": []},
        "template2.yaml": {"exports": ["Export2"], "imports": ["Export1"]},
    }
    captured_output = io.StringIO()
    sys.stdout = captured_output
    check_self_reference(template_info)
    sys.stdout = sys.__stdout__
    assert captured_output.getvalue() == ""  # noqa: S101


def test_generate_mermaid_text() -> None:
    """Test the generate_mermaid_text function."""
    edges = [
        ("template1.yaml", "template2.yaml", "Export1", "import"),
        ("template2.yaml", "template3.yaml", "Export2", "import"),
    ]
    captured_output = io.StringIO()
    sys.stdout = captured_output
    generate_mermaid_text(edges)
    sys.stdout = sys.__stdout__
    out = captured_output.getvalue()
    assert out.startswith("# CFn template dependency\n\n```mermaid")  # noqa: S101
    assert "graph LR" in out  # noqa: S101
    assert "template1.yaml-->|Export1|template2.yaml" in out  # noqa: S101
    assert "template2.yaml-->|Export2|template3.yaml" in out  # noqa: S101
    assert out.endswith("```\n\n")  # noqa: S101


def test_generate_mermaid_text_bt() -> None:
    """Test the generate_mermaid_text function with BT direction."""
    edges = [
        ("template1.yaml", "template2.yaml", "Export1", "import"),
        ("template2.yaml", "template3.yaml", "Export2", "import"),
    ]
    captured_output = io.StringIO()
    sys.stdout = captured_output
    generate_mermaid_text(edges, direction="BT")
    sys.stdout = sys.__stdout__
    assert "graph BT" in captured_output.getvalue()  # noqa: S101


def test_generate_mermaid_text_with_output_file() -> None:
    """Test the generate_mermaid_text function with an output file."""
    edges = [
        ("template1.yaml", "template2.yaml", "Export1", "import"),
        ("template2.yaml", "template3.yaml", "Export2", "import"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output.md"
        generate_mermaid_text(edges, output_file, direction="LR")
        assert output_file.exists()  # noqa: S101
        with output_file.open() as f:
            mermaid_text = f.read()
            assert mermaid_text.startswith("# CFn template dependency\n\n```mermaid")  # noqa: S101
            assert "graph LR" in mermaid_text  # noqa: S101
            assert "template1.yaml-->|Export1|template2.yaml" in mermaid_text  # noqa: S101
            assert "template2.yaml-->|Export2|template3.yaml" in mermaid_text  # noqa: S101
            assert mermaid_text.endswith("```\n")  # noqa: S101


def test_generate_mermaid_text_with_output_file_default_direction() -> None:
    """Test generate_mermaid_text writes 'graph LR' when direction is omitted and writing to a file."""  # noqa: E501
    edges = [
        ("template1.yaml", "template2.yaml", "Export1", "import"),
        ("template2.yaml", "template3.yaml", "Export2", "import"),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "output_default.md"
        generate_mermaid_text(edges, output_file)
        assert output_file.exists()  # noqa: S101
        with output_file.open() as f:
            mermaid_text = f.read()
            assert "graph LR" in mermaid_text  # noqa: S101


def test_build_dependency_graph_dynamic_reference() -> None:
    """Test build_dependency_graph includes dynamic reference edges."""
    template_info = {
        "dynamic.yaml": {
            "exports": [],
            "imports": [],
            "dynamics": [
                "{{resolve:ssm-secure:MyParam:1}}",
                "{{resolve:ssm:TagParam:latest}}",
            ],
        },
    }
    nodes, edges = build_dependency_graph(template_info)
    dynamic_edges = [e for e in edges if e[3] == "dynamic"]
    assert (  # noqa: S101
        "dynamic.yaml",
        "{{resolve:ssm-secure:MyParam:1}}",
        "{{resolve:ssm-secure:MyParam:1}}",
        "dynamic",
    ) in dynamic_edges
    assert (  # noqa: S101
        "dynamic.yaml",
        "{{resolve:ssm:TagParam:latest}}",
        "{{resolve:ssm:TagParam:latest}}",
        "dynamic",
    ) in dynamic_edges


def test_generate_mermaid_text_dynamic_reference() -> None:
    """Test generate_mermaid_text outputs cylindrical shape for dynamic references."""
    edges = [
        (
            "dynamic.yaml",
            "{{resolve:ssm-secure:MyParam:1}}",
            "{{resolve:ssm-secure:MyParam:1}}",
            "dynamic",
        ),
        (
            "dynamic.yaml",
            "{{resolve:ssm:TagParam:latest}}",
            "{{resolve:ssm:TagParam:latest}}",
            "dynamic",
        ),
    ]
    captured_output = io.StringIO()
    sys.stdout = captured_output
    generate_mermaid_text(edges)
    sys.stdout = sys.__stdout__
    out = captured_output.getvalue()
    assert "dynamic.yaml-->|ssm-secure|MyParam:1[(MyParam:1)]" in out  # noqa: S101
    assert "dynamic.yaml-->|ssm|TagParam:latest[(TagParam:latest)]" in out  # noqa: S101
