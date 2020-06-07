#!/usr/bin/env python3
#
# Copyright (c) 2020 Fabrice Triboix

import boto3
import botocore
import datetime
import time
import json
import requests


def handler(event, context):
    """
    Create, update or delete and ACM certificate. This Lambda function
    implements a backend for a CloudFormation custom resource to create an ACM
    certificate. The main problem with the
    `AWS::CertificateManager::Certificate` official resource is that the
    validation step is manual, even if you choose DNS validation and your DNS
    is managed by Route53. This custom resource allows you to create an ACM
    certificate in an entirely automated way when your DNS is managed by
    Route53.

    Please refer to the README file to know what properties to add to the
    custom resource in your CloudFormation template.
    """
    try:
        arn = handle_request(event)
        print(f"Success: {data}")
        send_response(event, True, "Success", arn)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        send_response(event, False, str(e), "")


def handle_request(event)
    request_type = event['RequestType']
    if request_type == "Create":
        arn = create_cert(event)
    elif request_type == "Update":
        arn = update_cert(event)
    elif request_type == "Delete":
        arn = delete_cert(event)
    else:
        raise ValueError(f"Invalid request type: {request_type}")
    return arn


def create_cert(event):
    print(f"Creating certificate")
    acm = boto3.client('acm')
    route53 = boto3.client('route53')

    # Request the certificate with DNS validation

    unique_token = event['StackId'] + event['RequestId']
    args = event['ResourceProperties']
    options = { 'CertificateTransparencyLoggingPreference': "DISABLED" }
    if 'Options' in args and 'CertificateTransparencyLoggingPreference' in args['Options']:
        options['CertificateTransparencyLoggingPreference'] = args['Options']['CertificateTransparencyLoggingPreference']
    tags = []
    if 'CertificateTags' in args:
        for tag in args['CertificateTags']:
            tags.append(tag)

    print(f"Sending certificate creation request to ACM for \"args['DomainName']\"")
    response = acm.request_certificate(
        DomainName=args['DomainName']
        ValidationMethod="DNS",
        SubjectAlternativeNames=args.get('SubjectAlternativeNames', []),
        IdempotencyToken=unique_token,  # Handle retries from CloudFormation
        Options=options,
        Tags=tags
    )
    arn = response['CertificateArn']
    print(f"Certificate creation successfully requested; certificate ARN: {arn}")

    # Get the CNAME record that needs to be created

    response = acm.describe_certificate(CertificateArn=arn)
    tmp = response['Certificate']['DomainValidationOptions']
    if tmp['ValidationMethod'] != "DNS":
        raise ValueError(f"Certificate unexpectedly changed its validation method from \"DNS\" to \"{tmp['ValidationMethod']}\"")
    if tmp['ValidationStatus'] != "PENDING_VALIDATION":
        raise ValueError(f"Certificate status is \"{tmp['ValidationStatus']}\", expected \"PENDING_VALIDATION\"")
    if tmp['ResourceRecord']['Type'] != "CNAME":
        raise ValueError(f"Unexpected DNS resource record type: \"{tmp['ResourceRecord']['Type']}\"")
    rr_name = tmp['ResourceRecord']['Name']
    rr_value = tmp['ResourceRecord']['Value']

    # Create the CNAME record

    print(f'Creating resource record: name="{rr_name}", value="{rr_value}"')
    route53.change_resource_record_sets(
        HostedZoneId=args['HostedZoneId'],
        ChangeBatch={
            'Changes': [
                {
                    'Action': "UPSERT",
                    'ResourceRecordSet': {
                        'Name': rr_name,
                        'Type': "CNAME",
                        'TTL': 60,
                        'ResourceRecords': [{'Value': rr_value}]
                    }
                }
            ]
        }
    )

    # Wait for the certficate to be validated

    timeout = int(args.get('Timeout', 300))
    start = datetime.datetime.utcnow()
    validated = False
    while not validated:
        time.sleep(15)
        response = acm.describe_certificate(CertificateArn=arn)
        tmp = response['Certificate']['DomainValidationOptions']
        if tmp['ValidationMethod'] != "DNS":
            raise ValueError(f"Certificate unexpectedly changed its validation method from \"DNS\" to \"{tmp['ValidationMethod']}\"")
        if tmp['ValidationStatus'] == "SUCCESS":
            validated = True
            print(f"Certficate successfully validated")
        else:
            elapsed = datetime.datetime.utcnow() - start
            elapsed_seconds = elapsed.seconds
            if elapsed_seconds >= timeout:
                raise ValueError(f"Timeout waiting for the certificate to be validated")
            remaining = timeout - elapsed_seconds
            print(f"Waiting for certificate to be validated; timeout in {remaining} seconds")

    # Cleanup Route53

    print(f"Cleaning up Route53")
    route53.change_resource_record_sets(
        HostedZoneId=args['HostedZoneId'],
        ChangeBatch={
            'Changes': [
                {
                    'Action': "DELETE",
                    'ResourceRecordSet': {
                        'Name': rr_name,
                        'Type': "CNAME",
                        'ResourceRecords': [{'Value': rr_value}]
                    }
                }
            ]
        }
    )

    print(f"Successfully created and validated certificate for: {args['DomainName']}; certificate ARN: {arn}")
    return arn


def update_cert(event):
    acm = boto3.client('acm')
    arn = event['PhysicalResourceId']
    old_args = event['OldResourceProperties']
    args = event['ResourceProperties']

    # Check for invalid changes
    if args['DomainName'] != old_args['DomainName']:
        raise ValueError(f"Updating the domain name is not allowed")
    if args['HostedZoneId'] != old_args['HostedZoneId']:
        raise ValueError(f"Updating the hosted zone ID is not allowed")
    san = args.get('SubjectAlternativeNames', [])
    old_san = old_args.get('SubjectAlternativeNames', [])
    if set(san) != set(old_san):
        raise ValueError(f"Updating the subject alternative names is not allowed")

    # Update certificate options if required
    transparency = args.get(
        'Options', {'CertificateTransparencyLoggingPreference': "DISABLED"}
    ).get(
        'CertificateTransparencyLoggingPreference', "DISABLED"
    )
    old_transparency = old_args.get(
        'Options', {'CertificateTransparencyLoggingPreference': "DISABLED"}
    ).get(
        'CertificateTransparencyLoggingPreference', "DISABLED"
    )
    if transparency != old_transparency:
        print(f"Update certificate transparency logging preference: {old_transparency} -> {transparency}")
        acm.update_certificate_options(
            CertificateArn=arn, 
            Options={
                'CertificateTransparencyLoggingPreference': transparency
            }
        )

    # Update certificate tags if required
    tags = args.get('CertificateTags', [])
    old_tags = old_args.get('CertificateTags', [])
    if set(tags) != set(old_tags):
        print(f"Update certificate tags")
        response = acm.list_tags_for_certificate(CertificateArn=arn)
        acm.remove_tags_from_certificate(CertificateArn=arn, Tags=response['Tags'])
        acm.add_tags_to_certificate(CertificateArn=arn, Tags=tags)

    print(f"Successfully updated certificate {arn}")
    return arn


def delete_cert(event):
    acm = boto3.client('acm')
    arn = event['PhysicalResourceId']
    acm.delete_certificate(CertificateArn=arn)
    return arn


def send_response(event, success, msg, arn):
    response = {
        'Status': "SUCCESS" if success else "FAILED",
        'Reason': msg,
        'PhysicalResourceId': arn,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId']
    }
    data = json.dumps(response)
    headers = {
        'Content-Type': ""
    }
    requests.put(event['ResponseURL'], headers=headers, data=data)
