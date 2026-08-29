# SmartBranch 360

A secure branch-office network simulation built in Cisco Packet Tracer with VLAN segmentation, inter-VLAN routing, DHCP, DNS, Guest Wi-Fi, NAT/PAT, ACL-based isolation, secure SSH management, controlled troubleshooting scenarios, and a Python network assurance tool.

## Project Status

- ✅ Project completed
- ✅ Network implementation completed
- ✅ Functional testing completed
- ✅ Five fault scenarios completed
- ✅ Python assurance tool completed
- ✅ Documentation completed
- ✅ Demo completed
- ✅ Final internship and college submission completed

## Project Overview

SmartBranch 360 models a small branch office that needs wired employee connectivity, Guest Wi-Fi, internal server access, simulated Internet connectivity, VLAN segmentation, secure management, controlled inter-VLAN access, repeatable troubleshooting, and automated validation. The completed implementation combines segmented wired and wireless access, centralized routing and services, security controls, and configuration assurance.

The repository contains the working Packet Tracer topology, the intended design in machine-readable YAML, real Cisco IOS command captures, validation reports, and screenshot evidence for healthy operation and five fault-remediation scenarios.

## Project Objectives

- Design a realistic small-branch network with distinct trust zones.
- Implement reliable inter-VLAN routing and shared network services.
- Isolate guest traffic from internal employee, server, and management networks.
- Restrict device administration to the authorized management host.
- Document normal behavior and repeatable fault-remediation workflows.
- Compare the intended design with captured device state using Python.

## Network Architecture

![SmartBranch 360 Packet Tracer topology](evidence/stage9/Complete%20Topology.png)

`R1-BRANCH` provides router-on-a-stick routing through IEEE 802.1Q subinterfaces on `G0/0` and connects to the simulated external network through `G0/1`. `SW1` and `SW2` carry VLANs 10, 20, 30, and 99 over their expected trunks. The topology includes an internal server, a simulated Internet server, wired employee and management endpoints, and guest laptops connected through `AP-GUEST`.

Expected trunks:

- `SW1 Gi0/1`: VLANs 10, 20, 30, and 99
- `SW1 Gi0/2`: VLANs 10, 20, 30, and 99
- `SW2 Gi0/1`: VLANs 10, 20, 30, and 99

## Device Inventory

| Device | Packet Tracer type | Addressing | Role |
|---|---|---|---|
| R1-BRANCH | Cisco 2911 | VLAN gateways; `203.0.113.1/24` on `G0/1` | Inter-VLAN routing, DHCP, NAT/PAT, ACL enforcement, and SSH management |
| SW1 | Cisco 2960-24TT | `10.10.99.2/24` | Access switching and trunk aggregation |
| SW2 | Cisco 2960-24TT | `10.10.99.3/24` | Access switching and guest-segment connectivity |
| SRV1 | Server-PT | `10.10.30.10` | Internal server in VLAN 30 |
| INTERNET-SRV | Server-PT | `203.0.113.10` | Server on the simulated external network |
| AP-GUEST | AccessPoint-PT | — | Wireless access for VLAN 20 guest clients |
| ADMIN-PC | PC-PT | `10.10.99.10` authorized SSH source | Management workstation |
| EMP-PC1–EMP-PC5 | PC-PT | DHCP clients | Employee endpoints in VLAN 10 |
| GUEST-LAP1–GUEST-LAP2 | Laptop-PT | DHCP clients | Wireless guest endpoints in VLAN 20 |

## VLAN and IP Addressing Plan

| VLAN | Name | Subnet | Default gateway |
|---:|---|---|---|
| 10 | EMPLOYEE | `10.10.10.0/24` | `10.10.10.1` |
| 20 | GUEST | `10.10.20.0/24` | `10.10.20.1` |
| 30 | SERVER | `10.10.30.0/24` | `10.10.30.1` |
| 99 | MANAGEMENT | `10.10.99.0/24` | `10.10.99.1` |

## Core Features

- VLAN segmentation for employee, guest, server, and management traffic
- IEEE 802.1Q trunking between the router and switches
- Router-on-a-stick using `R1-BRANCH` subinterfaces
- Inter-VLAN routing
- DHCP pools and default-gateway assignment
- DNS configuration and connectivity validation
- Guest Wi-Fi through `AP-GUEST`
- NAT/PAT toward the simulated external network
- ACL-based guest isolation
- Dedicated management VLAN
- Management-only SSH access
- Functional verification with Cisco IOS operational commands
- Five controlled fault-injection and recovery scenarios
- Python network assurance driven by YAML requirements and real CLI captures

