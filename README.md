# AWS CloudFormation Template Dependency Visualization

It parses Export and ImportValue from YAML formatted CFn template files and outputs dependencies in Mermaid format.

## Install

Python 3.12+ is supported.

Install it using pipx.

```bash
pipx install git+https://github.com/jay34986/cfn-template-dependency-visualization.git
```

## Basic Usage

If you run the cfn-tdv command without any arguments, it analyzes files with .yaml and .yml extensions in the current directory.  
The analysis results are output to standard output in Mermaid format as shown below.  
The following example shows that s3import.yaml references MyBucketExportName, which is exported in s3export.yaml.  

```mermaid
graph BT
    s3import.yaml-->|MyBucketExportName|s3export.yaml
```

Use the -d option to specify the directory where the CFn templates are saved.  

```bash
cfn-tdv -d examples/yaml/
```

To output the analysis results to a file, specify the -o option.  

```bash
cfn-tdv -o result.md
```

## Detecting self-references

If an ImportValue circularly references an Export within its own CFn template, a WARNING is issued.  
If there are multiple circular references, multiple WARNING will be printed.  
However, a Mermaid diagram can only represent one circular reference per CFn template.  
In the example below, there are two warnings about circular references in vpc.yml,
but the Mermaid diagram only has one line drawn from vpc.yml to vpc.yml.  

```text
cfn-tdv -d examples/yml
[WARNING] examples/yml/vpc.yml references its own Cfn template's Export(VpcStackSecurityGroup) using Fn::ImportValue or !ImportValue.
[WARNING] examples/yml/vpc.yml references its own Cfn template's Export(VpcStackPublicSubnet) using Fn::ImportValue or !ImportValue.
```

```mermaid
graph BT
    vpc.yml-->|VpcStackSecurityGroup|vpc.yml
    vpc.yml-->|VpcStackPublicSubnet|vpc.yml
    instanceprofile.yml-->|ArnS3Bucket|s3.yml
    ec2.yml-->|VpcStackSecurityGroup|vpc.yml
    ec2.yml-->|VpcStackPublicSubnet|vpc.yml
    ec2.yml-->|InstanceProfileName|instanceprofile.yml
```
