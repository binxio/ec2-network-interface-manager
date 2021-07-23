import copy
import boto3
from typing import List
from network_interface_manager import handler, Manager, NetworkInterface
from network_interface_manager.manager import (
    get_pool_instances,
    get_pool_interfaces,
    get_all_pool_names,
)

event = {
    "id": "7bf73129-1428-4cd3-a780-95db273d1602",
    "detail-type": "EC2 Instance State-change Notification",
    "source": "aws.ec2",
    "account": "123456789012",
    "time": "2015-11-11T21:29:54Z",
    "region": "us-east-1",
    "resources": ["arn:aws:ec2:us-east-1:123456789012:instance/i-abcd1111"],
    "detail": {"instance-id": "i-abcd1111", "state": "running"},
}


ec2 = boto3.client("ec2")


def get_interfaces() -> (
    List[NetworkInterface],
    List[NetworkInterface],
    List[NetworkInterface],
):
    response = ec2.describe_network_interfaces(
        Filters=[{"Name": "tag:network-interface-manager-pool", "Values": ["bastion"]}]
    )
    interfaces = [NetworkInterface(a) for a in response["NetworkInterfaces"]]
    assert len(interfaces) == 3
    return (
        interfaces,
        list(filter(lambda i: i.is_available, interfaces)),
        list(filter(lambda i: not i.is_available, interfaces)),
    )


def test_get_all_pool_names():
    pool_names = get_all_pool_names()
    assert pool_names == ["bastion"]


def test_get_interfaces():
    interfaces, _, _ = get_interfaces()
    pool_interfaces = get_pool_interfaces("bastion")
    for a in get_pool_interfaces("bastion"):
        assert a.pool_name == "bastion"
    assert set(interfaces) == set(pool_interfaces)


def test_get_pool_instances():
    instances = get_pool_instances("bastion")
    assert (
        len(instances) == 3
    ), "expected 3 instances with tag network-interfaces-manager-pool == bastion"


def return_all_interfaces_to_pool():
    for instance in get_pool_instances("bastion"):
        manager = Manager("bastion")
        manager.detach_interfaces(instance.instance_id)

    _, available, _ = get_interfaces()
    assert len(available) == 3


def test_remove_and_add():
    return_all_interfaces_to_pool()

    instances = get_pool_instances("bastion")
    for instance in instances:
        event["detail"]["state"] = "running"
        event["detail"]["instance-id"] = instance.instance_id
        handler(event, {})

    _, available, allocated = get_interfaces()
    assert len(available) == 0

    event["detail"]["state"] = "terminated"
    event["detail"]["instance-id"] = instances[0].instance_id
    handler(event, {})

    _, available, _ = get_interfaces()
    assert len(available) == 0


def test_remove_non_existing_instance():
    event["detail"]["state"] = "terminated"
    event["detail"]["instance-id"] = " i-000000000000a4a41"
    handler(event, {})


def test_add_non_existing_instance():
    return_all_interfaces_to_pool()
    event["detail"]["state"] = "running"
    event["detail"]["instance-id"] = "i-000000000000a4a41"
    handler(event, {})


def test_timer():
    get_interfaces()
    return_all_interfaces_to_pool()

    event = {"detail-type": "Scheduled Event", "source": "aws.events", "detail": {}}
    handler(event, {})

    _, available, _ = get_interfaces()
    assert len(available) == 0

    event = {"detail-type": "Scheduled Event", "source": "aws.events", "detail": {}}
    handler(event, {})

    _, available, _ = get_interfaces()
    assert len(available) == 0


def test_invalid_event():
    get_interfaces()
    return_all_interfaces_to_pool()

    event2 = copy.deepcopy(event)
    event2["source"] = "aws.unknown"
    handler(event2, {})

    _, available, _ = get_interfaces()
    assert len(available) == 3
