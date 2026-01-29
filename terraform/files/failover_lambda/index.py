"""
Asterisk EIP Failover Lambda Function
"""

import os
import json
import boto3
from datetime import datetime

ec2 = boto3.client('ec2')
sns = boto3.client('sns')

EIP_ALLOCATION_ID = os.environ['EIP_ALLOCATION_ID']
PRIMARY_INSTANCE_ID = os.environ['PRIMARY_INSTANCE_ID']
STANDBY_INSTANCE_ID = os.environ['STANDBY_INSTANCE_ID']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']


def handler(event, context):
    print(f"Failover event received: {json.dumps(event)}")

    try:
        eip_info = ec2.describe_addresses(AllocationIds=[EIP_ALLOCATION_ID])
        addresses = eip_info.get('Addresses', [])

        if not addresses:
            raise Exception(f"EIP {EIP_ALLOCATION_ID} not found")

        current_instance = addresses[0].get('InstanceId')
        association_id = addresses[0].get('AssociationId')
        public_ip = addresses[0].get('PublicIp')

        print(f"Current EIP {public_ip} attached to: {current_instance}")

        if current_instance == PRIMARY_INSTANCE_ID:
            target_instance = STANDBY_INSTANCE_ID
            source_name, target_name = "Primary", "Standby"
        elif current_instance == STANDBY_INSTANCE_ID:
            target_instance = PRIMARY_INSTANCE_ID
            source_name, target_name = "Standby", "Primary"
        else:
            target_instance = STANDBY_INSTANCE_ID
            source_name, target_name = "Unknown", "Standby"

        target_status = get_instance_status(target_instance)
        if target_status != 'running':
            raise Exception(f"Target instance {target_instance} is not running (status: {target_status})")

        if association_id:
            print(f"Disassociating EIP from {current_instance}")
            ec2.disassociate_address(AssociationId=association_id)

        print(f"Associating EIP with {target_instance}")
        ec2.associate_address(
            AllocationId=EIP_ALLOCATION_ID,
            InstanceId=target_instance,
            AllowReassociation=True
        )

        message = {
            'event': 'FAILOVER_COMPLETE',
            'timestamp': datetime.utcnow().isoformat(),
            'eip': public_ip,
            'from_instance': current_instance,
            'from_name': source_name,
            'to_instance': target_instance,
            'to_name': target_name
        }

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='[ASTERISK] EIP Failover Completed',
            Message=json.dumps(message, indent=2)
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'EIP {public_ip} reassigned from {source_name} to {target_name}',
                'from': current_instance,
                'to': target_instance
            })
        }

    except Exception as e:
        error_message = str(e)
        print(f"Failover error: {error_message}")

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='[ASTERISK] EIP Failover FAILED',
            Message=f'Failover failed: {error_message}'
        )
        raise


def get_instance_status(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get('Reservations', [])
    if not reservations:
        return 'not_found'
    instances = reservations[0].get('Instances', [])
    if not instances:
        return 'not_found'
    return instances[0].get('State', {}).get('Name', 'unknown')
