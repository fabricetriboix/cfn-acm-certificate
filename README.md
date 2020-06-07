cfn-acm-certificate
===================

CloudFormation custom resource to create an ACM certificate and
automatically validate it using DNS. Your DNS must be managed by
Route53.

How to install the Lambda function?
===================================

Create an IAM policy using the `acm-certificate-policy.json` file.
Then create an IAM role for the Lambda function using this policy;
name this role `acm-certificate-lambda-role`.

Then run the following commands in a bash shell, where "123456789012"
is your AWS account ID, and `YOUR_PROFILE` the AWS profile you
configured for your awscli:

$ ./package.sh
$ aws --profile YOUR_PROFILE lambda create-function \
    --function-name acm-certificate --memory 128 --timeout 300 \
    --role arn:aws:iam::123456789012:role/acm-certificate-lambda-role \
    --runtime python3.7 --zip-file fileb://./acm-certificate.zip \
    --handler acm-certificate.handler

How to use the custom resource?
===============================

Your CloudFormation template should look like that:

    MyCertificate:
      Type: Custom::Certificate
      Properties:
        ServiceToken: !Ref AcmCertificateLambdaArn
        DomainName: test.mycompany.com
        HostedZoneId: ABCXYZ
        Timeout: 300
        SubjectAlternativeNames:
          - test-api.mycompany.com
          - test-admin.mycompany.com
        Options:
          CertificateTransparencyLoggingPreference: ENABLED
        CertificateTags:
          - Key: Name
            Value: value
          - Key: Name
            Value: value

Mandatory parameters:
 - `ServiceToken` is the ARN of the Lambda function implementing the
   ACM certificate backend
 - `DomainName` is the main domain name of the certificate; wildcard
   certificates are allowed; must be the same domain as managed by the
   hosted zone identified in the next parameter, or a subdomain of it
 - `HostedZoneId`: ID of the Route53 hosted zone

Optional parameters:
 - `Timeout`: Timeout in seconds waiting for the certificate to be
   validated after the Route53 CNAME has been created; default is 300
   (five minutes)
 - `SubjectAlternativeNames` is a list of domain names to include in
   the certificate
 - `Options` are ACM options (currently consisting of only one option
   which is about logging for certificate transparency), which has two
   allowed values: `ENABLED` and `DISABLED
 - `CertificateTags` are tags that will be added to the created ACM
   certificate

**IMPORTANT NOTE**: Once created, the only parameters you can change
are `Timeout` (although modifying this would do nothing), `Options`
and `Tags`. Attempting to modify any other parameter would result in
the stack update operation to fail. If you do need to perform such
modifications on the certificate, you will need to remove it (or
comment it out) of your CloudFormation template, update the stack and
the to re-create it with the modified parameters.