## Security Design

| Source | Destination | Policy |
|---|---|---|
| Guest | Employee network | Denied |
| Guest | Server network | Denied |
| Guest | Management network | Denied |
| Guest | Simulated external network | Allowed |

SSH access to network devices is restricted to the management host at `10.10.99.10`. The Guest ACL is applied inbound on `R1-BRANCH G0/0.20`.

## Python Assurance Tool

[`python_checker/checker.py`](python_checker/checker.py) is a Python 3 network-assurance utility. It loads the intended design from [`requirements/requirements.yaml`](requirements/requirements.yaml), parses real Packet Tracer Cisco IOS captures from [`python_checker/sample_inputs/`](python_checker/sample_inputs/), and reports PASS, WARN, or FAIL findings.

The checker validates:

- Required VLAN presence on SW1 and SW2
- Allowed VLANs on every expected trunk
- Router interface and gateway addresses
- NAT inside/outside interface roles
- DHCP default-router values when present
- Guest ACL definition and inbound application
- Management SSH source restrictions

It returns exit code `0` when all mandatory checks pass, `1` when a mandatory check fails, and `2` for an input or configuration error. The `--report` option writes the same findings and summary to a plain-text report.

## Example Healthy Validation

The committed [healthy validation report](python_checker/sample_reports/healthy_report.txt) was generated from the healthy captures. Selected exact findings:

```text
[PASS] Trunk SW1 Gi0/2 allows VLANs 10,20,30,99
[PASS] R1-BRANCH G0/0.20 gateway is 10.10.20.1
[PASS] Guest ACL 100 exists and is applied inbound to G0/0.20
[PASS] SSH access to network devices is restricted to 10.10.99.10
```

```text
==================================================
SmartBranch 360 Assurance Summary
==================================================
Checks passed: 25
Warnings:      0
Checks failed: 0
Overall: PASS
==================================================
```

## Example Fault Detection

The committed [trunk fault report](python_checker/sample_reports/trunk_fault_report.txt) shows the checker detecting the missing Guest VLAN on `SW1 Gi0/2`:

```text
[FAIL] VLAN 20 missing from trunk SW1 Gi0/2
       Expected: 10,20,30,99
       Observed: 10,30,99
       Symptom: Guest connectivity may fail.
       Suggested fix: Add VLAN 20 to the allowed trunk VLAN list.
```

```text
Checks passed: 24
Warnings:      0
Checks failed: 1
Overall: FAIL
```

## Fault Injection and Troubleshooting

The Stage 10 evidence documents each injected fault, its visible symptom, and the restored state:

1. **F01 - Incorrect Employee Default Gateway:** changes the Employee gateway, demonstrates routed-connectivity failure, and verifies recovery after correction. [View evidence](evidence/stage10/F01%2001%20Wrong%20Gateway.png)
2. **F02 - VLAN 20 Missing From Trunk:** removes VLAN 20 from the `SW1 Gi0/2` allowed list, interrupting Guest connectivity until the trunk is restored. [View evidence](evidence/stage10/F02%2001%20Trunk%20Missing%20VLAN20.png)
3. **F03 - Incorrect Guest DHCP Gateway:** supplies the wrong Guest default gateway and verifies recovery after the DHCP configuration is corrected. [View evidence](evidence/stage10/F03%2001%20Bad%20DHCP%20Gateway.png)
4. **F04 - ACL Blocking DNS:** demonstrates DNS failure caused by an ACL denial and recovery after the ACL is fixed. [View evidence](evidence/stage10/F04%2001%20DNS%20ACL%20Deny.png)
5. **F05 - NAT Outside Missing:** removes the outside NAT role, demonstrates missing translation state, and verifies restoration. [View evidence](evidence/stage10/F05%2001%20NAT%20Outside%20Missing.png)

> **F05 verification note:** NAT health is verified primarily through interface-role, NAT statistics, and fresh translation evidence. An external ping is not treated as definitive because `INTERNET-SRV` is directly connected to `R1-BRANCH` in this Packet Tracer simulation.

## Testing and Verification

The completed evidence set and reports cover:

