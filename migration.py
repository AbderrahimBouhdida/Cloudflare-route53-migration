import boto3
import CloudFlare
import json
import yaml
import time
with open('cred.yml') as creds:
    cred = yaml.load(creds, Loader=yaml.FullLoader)
# aws
print(cred)
timestamp = time.strftime('%m-%d-%Y.%I_%M_%S_%p')
print(timestamp)
client = boto3.client(
    'route53',
    aws_access_key_id=cred["aws"]["access_key"],
    aws_secret_access_key=cred["aws"]["secret_key"],
    aws_session_token=cred["aws"]["session_token"],
    region_name="eu-west-1",
)
# cloudflare
cf = CloudFlare.CloudFlare(cred["cloudflare"]["mail"], cred["cloudflare"]["api_key"])

zones = cf.zones.get(params={'per_page': 4})

#exmaple: DelegationSetId='/delegationset/N03196XXXXXXXXXXXX'
DelegationSetId='change this'
for cfZone in zones:
    zone=cfZone['name']
    tag='change tag'

    # check if zone exists in route53
    response = client.list_hosted_zones_by_name(DNSName=zone)
    if ('HostedZones' in response.keys()
        and len(response['HostedZones']) > 0
        and response['HostedZones'][0]['Name'].startswith(zone)):
        # already existing zone
        print("found zone : ")
        print(json.dumps(response['HostedZones'], indent=4))
    else:
        # zone doesn't exist
        # create the new zone
        print("Creating new zone : {} ".format(zone))
        response = client.create_hosted_zone(
            Name=zone,
            CallerReference=cfZone['id']+timestamp,
            HostedZoneConfig={
                'Comment': 'comment',
                'PrivateZone': False
            },
            DelegationSetId=DelegationSetId
        )
        print(response)
        # get zone ID
        zoneId = response['HostedZone']['Id'].split('/')[2]
        # adding tags
        response = client.change_tags_for_resource(
            ResourceType='hostedzone',
            ResourceId=zoneId,
            AddTags=[
                {
                    'Key': 'key',
                    'Value': tag
                },
            ]
        )
        # listing tags
        response = client.list_tags_for_resource(
            ResourceType='hostedzone',
            ResourceId=zoneId
        )
        print(response)
        # get dns records for the current zone
        mx = dict()
        txts=""
        dns_records = cf.zones.dns_records.get(cfZone['id'])
        for cf_record in dns_records:
            # print(record['type'])
            # checking record types
            if cf_record['type'] == 'A':
                print('A : ', cf_record['content'])
                if cf_record['name'] == "www." + cfZone['name']:
                    print('in')
                    cf_record['type'] = "CNAME"
                    cf_record['content'] = cfZone['name']
                    response = client.change_resource_record_sets(
                        HostedZoneId = zoneId,
                        ChangeBatch = {
                            'Changes': [
                                {
                                    'Action': 'CREATE',
                                    'ResourceRecordSet': {
                                        'Name': cf_record['name']+".",
                                        'Type': cf_record['type'],
                                        'TTL': 60,
                                        'ResourceRecords': [
                                            {
                                                'Value': cf_record['content']
                                            },
                                        ]
                                    }
                                }
                            ]
                        }
                    )
                    response = client.list_resource_record_sets(
                        HostedZoneId=zoneId,
                    )
                    print(json.dumps(response,indent=4))
            elif cf_record['type'] == 'MX':
                mx.setdefault(cf_record['name'], []).append(str(cf_record["priority"])+" "+cf_record['content'])
            elif cf_record['type'] in ("SOA", "NS"):
                continue
            elif cf_record['type'] == 'TXT':
                txts = '\"' + cf_record['content'] + '\"' + " " + txts
                txt_name=cf_record['name']
            elif cf_record['type'] == 'CNAME':
                print("creating CNAME record named "+cf_record["name"]+" in "+cfZone["name"]+" zone with content "+cf_record["content"])
                response = client.change_resource_record_sets(
                    HostedZoneId=zoneId,
                    ChangeBatch={
                        'Changes': [
                            {
                                'Action': 'CREATE',
                                'ResourceRecordSet': {
                                    'Name': "www."+cf_record['name'] + ".",
                                    'Type': "CNAME",
                                    'TTL': 60,
                                    'ResourceRecords': [
                                        {
                                            'Value': cf_record['content']
                                        },
                                    ]
                                }
                            }
                        ]
                    }
                )
            else :
                print("creating "+cf_record["type"]+" record named "+cf_record["name"]+" in "+cfZone["name"]+" zone with content "+cf_record["content"])
                response = client.change_resource_record_sets(
                    HostedZoneId=zoneId,
                    ChangeBatch={
                        'Changes': [
                            {
                                'Action': 'CREATE',
                                'ResourceRecordSet': {
                                    'Name': cf_record['name'] + ".",
                                    'Type': cf_record['type'],
                                    'TTL': 60,
                                    'ResourceRecords': [
                                        {
                                            'Value': cf_record['content']
                                        },
                                    ]
                                }
                            }
                        ]
                    }
                )
        if len(txts) > 1 :
            print("creating MX record named ", cfZone['name'], " with in ", cfZone["name"], " zone with content ", txts)
            response = client.change_resource_record_sets(
                HostedZoneId=zoneId,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'CREATE',
                            'ResourceRecordSet': {
                                'Name': cfZone['name'] + ".",
                                'Type': "TXT",
                                'TTL': 60,
                                'ResourceRecords': [
                                    {
                                        'Value': txts
                                    },
                                ]
                            }
                        }
                    ]
                }
            )

        for name, content in mx.items():
            print("creating MX record named ",name," with in ",cfZone["name"]," zone with content ",content)
            ResourceRecordSet=[]
            for value in content :
                ResourceRecordSet.append({
                                        'Value': value
                                    })
            response = client.change_resource_record_sets(
                HostedZoneId=zoneId,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'CREATE',
                            'ResourceRecordSet': {
                                'Name': name + ".",
                                'Type': "MX",
                                'TTL': 60,
                                'ResourceRecords': ResourceRecordSet
                            }
                        }
                    ]
                }
            )

