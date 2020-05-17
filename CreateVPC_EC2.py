#!/usr/bin/env python3
import os
import sys
import boto3
# Importing "operator" for implementing itemgetter 
from operator import itemgetter
# The operator module exports a set of efficient functions corresponding to the intrinsic operators of Python.
# For example, operator.add(x, y) is equivalent to the expression x+y.

# Variables defination
aws_region = "sa-east-1"
aws_az1 = "sa-east-1c"
vpc_cidr = "10.40.0.0/16"
subnet_cidr = "10.40.1.0/24"
source_cidr = '0.0.0.0/0'

ec2_resource = boto3.resource('ec2', aws_region)
ec2_client = boto3.client('ec2', aws_region)

# Create VPC
vpc = ec2_resource.create_vpc(CidrBlock=vpc_cidr)
vpc.create_tags(Tags=[{"Key": "Name", "Value": "VPC_PROD"}])
vpc.wait_until_available()
print('\033[1;33m VPC CREATED SUCCESSFULLY WITH VPC ID: \033[0;0m' + vpc.id)

# Enable public DNS Hostname so that we can SSH into it later
vpc.modify_attribute(EnableDnsHostnames={'Value':True})
vpc.modify_attribute(EnableDnsSupport={'Value':True})

# Create an Internet Gateway and attach it to VPC
internet_gateway = ec2_resource.create_internet_gateway()
internet_gateway.create_tags(Tags=[{"Key": "Name", "Value": "IGW-SAM-PROD"}])
internet_gateway.attach_to_vpc(VpcId=vpc.id)
print('\033[1;35;40m INTERNET GATEWAY CREATED SUCCESSFULLY WITH GATEWAY ID: \033[0;0m' + internet_gateway.id)

# Create Subnet
subnet = vpc.create_subnet(AvailabilityZone=aws_az1,CidrBlock=subnet_cidr)
subnet.create_tags(Tags=[{"Key": "Name", "Value": "PROD_SUBNET40"}])
print('\033[1;36;40m SUBNET CREATED SUCCESSFULLY WITH SUBNET ID: \033[0;0m' + subnet.id)

# Create a route table and associate to subnet PROD_SUBNET40
route_table = ec2_resource.create_route_table(VpcId=vpc.id)
route_table.associate_with_subnet(SubnetId=subnet.id)
route_table.create_tags(Tags=[{"Key": "Name", "Value": "RT-SAM-PROD"}])
# Create route to Internet Gateway in public route table
public_route = ec2_client.create_route(RouteTableId=route_table.id,DestinationCidrBlock=source_cidr,GatewayId=internet_gateway.id)
print('\033[1;37;40m PUBLIC ROUTE TABLE WITH ID CREATED SUCCESSFULLY. \033[0;0m' + route_table.id)

# Create a security group
security_group = ec2_resource.create_security_group(GroupName='SG-SAM-PROD',Description='Used by PROD Env',VpcId= vpc.id)
security_group.create_tags(Tags=[{"Key": "Name", "Value": "SG-SAM-PROD"}])
# Create ssh and ICMP ingress rules
ec2_client.authorize_security_group_ingress(GroupId=security_group.id,IpProtocol='tcp',FromPort=22,ToPort=22,CidrIp=source_cidr)
ec2_client.authorize_security_group_ingress(GroupId=security_group.id,IpProtocol='icmp',FromPort=-1,ToPort=-1,CidrIp=source_cidr)
print('\033[1;31;40m SECURITY GROUP WITH ID CREATED SUCCESSFULLY. \033[0;0m' + security_group.id)

# Find the latest AMI ID for Amazon Linux 2
ec2_ami_ids = ec2_client.describe_images(
    Filters=[{'Name':'name','Values':['amzn2-ami-hvm-2.0.????????-x86_64-gp2']},{'Name':'state','Values':['available']}],
    Owners=['amazon']
)

# Using sorted and itemgetter to print list sorted by "CreationDate" in descending order
image_details = sorted(ec2_ami_ids['Images'],key=itemgetter('CreationDate'),reverse=True)
ec2_ami_id = image_details[0]['ImageId']

# Create a SSH key pair
outfile = open('PROD.pem','w')
keypair = ec2_client.create_key_pair(KeyName='PROD_Key')
keyval = keypair['KeyMaterial']
outfile.write(keyval)
outfile.close()
os.chmod('PROD.pem', 400)
print(' KEY PAIR "PROD_KEY" CREATED SUCCESSFULLY.')

# Create an ec2 instance
ec2_instance = ec2_resource.create_instances(
    ImageId=ec2_ami_id, InstanceType='t2.micro', KeyName='PROD_Key', MaxCount=1, MinCount=1,
    NetworkInterfaces=[{'SubnetId': subnet.id, 'DeviceIndex': 0, 'AssociatePublicIpAddress': True, 'Groups': [security_group.id]}])

ec2_instance_id = ec2_instance[0].id
create_tag = ec2_client.create_tags(Resources=[ec2_instance_id], Tags=[{'Key': 'Name','Value': 'PRODInst'}])

print('\033[1;30;40m CREATING EC2 INSTANCE...... \033[0;0m')
 
# Wait until the EC2 is running
waiter = ec2_client.get_waiter('instance_running')
waiter.wait(InstanceIds=[ec2_instance_id])
print(' EC2 INSTANCE CREATED SUCCESSFULLY WITH ID:' + ec2_instance_id)

# Print Instance FQDN
ec2_instance = ec2_client.describe_instances(
    Filters=[{'Name': 'tag:Name','Values': ['PRODInst']},
    {'Name': 'instance-state-name','Values': ['running']}]
)
ec2_public_dns_name = ec2_instance["Reservations"][0]["Instances"][0]["PublicDnsName"]
print(' Login to EC2 Instance using ssh -i PROD.pem ec2-user@' + ec2_public_dns_name)