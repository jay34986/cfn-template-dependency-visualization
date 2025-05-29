# CFn template dependency

```mermaid
graph BT
    vpc.yml-->|VpcStackSecurityGroup|vpc.yml
    vpc.yml-->|VpcStackPublicSubnet|vpc.yml
    instanceprofile.yml-->|ArnS3Bucket|s3.yml
    ec2.yml-->|VpcStackSecurityGroup|vpc.yml
    ec2.yml-->|VpcStackPublicSubnet|vpc.yml
    ec2.yml-->|InstanceProfileName|instanceprofile.yml
```