- Employee DHCP addressing, server access, DNS resolution, and simulated external access
- Guest DHCP and Wi-Fi connectivity
- Guest access to the simulated external network
- Guest isolation from Employee, Server, and Management networks
- Authorized management SSH to R1-BRANCH, SW1, and SW2
- Unauthorized Employee SSH blocking
- VLAN and trunk verification on both switches
- Router interface, ACL counter, and NAT translation verification
- Healthy Python assurance validation and the VLAN 20 trunk-fault detection run

## Documentation and Deliverables

- [Cisco Packet Tracer project](packet_tracer/SmartBranch360.pkt)
- Network design document: [PDF](design/SmartBranch360_Design_Document.pdf) and [DOCX](design/SmartBranch360_Design_Document.docx)
- Troubleshooting fault cards: [PDF](fault_cards/SmartBranch360_Fault_Cards.pdf) and [DOCX](fault_cards/SmartBranch360_Fault_Cards.docx)
- [Machine-readable network requirements](requirements/requirements.yaml)
- [Python assurance checker](python_checker/checker.py)
- [Healthy validation report](python_checker/sample_reports/healthy_report.txt)
- [VLAN 20 trunk-fault report](python_checker/sample_reports/trunk_fault_report.txt)
- [Stage 9 functional evidence](evidence/stage9/) and [Stage 10 troubleshooting evidence](evidence/stage10/)
- [Final demo guide](demo/README.md)
- [Final college submission package](college_submission/) containing the submitted Packet Tracer file, internship project report, and completion certificates

## Repository Structure

```text
SmartBranch360/
├── README.md
├── .gitignore
├── packet_tracer/
│   └── SmartBranch360.pkt
├── requirements/
│   └── requirements.yaml
├── python_checker/
│   ├── checker.py
│   ├── sample_inputs/
│   │   ├── sw1_vlan.txt
│   │   ├── sw2_vlan.txt
│   │   ├── sw1_trunk_good.txt
│   │   ├── sw1_trunk_fault.txt
│   │   ├── sw2_trunk.txt
│   │   ├── r1_interfaces.txt
│   │   ├── r1_running_config.txt
│   │   ├── r1_nat.txt
│   │   ├── r1_dhcp.txt
│   │   └── r1_acl.txt
│   └── sample_reports/
│       ├── healthy_report.txt
│       └── trunk_fault_report.txt
├── evidence/
│   ├── stage9/
│   └── stage10/
├── design/
│   ├── SmartBranch360_Design_Document.pdf
│   └── SmartBranch360_Design_Document.docx
├── fault_cards/
│   ├── SmartBranch360_Fault_Cards.pdf
│   └── SmartBranch360_Fault_Cards.docx
├── demo/
│   └── README.md
└── college_submission/       # final .pkt, project report PDF, and certificates
```

`evidence/stage9/` contains healthy validation screenshots. `evidence/stage10/` contains the F01-F05 fault, symptom, and restored-state screenshots.

## Running the Checker

From the repository root, install the single Python dependency:

```bash
python -m pip install pyyaml
```

Run the healthy validation set:

```bash
python python_checker/checker.py
```

Run the VLAN 20 trunk-fault demonstration:

```bash
python python_checker/checker.py --sw1-trunk python_checker/sample_inputs/sw1_trunk_fault.txt
```

## Technologies Used

- Cisco Packet Tracer
- Cisco IOS CLI
- Python
- PyYAML
- Git
- GitHub

## Demo Video

[Watch the SmartBranch 360 Demo Video](https://drive.google.com/drive/folders/1pjBc5WL8g6srrqlbR4s28TNfVx1h3P2Z?usp=drive_link)

The completed demo accompanies the documented workflow: presenting the final topology, verifying healthy operation, introducing a troubleshooting fault, diagnosing and repairing the issue, confirming restored service, and using the Python assurance results where applicable.

## Learning Outcomes

- Translating a logical network design into a working Packet Tracer topology
- Implementing VLANs, 802.1Q trunks, router-on-a-stick, DHCP, DNS, NAT/PAT, ACLs, and SSH
- Applying least-privilege access between user, guest, server, and management segments
- Capturing and interpreting Cisco IOS operational and configuration output
- Diagnosing connectivity faults through symptoms, command evidence, and controlled remediation
- Representing intended network state in YAML and validating observed state with Python
- Maintaining reproducible technical evidence and reports in Git and GitHub
