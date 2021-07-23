"""
AWS Network Interface Manager

Manages network interfaces associated to ec2 instances.

When a instances is stopped or terminated, the manager will remove all the network interface that are associated
with the instance.

When a instance is started, the manager will add a network interface with the instance.
"""
import os
import boto3
import logging
from time import sleep
from typing import List, Set
from .network_interface import (
    NetworkInterface,
    get_pool_interfaces,
    get_available_pool_interfaces_in_subnet,
)
from .ec2_instance import EC2Instance, get_pool_instances, describe_pool_instance


from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
ec2 = boto3.client("ec2")


class Manager(object):
    def __init__(self, pool_name: str):
        self.pool_name: str = pool_name
        self.network_interfaces: List[NetworkInterface] = []
        self.instances: List[EC2Instance] = []

    def refresh(self):
        self.network_interfaces = get_pool_interfaces(self.pool_name)
        self.instances = get_pool_instances(self.pool_name)

    @property
    def attached_instances(self) -> Set[EC2Instance]:
        """
        all `self.instances` attached to an interface from `self.network_interfaces`
        """
        result = set()
        for instance in self.instances:
            if list(
                filter(
                    lambda a: a.instance_id == instance.instance_id,
                    self.network_interfaces,
                )
            ):
                result.add(instance)
        return result

    @property
    def unattached_instances(self) -> Set[EC2Instance]:
        """
        all instances in the  self.instances which do not have an interface assigned from `self.network_interfaces`
        """
        return set(self.instances) - self.attached_instances

    def attach_interface(self, instance: EC2Instance):
        available_interfaces = get_available_pool_interfaces_in_subnet(self.pool_name, instance.subnet_id)
        if not available_interfaces:
            log.error(
                f'No network interfaces available from pool "{self.pool_name}" in subnet "{instance.subnet_id}" to attach to "{instance.instance_id}"'
            )
            return

        instance_id = instance.instance_id
        interface_id = available_interfaces[0].interface_id
        device_index = len(instance.get("NetworkInterfaces", []))
        try:
            log.info(
                f'attach network interface from pool "{self.pool_name}" to "{instance_id}" as device {device_index}'
            )
            ec2.attach_network_interface(
                InstanceId=instance_id,
                NetworkInterfaceId=interface_id,
                DeviceIndex=device_index,
            )
            self.wait_for_interface_status(available_interfaces[0], "in-use")
        except ClientError as e:
            log.error(
                f'failed to attach interface "{interface_id}" from "{self.pool_name}" to instance "{instance_id}", {e}'
            )

    def attach_interfaces(self):
        """
        ensure a network interface is associated with all running instances in the pool
        """
        self.refresh()
        instances = list(self.unattached_instances)

        if not instances:
            log.debug(
                f'All {len(self.instances)} instances in the pool "{self.pool_name}" are associated with a network interface'
            )
            return

        for instance in instances:
            self.attach_interface(instance)

    def wait_for_interface_status(self, interface: NetworkInterface, status: str):
        while interface.status != status:
            log.info(
                f"waiting 1s for interface {interface.interface_id} to become {status}"
            )
            sleep(1)
            response = ec2.describe_network_interfaces(
                NetworkInterfaceIds=[interface.interface_id]
            )
            if response["NetworkInterfaces"]:
                interface = NetworkInterface(response["NetworkInterfaces"][0])
            else:
                log.error(
                    f"interface {interface.interface_id} could not be described. Has it been deleted?"
                )

    def detach_interfaces(self, instance_id: str):
        """
        detach all the interfaces of the pool from the instance `self.instance_id`
        """
        self.refresh()
        attached_interfaces = list(
            filter(lambda i: i.instance_id == instance_id, self.network_interfaces)
        )
        if not attached_interfaces:
            log.debug(
                f'No network interfaces from pool {self.pool_name} to detach from instance "{instance_id}"'
            )
            return

        for interface in attached_interfaces:
            try:
                log.info(
                    f'detaching interface "{interface.interface_id}" of pool "{self.pool_name} from "{instance_id}"'
                )
                ec2.detach_network_interface(AttachmentId=interface.attachment_id)
                self.wait_for_interface_status(interface, "available")

            except ClientError as e:
                log.error(
                    f'failed to remove interface "{interface.interface_id}" from instance "{instance_id}", {e}'
                )


def is_state_change_event(event):
    return event.get("source") == "aws.ec2" and event.get("detail-type") in [
        "EC2 Instance State-change Notification"
    ]


def is_add_address_event(event):
    return (
        is_state_change_event(event) and event.get("detail").get("state") == "running"
    )


def is_address_removed_event(event):
    return is_state_change_event(event) and event.get("detail").get("state") in [
        "stopping",
        "shutting-down",
        "terminated",
    ]


def is_timer(event) -> bool:
    return event.get("source") == "aws.events" and event.get("detail-type") in [
        "Scheduled Event"
    ]


def get_all_pool_names() -> List[str]:
    result = []
    resourcetagging = boto3.client("resourcegroupstaggingapi")
    for values in resourcetagging.get_paginator("get_tag_values").paginate(
        Key="network-interface-manager-pool"
    ):
        result.extend(values["TagValues"])
    return result


def handler(event: dict, context: dict):
    if is_add_address_event(event) or is_address_removed_event(event):
        instance = describe_pool_instance(event.get("detail").get("instance-id"))
        if not instance:
            return

        if not instance.pool_name:
            log.debug(
                f'ignoring instance "{instance.instance_id}" as it is not associated with a pool'
            )
            return

        manager = Manager(instance.pool_name)
        if is_address_removed_event(event):
            manager.detach_interfaces(instance.instance_id)
            manager.attach_interfaces()
        else:
            manager.attach_interface(instance)

    elif is_timer(event):
        for pool_name in get_all_pool_names():
            manager = Manager(pool_name)
            manager.attach_interfaces()
    elif is_state_change_event(event):
        log.debug("ignored state change event %s", event.get("detail", {}).get("state"))
    else:
        log.error(
            "ignoring event %s from source %s",
            event.get("detail-type"),
            event.get("source"),
        )
