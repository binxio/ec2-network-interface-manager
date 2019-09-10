# AWS Network Interface Manager
The network-interface-manager, manages the assignment of a pool of network interfaces to instances. When
the instance is stopped or terminated, the interface is removed. When a new instance is started, an interface
from the pool is assigned to it. The goal is to be keep a fixed internal ip address active, while replacing the 
instance. 


## Who does it work?
The manager will listen to all EC2 instance state change notifications. When an instance with the tag `network-interface-manager-pool` 
reaches the state running, it will assign a free network interface with the same tag and tag value in it's subnet.

## How do I use it?
You can start using the network interface manager, in three simple steps:

1. deploy the network-interface-manager
2. create a pool of tagged network interfaces
3. create an auto scaling group of tagged instances

## deploy the network-interface-manager
To deploy the provider, type:

```sh
git clone https://github.com/binxio/ec2-network-interface-manager.git
cd ec2-network-interface-manager
aws cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name network-interface-manager \
        --template-body file://./cloudformation/network-interface-manager.yaml

aws cloudformation wait stack-create-complete  --stack-name network-interface-manager
```
## Create a pool of Network interfaces
Create a pool of network interfaces, and tag them with an `network-interface-manager-pool` value:
```
InterfaceAZ1:
  Type: AWS::EC2::NetworkInterface
  Properties:
     Tags:
     - Key: network-interface-manager-pool
       Value: bastion

InterfaceAZ2:
  Type: AWS::EC2::NetworkInterface
  Properties:
     Tags:
     - Key: network-interface-manager-pool
       Value: bastion
```

## Create an auto scaling group
Create an auto scaling group and apply the tag `network-interface-manager-pool` to all the instances:
```
  AutoScalingGroup:
    Type: AWS::AutoScaling::AutoScalingGroup
    Properties:
      ...
      Tags:
        - Key: network-interface-manager-pool
          Value: bastion
          PropagateAtLaunch: true
```
The manager will automatically associate network interfaces to instance tagged with `network-interface-manager-pool`. It does
this by subscribing to EC2 state change events. It will not do anything on instances without the
tag `network-interface-manager-pool`. The network interface manager also syncs the state every 5 minutes, to ensure that we are eventually
consistent in the face of errors.

That is all. If you want to see it all in action, deploy the demo.

## Deploy the demo
In order to deploy the demo, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_NAMED_IAM \
        --stack-name network-interface-manager-demo \
        --template-body file://./cloudformation/demo-stack.yaml

aws cloudformation wait stack-create-complete  --stack-name network-interface-manager-demo
```

## Caveats
As network interfaces are bound to an availability zone, the auto scaling group should also be tied to 
a single availability zone. Otherwise. instances can be rescheduled in another AZ leaving the network 
interfaces from the pool unattached.

## Alternatives
There are two alternative solutions to achieve the same functionality:
1. use a [network load balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/create-network-load-balancer.html) 
2. associate an network interfae on instance startup.
In my use case, I did not want to spent money on keeping an NLB running nor give the instance all the permissions to attach network
interfaces.
