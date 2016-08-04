# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates config for htcondor cluster with 1 master, 1 job submitter
and n compute nodes.
"""


def GenerateConfig(evaluation_context):
    return """
resources:
- name: condor-network
  type: compute.v1.network
  properties:
    IPv4Range: 10.240.0.0/16
- name: ssh-firewall-rule
  type: compute.v1.firewall
  properties:
    network: $(ref.condor-network.selfLink)
    sourceRanges: ["0.0.0.0/0"]
    allowed:
    - IPProtocol: TCP
      ports: ["22"]
- name: all-internal-firewall-rule
  type: compute.v1.firewall
  properties:
    network: $(ref.condor-network.selfLink)
    sourceRanges: ["10.240.0.0/16"]
    allowed:
    - IPProtocol: TCP
      ports: ["0-65535"]
    - IPProtocol: UDP
      ports: ["0-65535"]
    - IPProtocol: ICMP
- name: condor-master
  type: compute.v1.instance
  properties:
    zone: %(zone)s
    machineType: https://www.googleapis.com/compute/v1/projects/%(project)s/zones/%(zone)s/machineTypes/%(instancetype)s
    disks:
    - deviceName: boot
      type: PERSISTENT
      boot: true
      autoDelete: true
      initializeParams:
        sourceImage: https://www.googleapis.com/compute/v1/projects/debian-cloud/global/images/debian-8-jessie-v20160606
    networkInterfaces:
    - network: $(ref.condor-network.selfLink)
      accessConfigs:
      - name: External NAT
        type: ONE_TO_ONE_NAT
    serviceAccounts:
      - email: "default"
        scopes:
        - "https://www.googleapis.com/auth/logging.write"
    tags:
      items:
        - condor-master
    metadata:
      items:
        - key: startup-script
          value: |
            #!/bin/bash
            apt-get update && apt-get install -y wget curl net-tools vim
            echo "deb http://research.cs.wisc.edu/htcondor/debian/stable/ jessie contrib" >> /etc/apt/sources.list
            wget -qO - http://research.cs.wisc.edu/htcondor/debian/HTCondor-Release.gpg.key | apt-key add -
            apt-get update && apt-get install -y condor
            if  dpkg -s condor >& /dev/null  ; then echo "yes"; else sleep 10; apt-get install -y condor; fi;
            cat <<EOF > /etc/condor/config.d/condor_config.local
            DISCARD_SESSION_KEYRING_ON_STARTUP=False
            DAEMON_LIST = MASTER
            CONDOR_ADMIN=%(email)s
            ALLOW_WRITE = \$(ALLOW_WRITE),10.240.0.0/16
            EOF
            /etc/init.d/condor start
            cd /tmp; curl -sSO https://dl.google.com/cloudagents/install-logging-agent.sh
            bash install-logging-agent.sh
            cat <<EOF > /etc/google-fluentd/config.d/condor.conf
            <source>
            type tail
            format none
            path /var/log/condor/*Log
            pos_file /var/lib/google-fluentd/pos/condor.pos
            read_from_head true
            tag condor
            </source>
            EOF
            service google-fluentd restart
- name: condor-submit
  type: compute.v1.instance
  properties:
    zone: %(zone)s
    machineType: https://www.googleapis.com/compute/v1/projects/%(project)s/zones/%(zone)s/machineTypes/%(instancetype)s
    disks:
    - deviceName: boot
      type: PERSISTENT
      boot: true
      autoDelete: true
      initializeParams:
        sourceImage: https://www.googleapis.com/compute/v1/projects/debian-cloud/global/images/debian-8-jessie-v20160606
    networkInterfaces:
    - network: $(ref.condor-network.selfLink)
      accessConfigs:
      - name: External NAT
        type: ONE_TO_ONE_NAT
    serviceAccounts:
      - email: "default"
        scopes:
        - "https://www.googleapis.com/auth/logging.write"
    tags:
      items:
        - condor-submit
    metadata:
      items:
        - key: startup-script
          value: |
            #!/bin/bash
            apt-get update && apt-get install -y wget net-tools vim curl gcc
            echo "deb http://research.cs.wisc.edu/htcondor/debian/stable/ jessie contrib" >> /etc/apt/sources.list
            wget -qO - http://research.cs.wisc.edu/htcondor/debian/HTCondor-Release.gpg.key | apt-key add -
            apt-get update && apt-get install -y condor
            if  dpkg -s condor >& /dev/null  ; then echo "yes"; else sleep 10; apt-get install -y condor; fi;
            cat <<EOF > /etc/condor/config.d/condor_config.local
            DISCARD_SESSION_KEYRING_ON_STARTUP=False
            CONDOR_ADMIN=%(email)s
            CONDOR_HOST=condor-master
            DAEMON_LIST = MASTER, SCHEDD
            ALLOW_WRITE = \$(ALLOW_WRITE), \$(CONDOR_HOST)
            EOF
            /etc/init.d/condor start
            cd /tmp; curl -sSO https://dl.google.com/cloudagents/install-logging-agent.sh
            bash install-logging-agent.sh
            cat <<EOF > /etc/google-fluentd/config.d/condor.conf
            <source>
            type tail
            format none
            path /var/log/condor/*Log
            pos_file /var/lib/google-fluentd/pos/condor.pos
            read_from_head true
            tag condor
            </source>
            EOF
            cat <<EOF > /etc/google-fluentd/config.d/condor-jobs.conf
            <source>
            type tail
            format multiline
            format_firstline /^\.\.\./
            format1 /^\\.\\.\\.\\n... \\((?<job>[^\.]*)\\.(?<subjob>[^\\.]*)\\.(?<run>[^\\)]*)\\).*Usr 0 (?<usrh>[^:]*):(?<usrm>[^:]*):(?<usrs>[^,]*), Sys 0 (?<sysh>[^:]*):(?<sysm>[^:]*):(?<syss>[^ ]*)  -  Run Remote Usage.*/
            types usrh:integer,usrm:integer,usrs:integer,sysh:integer,sysm:integer,syss:integer
            path /var/log/condor/jobs/*.log
            pos_file /var/lib/google-fluentd/pos/condor-jobs.pos
            read_from_head true
            tag condor
            </source>
            EOF
            mkdir -p /var/log/condor/jobs
            touch /var/log/condor/jobs/stats.log
            chmod 666 /var/log/condor/jobs/stats.log
            service google-fluentd restart
- name: condor-compute
  type: compute.v1.instanceTemplate
  properties:
    project: %(project)s
    properties:
      machineType: %(instancetype)s
      disks:
      - deviceName: boot
        type: PERSISTENT
        boot: true
        autoDelete: true
        initializeParams:
          sourceImage: https://www.googleapis.com/compute/v1/projects/debian-cloud/global/images/debian-8-jessie-v20160606
      networkInterfaces:
      - network: $(ref.condor-network.selfLink)
        accessConfigs:
        - name: External NAT
          type: ONE_TO_ONE_NAT
      serviceAccounts:
      - email: "default"
        scopes:
        - "https://www.googleapis.com/auth/logging.write"
      tags:
        items:
        - condor-compute
      scheduling:
        preemptible: true
      metadata:
        items:
        - key: startup-script
          value: |
            #!/bin/bash
            apt-get update && apt-get install -y wget net-tools vim curl
            echo "deb http://research.cs.wisc.edu/htcondor/debian/stable/ jessie contrib" >> /etc/apt/sources.list
            wget -qO - http://research.cs.wisc.edu/htcondor/debian/HTCondor-Release.gpg.key | apt-key add -
            apt-get update && apt-get install -y condor
            if  dpkg -s condor >& /dev/null  ; then echo "yes"; else sleep 10; apt-get install -y condor; fi;
            cat <<EOF > /etc/condor/config.d/condor_config.local
            DISCARD_SESSION_KEYRING_ON_STARTUP=False
            CONDOR_ADMIN=%(email)s
            CONDOR_HOST=condor-master
            DAEMON_LIST = MASTER, STARTD
            ALLOW_WRITE = \$(ALLOW_WRITE), \$(CONDOR_HOST)
            EOF
            cd /tmp; curl -sSO https://dl.google.com/cloudagents/install-logging-agent.sh
            bash install-logging-agent.sh
            /etc/init.d/condor start
            cat <<EOF > /etc/google-fluentd/config.d/condor.conf
            <source>
            type tail
            format none
            path /var/log/condor/*Log
            pos_file /var/lib/google-fluentd/pos/condor.pos
            read_from_head true
            tag condor
            </source>
            EOF
            service google-fluentd restart
- name: condor-compute-igm
  type: compute.v1.instanceGroupManagers
  properties:
    baseInstanceName: condor-compute-instance
    instanceTemplate: $(ref.condor-compute.selfLink)
    targetSize: %(count)s
    zone: %(zone)s
- name: condor-compute-as
  type: compute.v1.autoscaler
  properties:
    zone: %(zone)s
    target: $(ref.condor-compute-igm.selfLink)
    autoscalingPolicy:
      minNumReplicas: %(count)s
      maxNumReplicas: %(count)s
outputs:
- name: condor-submit-host-ip,
  value: \$(ref.condor-submit.networkInterfaces[0].accessConfigs[0].natIP)
""" % {"zone": evaluation_context.properties["zone"],
       "count": evaluation_context.properties["count"],
       "project": evaluation_context.env["project"],
       "email": evaluation_context.properties["email"],
       "instancetype": evaluation_context.properties["instancetype"]}
