import logging
import os
from typing import List, Optional

import boto3

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
ec2 = boto3.client("ec2")


class NetworkInterface(dict):
    def __init__(self, instance: dict):
        self.update(instance)

    @property
    def interface_id(self) -> str:
        return self.get("NetworkInterfaceId")

    @property
    def attachment_id(self) -> str:
        return self.get("Attachment",{}).get("AttachmentId")

    @property
    def attachment_status(self) -> str:
        return self.get("Attachment",{}).get("Status")

    @property
    def status(self) -> str:
        return self.get("Status")

    @property
    def is_available(self) -> bool:
        return self.status == "available"

    @property
    def instance_id(self) -> Optional[str]:
        return self.get("Attachment", {}).get("InstanceId")

    @property
    def subnet_id(self) -> Optional[str]:
        return self.get("SubnetId")

    @property
    def pool_name(self) -> Optional[str]:
        return self.tags.get("network-interface-manager-pool")

    @property
    def tags(self) -> dict:
        return {t["Key"]: t["Value"] for t in self["TagSet"]}

    def __key(self):
        return self.interface_id

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __str__(self):
        return str(self.__key())


def get_pool_interfaces(pool_name: str) -> List[NetworkInterface]:
    response = ec2.describe_network_interfaces(
        Filters=[
            {"Name": "tag:network-interface-manager-pool", "Values": [pool_name]},
        ]
    )
    return [NetworkInterface(n) for n in response["NetworkInterfaces"]]

def get_pool_interfaces_in_subnet(pool_name: str, subnet_id: str) -> List[NetworkInterface]:
    response = ec2.describe_network_interfaces(
        Filters=[
            {"Name": "tag:network-interface-manager-pool", "Values": [pool_name]},
            {"Name": "subnet-id", "Values": [subnet_id]},
        ]
    )
    return [NetworkInterface(n) for n in response["NetworkInterfaces"]]
