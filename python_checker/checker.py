#!/usr/bin/env python3
"""Compare SmartBranch360 requirements with captured Cisco CLI output."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements" / "requirements.yaml"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INPUT_ERROR = 2

Finding = tuple[str, str, tuple[str, ...]]


class InputConfigurationError(Exception):
    """Raised when a required file or configuration value is unusable."""


def normalize_interface(name: str) -> str:
    """Return a compact interface name for tolerant comparisons."""
    compact = re.sub(r"\s+", "", name).lower()
    prefixes = (
        "gigabitethernet",
        "gigabit",
        "gig",
        "gi",
        "g",
    )
    for prefix in prefixes:
        if compact.startswith(prefix):
            return "g" + compact[len(prefix) :]
    return compact


def require_mapping(value: Any, location: str) -> dict[str, Any]:
    """Require a YAML value to be a mapping."""
    if not isinstance(value, dict):
        raise InputConfigurationError(f"{location} must be a YAML mapping.")
    return value


def require_list(value: Any, location: str) -> list[Any]:
    """Require a YAML value to be a list."""
    if not isinstance(value, list):
        raise InputConfigurationError(f"{location} must be a YAML list.")
    return value


def require_keys(mapping: dict[str, Any], keys: Iterable[str], location: str) -> None:
    """Require a mapping to contain each named key."""
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise InputConfigurationError(
            f"{location} is missing required key(s): {', '.join(missing)}."
        )


def require_text(value: Any, location: str) -> str:
    """Require a non-empty string value."""
    if not isinstance(value, str) or not value.strip():
        raise InputConfigurationError(f"{location} must be a non-empty string.")
    return value.strip()


def require_vlan_id(value: Any, location: str) -> int:
    """Require an integer VLAN ID in Cisco's normal VLAN range."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4094:
        raise InputConfigurationError(
            f"{location} must be an integer between 1 and 4094."
        )
    return value


def require_ip_address(value: Any, location: str) -> str:
    """Require a valid IPv4 address and return its normalized text."""
    text = require_text(value, location)
    try:
        return str(ipaddress.IPv4Address(text))
    except ipaddress.AddressValueError as exc:
        raise InputConfigurationError(f"{location} is not a valid IPv4 address.") from exc


def require_ip_interface(value: Any, location: str) -> str:
    """Require a valid IPv4 interface in address/prefix form."""
    text = require_text(value, location)
    try:
        return str(ipaddress.IPv4Interface(text))
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
        raise InputConfigurationError(
            f"{location} is not a valid IPv4 interface address."
        ) from exc


def validate_requirements(config: Any) -> dict[str, Any]:
    """Validate the requirement sections used by the assurance checks."""
    root = require_mapping(config, "requirements")
    require_keys(
        root,
        (
            "site",
            "vlans",
            "router",
            "nat",
            "switch_management",
            "expected_trunks",
            "servers",
            "dhcp",
            "security_policy",
        ),
        "requirements",
    )

    site = require_mapping(root["site"], "site")
    require_keys(site, ("name",), "site")
    require_text(site["name"], "site.name")

    vlan_ids: set[int] = set()
    for index, value in enumerate(require_list(root["vlans"], "vlans")):
        vlan = require_mapping(value, f"vlans[{index}]")
        require_keys(vlan, ("id", "name", "subnet", "gateway"), f"vlans[{index}]")
        vlan_id = require_vlan_id(vlan["id"], f"vlans[{index}].id")
        if vlan_id in vlan_ids:
            raise InputConfigurationError(f"VLAN {vlan_id} is defined more than once.")
        vlan_ids.add(vlan_id)
        require_text(vlan["name"], f"vlans[{index}].name")
        subnet_text = require_text(vlan["subnet"], f"vlans[{index}].subnet")
        gateway = require_ip_address(vlan["gateway"], f"vlans[{index}].gateway")
        try:
            subnet = ipaddress.IPv4Network(subnet_text, strict=True)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as exc:
            raise InputConfigurationError(
                f"vlans[{index}].subnet is not a valid IPv4 network."
            ) from exc
        if ipaddress.IPv4Address(gateway) not in subnet:
            raise InputConfigurationError(
                f"vlans[{index}].gateway is not inside {subnet}."
            )

    router = require_mapping(root["router"], "router")
    require_keys(router, ("hostname", "interfaces"), "router")
    require_text(router["hostname"], "router.hostname")
    router_interfaces: set[str] = set()
    for index, value in enumerate(require_list(router["interfaces"], "router.interfaces")):
        interface = require_mapping(value, f"router.interfaces[{index}]")
        require_keys(interface, ("name", "ipv4_address"), f"router.interfaces[{index}]")
        name = require_text(interface["name"], f"router.interfaces[{index}].name")
        normalized_name = normalize_interface(name)
        if normalized_name in router_interfaces:
            raise InputConfigurationError(f"Router interface {name} is defined more than once.")
        router_interfaces.add(normalized_name)
        require_ip_interface(
            interface["ipv4_address"], f"router.interfaces[{index}].ipv4_address"
        )
        if "vlan" in interface:
            interface_vlan = require_vlan_id(
                interface["vlan"], f"router.interfaces[{index}].vlan"
            )
            if interface_vlan not in vlan_ids:
                raise InputConfigurationError(
                    f"router.interfaces[{index}].vlan references undefined VLAN "
                    f"{interface_vlan}."
                )

    nat = require_mapping(root["nat"], "nat")
    require_keys(nat, ("interfaces",), "nat")
    for index, value in enumerate(require_list(nat["interfaces"], "nat.interfaces")):
        interface = require_mapping(value, f"nat.interfaces[{index}]")
        require_keys(interface, ("name", "role"), f"nat.interfaces[{index}]")
        name = require_text(interface["name"], f"nat.interfaces[{index}].name")
        if normalize_interface(name) not in router_interfaces:
            raise InputConfigurationError(
                f"nat.interfaces[{index}].name references undefined router interface {name}."
            )
        role = require_text(interface["role"], f"nat.interfaces[{index}].role").lower()
        if role not in {"inside", "outside"}:
            raise InputConfigurationError(
                f"nat.interfaces[{index}].role must be inside or outside."
            )

    switch_management = require_mapping(root["switch_management"], "switch_management")
    require_keys(
        switch_management,
        ("default_gateway", "switches"),
        "switch_management",
    )
    require_ip_address(
        switch_management["default_gateway"], "switch_management.default_gateway"
    )
    switch_names: set[str] = set()
    for index, value in enumerate(
        require_list(switch_management["switches"], "switch_management.switches")
    ):
        switch = require_mapping(value, f"switch_management.switches[{index}]")
        require_keys(
            switch,
            ("hostname", "ipv4_address"),
            f"switch_management.switches[{index}]",
        )
        hostname = require_text(
            switch["hostname"], f"switch_management.switches[{index}].hostname"
        )
        switch_names.add(hostname.upper())
        require_ip_interface(
            switch["ipv4_address"],
            f"switch_management.switches[{index}].ipv4_address",
        )

    for index, value in enumerate(
        require_list(root["expected_trunks"], "expected_trunks")
    ):
        trunk = require_mapping(value, f"expected_trunks[{index}]")
        require_keys(
            trunk,
            ("switch", "interface", "allowed_vlans"),
            f"expected_trunks[{index}]",
        )
        switch = require_text(trunk["switch"], f"expected_trunks[{index}].switch")
        if switch.upper() not in switch_names:
            raise InputConfigurationError(
                f"expected_trunks[{index}].switch references undefined switch {switch}."
            )
        require_text(trunk["interface"], f"expected_trunks[{index}].interface")
        allowed = require_list(
            trunk["allowed_vlans"], f"expected_trunks[{index}].allowed_vlans"
        )
        for vlan_index, vlan_value in enumerate(allowed):
            vlan_id = require_vlan_id(
                vlan_value,
                f"expected_trunks[{index}].allowed_vlans[{vlan_index}]",
            )
            if vlan_id not in vlan_ids:
                raise InputConfigurationError(
                    f"expected_trunks[{index}] references undefined VLAN {vlan_id}."
                )

    for index, value in enumerate(require_list(root["servers"], "servers")):
        server = require_mapping(value, f"servers[{index}]")
        require_keys(server, ("name", "ipv4_address"), f"servers[{index}]")
        require_text(server["name"], f"servers[{index}].name")
        require_ip_address(server["ipv4_address"], f"servers[{index}].ipv4_address")

    dhcp = require_mapping(root["dhcp"], "dhcp")
    for role, value in dhcp.items():
        settings = require_mapping(value, f"dhcp.{role}")
        require_keys(settings, ("default_gateway",), f"dhcp.{role}")
        require_ip_address(settings["default_gateway"], f"dhcp.{role}.default_gateway")

    policy = require_mapping(root["security_policy"], "security_policy")
    require_keys(policy, ("traffic_rules", "ssh"), "security_policy")
    for index, value in enumerate(
        require_list(policy["traffic_rules"], "security_policy.traffic_rules")
    ):
        rule = require_mapping(value, f"security_policy.traffic_rules[{index}]")
        require_keys(
            rule,
            ("source", "destination", "action"),
            f"security_policy.traffic_rules[{index}]",
        )
        require_text(rule["source"], f"security_policy.traffic_rules[{index}].source")
        require_text(
            rule["destination"], f"security_policy.traffic_rules[{index}].destination"
        )
        require_text(rule["action"], f"security_policy.traffic_rules[{index}].action")
    ssh = require_mapping(policy["ssh"], "security_policy.ssh")
    require_keys(
        ssh,
        ("destination", "only_allowed_source"),
        "security_policy.ssh",
    )
    require_text(ssh["destination"], "security_policy.ssh.destination")
    require_ip_address(
        ssh["only_allowed_source"], "security_policy.ssh.only_allowed_source"
    )

    return root


def load_requirements(path: Path) -> dict[str, Any]:
    """Load and validate the intended design from YAML."""
    try:
        import yaml
    except ImportError as exc:
        raise InputConfigurationError(
            "PyYAML is required. Install it with: python -m pip install PyYAML"
        ) from exc

    if not path.is_file():
        raise InputConfigurationError(f"Requirements file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
        parsed = yaml.safe_load(text)
    except OSError as exc:
        raise InputConfigurationError(f"Cannot read requirements file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InputConfigurationError(f"Invalid YAML in {path}: {exc}") from exc
    return validate_requirements(parsed)


def resolve_script_relative_path(value: str, *, for_output: bool = False) -> Path:
    """Resolve a CLI path without depending on the process working directory."""
    supplied = Path(value).expanduser()
    if supplied.is_absolute():
        return supplied.resolve()

    parts = supplied.parts
    if parts and parts[0].lower() == SCRIPT_DIR.name.lower():
        return (PROJECT_ROOT / supplied).resolve()

    script_candidate = (SCRIPT_DIR / supplied).resolve()
    project_candidate = (PROJECT_ROOT / supplied).resolve()
    if not for_output and project_candidate.exists() and not script_candidate.exists():
        return project_candidate
    return script_candidate


def read_capture(path: Path, label: str) -> str:
    """Read a Cisco text capture without changing it."""
    if not path.is_file():
        raise InputConfigurationError(f"Missing {label} input file: {path}")
    try:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="cp1252")
    except OSError as exc:
        raise InputConfigurationError(f"Cannot read {label} input file {path}: {exc}") from exc
    if not text.strip():
        raise InputConfigurationError(f"{label} input file is empty: {path}")
    return text


def add_finding(
    findings: list[Finding], status: str, message: str, *details: str
) -> None:
    """Append one normalized PASS, WARN, or FAIL finding."""
    normalized_status = status.upper()
    if normalized_status not in {"PASS", "WARN", "FAIL"}:
        raise ValueError(f"Unsupported finding status: {status}")
    findings.append((normalized_status, message, tuple(details)))


def parse_vlan_brief(text: str) -> dict[int, str]:
    """Parse VLAN IDs and names from show vlan brief output."""
    vlans: dict[int, str] = {}
    line_pattern = re.compile(
        r"^\s*(\d{1,4})\s+(\S+)\s+(active|act/unsup|suspend|shutdown)\b",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = line_pattern.match(line)
        if match:
            vlan_id = int(match.group(1))
            if 1 <= vlan_id <= 4094:
                vlans[vlan_id] = match.group(2)
    return vlans


def expand_vlan_spec(specification: str) -> set[int]:
    """Expand a Cisco VLAN list such as 10,20,30-32 into integers."""
    compact = re.sub(r"\s+", "", specification).lower()
    if compact == "all":
        return set(range(1, 4095))
    if compact in {"", "none"}:
        return set()

    vlans: set[int] = set()
    for part in compact.split(","):
        if re.fullmatch(r"\d+", part):
            vlan_id = int(part)
            if 1 <= vlan_id <= 4094:
                vlans.add(vlan_id)
            continue
        range_match = re.fullmatch(r"(\d+)-(\d+)", part)
        if not range_match:
            raise ValueError(f"Invalid VLAN list element: {part}")
        start, end = (int(value) for value in range_match.groups())
        if start > end or start < 1 or end > 4094:
            raise ValueError(f"Invalid VLAN range: {part}")
        vlans.update(range(start, end + 1))
    return vlans


def parse_interfaces_trunk(text: str) -> dict[str, tuple[set[int], str]]:
    """Parse the 'Vlans allowed on trunk' table by interface."""
    trunks: dict[str, tuple[set[int], str]] = {}
    in_allowed_table = False
    vlan_spec_pattern = re.compile(
        r"^(?:all|none|\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*)$",
        re.IGNORECASE,
    )

    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^port\b", stripped, re.IGNORECASE):
            in_allowed_table = bool(
                re.search(r"vlans?\s+allowed\s+on\s+trunk", stripped, re.IGNORECASE)
            )
            continue
        if not in_allowed_table or not stripped:
            continue

        row = re.match(r"^(\S+)\s+(.+?)\s*$", stripped)
        if not row:
            continue
        interface_name, raw_spec = row.groups()
        if not vlan_spec_pattern.fullmatch(raw_spec):
            continue
        try:
            allowed = expand_vlan_spec(raw_spec)
        except ValueError:
            continue
        canonical_name = normalize_interface(interface_name)
        if canonical_name in trunks:
            previous_vlans, previous_spec = trunks[canonical_name]
            allowed |= previous_vlans
            raw_spec = f"{previous_spec},{raw_spec}"
        trunks[canonical_name] = (allowed, re.sub(r"\s+", "", raw_spec))
    return trunks


def parse_ip_interface_brief(text: str) -> dict[str, str]:
    """Parse interface IPv4 addresses from show ip interface brief."""
    addresses: dict[str, str] = {}
    line_pattern = re.compile(r"^\s*(\S+)\s+(\S+)")
    for line in text.splitlines():
        match = line_pattern.match(line)
        if not match:
            continue
        interface_name, address = match.groups()
        if address.lower() == "unassigned":
            addresses[normalize_interface(interface_name)] = "unassigned"
            continue
        try:
            normalized_address = str(ipaddress.IPv4Address(address))
        except ipaddress.AddressValueError:
            continue
        addresses[normalize_interface(interface_name)] = normalized_address
    return addresses


def extract_stanza_blocks(
    text: str, heading_pattern: re.Pattern[str]
) -> list[tuple[re.Match[str], str]]:
    """Extract exclamation-delimited Cisco configuration stanzas."""
    matches = list(heading_pattern.finditer(text))
    blocks: list[tuple[re.Match[str], str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        candidate = text[start:end]
        terminator = re.search(r"(?m)^[ \t]*![ \t]*$", candidate)
        if terminator:
            candidate = candidate[: terminator.start()]
        blocks.append((match, candidate))
    return blocks


def parse_interface_blocks(config_text: str) -> dict[str, str]:
    """Return running-config interface stanzas by canonical name."""
    heading = re.compile(r"(?im)^[ \t]*interface[ \t]+(\S+)[ \t]*$")
    return {
        normalize_interface(match.group(1)): body
        for match, body in extract_stanza_blocks(config_text, heading)
    }


def parse_dhcp_pools(config_text: str) -> dict[str, str]:
    """Return DHCP pool configuration bodies by pool name."""
    heading = re.compile(r"(?im)^[ \t]*ip[ \t]+dhcp[ \t]+pool[ \t]+(\S+)[ \t]*$")
    return {
        match.group(1): body for match, body in extract_stanza_blocks(config_text, heading)
    }


def parse_named_acls(config_text: str) -> dict[str, tuple[str, str]]:
    """Return named standard and extended ACL configuration blocks."""
    heading = re.compile(
        r"(?im)^[ \t]*ip[ \t]+access-list[ \t]+(?:standard|extended)"
        r"[ \t]+(\S+)[ \t]*$"
    )
    return {
        match.group(1).lower(): (match.group(1), body)
        for match, body in extract_stanza_blocks(config_text, heading)
    }


def parse_vty_blocks(config_text: str) -> list[tuple[str, str]]:
    """Return line VTY ranges and their configuration bodies."""
    heading = re.compile(
        r"(?im)^[ \t]*line[ \t]+vty[ \t]+(\d+(?:[ \t]+\d+)?)[ \t]*$"
    )
    return [
        (match.group(1), body)
        for match, body in extract_stanza_blocks(config_text, heading)
    ]


def normalized_config_lines(body: str) -> list[str]:
    """Normalize whitespace and case for exact Cisco statement checks."""
    return [
        " ".join(line.strip().lower().split())
        for line in body.splitlines()
        if line.strip()
    ]


def check_vlans(
    requirements: dict[str, Any],
    vlan_outputs: dict[str, str],
    findings: list[Finding],
) -> None:
    """Check every required VLAN ID on each supplied switch."""
    expected_vlans = requirements["vlans"]
    expected_ids = {int(vlan["id"]) for vlan in expected_vlans}
    expected_display = ",".join(str(vlan_id) for vlan_id in sorted(expected_ids))

    for switch, text in vlan_outputs.items():
        observed = parse_vlan_brief(text)
        observed_display = ",".join(str(vlan_id) for vlan_id in sorted(observed)) or "none"
        for vlan in expected_vlans:
            vlan_id = int(vlan["id"])
            vlan_name = str(vlan["name"])
            if vlan_id in observed:
                add_finding(
                    findings,
                    "PASS",
                    f"VLAN {vlan_id} {vlan_name} found on {switch}",
                )
            else:
                add_finding(
                    findings,
                    "FAIL",
                    f"VLAN {vlan_id} {vlan_name} missing from {switch}",
                    f"Expected VLAN IDs: {expected_display}",
                    f"Observed VLAN IDs: {observed_display}",
                    f"Suggested fix: Create VLAN {vlan_id} on {switch}.",
                )


def check_trunks(
    requirements: dict[str, Any],
    trunk_outputs: dict[str, str],
    findings: list[Finding],
) -> None:
    """Check that each intended trunk permits every expected VLAN."""
    parsed_outputs = {
        switch.upper(): parse_interfaces_trunk(text)
        for switch, text in trunk_outputs.items()
    }

    for trunk in requirements["expected_trunks"]:
        switch = str(trunk["switch"])
        interface = str(trunk["interface"])
        expected = {int(vlan_id) for vlan_id in trunk["allowed_vlans"]}
        expected_display = ",".join(str(vlan_id) for vlan_id in sorted(expected))
        observed_entry = parsed_outputs.get(switch.upper(), {}).get(
            normalize_interface(interface)
        )

        if observed_entry is None:
            add_finding(
                findings,
                "FAIL",
                f"Trunk {switch} {interface} not found",
                f"Expected allowed VLANs: {expected_display}",
                "Observed: trunk interface or allowed-VLAN table not found",
                f"Suggested fix: Verify {interface} is trunking and capture "
                "show interfaces trunk.",
            )
            continue

        observed, raw_observed = observed_entry
        observed_display = (
            raw_observed.lower()
            if raw_observed.lower() in {"all", "none"}
            else ",".join(str(vlan_id) for vlan_id in sorted(observed)) or "none"
        )
        missing = sorted(expected - observed)
        if not missing:
            add_finding(
                findings,
                "PASS",
                f"Trunk {switch} {interface} allows VLANs {expected_display}",
            )
            continue

        for vlan_id in missing:
            symptom = (
                "Guest connectivity may fail."
                if vlan_id == 20
                else f"Traffic for VLAN {vlan_id} may fail."
            )
            add_finding(
                findings,
                "FAIL",
                f"VLAN {vlan_id} missing from trunk {switch} {interface}",
                f"Expected: {expected_display}",
                f"Observed: {observed_display}",
                f"Symptom: {symptom}",
                f"Suggested fix: Add VLAN {vlan_id} to the allowed trunk VLAN list.",
            )


def check_router_interfaces(
    requirements: dict[str, Any], text: str, findings: list[Finding]
) -> None:
    """Check R1 interface addresses from show ip interface brief."""
    observed = parse_ip_interface_brief(text)
    hostname = str(requirements["router"]["hostname"])

    for interface in requirements["router"]["interfaces"]:
        name = str(interface["name"])
        expected = str(ipaddress.IPv4Interface(interface["ipv4_address"]).ip)
        actual = observed.get(normalize_interface(name))
        address_label = "gateway" if "vlan" in interface else "address"
        if actual == expected:
            add_finding(
                findings,
                "PASS",
                f"{hostname} {name} {address_label} is {expected}",
            )
        elif actual is None:
            add_finding(
                findings,
                "FAIL",
                f"{hostname} {name} missing from show ip interface brief",
                f"Expected: {expected}",
                "Observed: interface not found",
            )
        else:
            add_finding(
                findings,
                "FAIL",
                f"{hostname} {name} has the wrong {address_label}",
                f"Expected: {expected}",
                f"Observed: {actual}",
                f"Suggested fix: Configure {name} with {interface['ipv4_address']}.",
            )


def check_nat(
    requirements: dict[str, Any], config_text: str, findings: list[Finding]
) -> None:
    """Check ip nat inside/outside statements on intended interfaces."""
    blocks = parse_interface_blocks(config_text)
    hostname = str(requirements["router"]["hostname"])

    for interface in requirements["nat"]["interfaces"]:
        name = str(interface["name"])
        expected_role = str(interface["role"]).lower()
        body = blocks.get(normalize_interface(name))
        expected_statement = f"ip nat {expected_role}"
        if body is None:
            add_finding(
                findings,
                "FAIL",
                f"{hostname} {name} configuration block not found for NAT check",
                f"Expected: {expected_statement}",
            )
            continue

        lines = normalized_config_lines(body)
        observed_roles = [
            line.removeprefix("ip nat ")
            for line in lines
            if line in {"ip nat inside", "ip nat outside"}
        ]
        if expected_statement in lines:
            add_finding(
                findings,
                "PASS",
                f"{hostname} {name} has {expected_statement}",
            )
        else:
            observed_text = ", ".join(observed_roles) if observed_roles else "not configured"
            add_finding(
                findings,
                "FAIL",
                f"{hostname} {name} NAT role is incorrect",
                f"Expected: {expected_role}",
                f"Observed: {observed_text}",
                f"Suggested fix: Add '{expected_statement}' under interface {name}.",
            )


def normalized_identifier(value: str) -> str:
    """Normalize labels such as EMPLOYEE_POOL for loose role matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def extract_default_routers(pool_body: str) -> list[str]:
    """Extract IPv4 values from DHCP default-router commands."""
    routers: list[str] = []
    for line in pool_body.splitlines():
        match = re.match(r"^\s*default-router\s+(.+?)\s*$", line, re.IGNORECASE)
        if not match:
            continue
        for token in match.group(1).split():
            try:
                routers.append(str(ipaddress.IPv4Address(token)))
            except ipaddress.AddressValueError:
                continue
    return routers


def check_dhcp(
    requirements: dict[str, Any], config_text: str, findings: list[Finding]
) -> None:
    """Check DHCP default routers when matching pool configuration is captured."""
    pools = parse_dhcp_pools(config_text)
    if not pools:
        add_finding(
            findings,
            "WARN",
            "DHCP checks skipped because no ip dhcp pool configuration was captured",
        )
        return

    for role, settings in requirements["dhcp"].items():
        role_key = normalized_identifier(str(role))
        matches = [
            (name, body)
            for name, body in pools.items()
            if role_key in normalized_identifier(name)
        ]
        if not matches:
            add_finding(
                findings,
                "WARN",
                f"DHCP {str(role).title()} pool could not be identified",
                "No matching pool name was found in the captured running configuration.",
            )
            continue

        expected = str(settings["default_gateway"])
        observed = sorted(
            {
                address
                for _, body in matches
                for address in extract_default_routers(body)
            }
        )
        pool_names = ", ".join(name for name, _ in matches)
        if expected in observed:
            add_finding(
                findings,
                "PASS",
                f"DHCP {str(role).title()} default gateway is {expected}",
            )
        elif not observed:
            add_finding(
                findings,
                "WARN",
                f"DHCP {str(role).title()} default-router statement was not captured",
                f"Matched pool: {pool_names}",
            )
        else:
            add_finding(
                findings,
                "FAIL",
                f"DHCP {str(role).title()} default gateway is incorrect",
                f"Expected: {expected}",
                f"Observed: {','.join(observed)}",
                f"Suggested fix: Set default-router {expected} in pool {pool_names}.",
            )


def acl_is_defined(
    config_text: str,
    acl_name: str,
    named_acls: dict[str, tuple[str, str]],
) -> bool:
    """Return whether a named or numbered ACL definition exists."""
    if acl_name.lower() in named_acls:
        return True
    return bool(
        re.search(
            rf"(?im)^[ \t]*access-list[ \t]+{re.escape(acl_name)}(?:[ \t]+|$)",
            config_text,
        )
    )


def acl_rule_lines(
    config_text: str,
    acl_name: str,
    named_acls: dict[str, tuple[str, str]],
) -> list[str]:
    """Return normalized rule lines for a named or numbered ACL."""
    named = named_acls.get(acl_name.lower())
    if named:
        lines = normalized_config_lines(named[1])
        return [re.sub(r"^\d+\s+", "", line) for line in lines]

    rules: list[str] = []
    pattern = re.compile(
        rf"(?im)^[ \t]*access-list[ \t]+{re.escape(acl_name)}[ \t]+(.+?)\s*$"
    )
    for match in pattern.finditer(config_text):
        rules.append(" ".join(match.group(1).lower().split()))
    return rules


def check_guest_acl(
    requirements: dict[str, Any], config_text: str, findings: list[Finding]
) -> None:
    """Check that a defined ACL is applied inbound to the Guest subinterface."""
    guest_interface = next(
        (
            str(interface["name"])
            for interface in requirements["router"]["interfaces"]
            if interface.get("vlan") == 20
        ),
        "G0/0.20",
    )
    blocks = parse_interface_blocks(config_text)
    body = blocks.get(normalize_interface(guest_interface))
    if body is None:
        add_finding(
            findings,
            "WARN",
            f"Guest ACL check skipped because {guest_interface} configuration was not captured",
        )
        return

    applications = [
        (match.group(1), match.group(2).lower())
        for match in re.finditer(
            r"(?im)^[ \t]*ip[ \t]+access-group[ \t]+(\S+)[ \t]+(in|out)[ \t]*$",
            body,
        )
    ]
    inbound = [name for name, direction in applications if direction == "in"]
    named_acls = parse_named_acls(config_text)

    if inbound:
        acl_name = inbound[0]
        if acl_is_defined(config_text, acl_name, named_acls):
            add_finding(
                findings,
                "PASS",
                f"Guest ACL {acl_name} exists and is applied inbound to {guest_interface}",
            )
        else:
            add_finding(
                findings,
                "FAIL",
                f"Guest ACL {acl_name} is applied inbound but its definition is missing",
                f"Interface: {guest_interface}",
                f"Suggested fix: Define ACL {acl_name} or apply the correct Guest ACL.",
            )
        return

    guest_acl_names = [
        original_name
        for original_name, _ in named_acls.values()
        if "guest" in original_name.lower()
    ]
    if applications or guest_acl_names:
        observed = (
            ", ".join(f"{name} {direction}" for name, direction in applications)
            if applications
            else "no ip access-group statement"
        )
        add_finding(
            findings,
            "FAIL",
            f"Guest ACL is not applied inbound to {guest_interface}",
            f"Observed: {observed}",
            f"Suggested fix: Apply the Guest ACL inbound on {guest_interface}.",
        )
    else:
        add_finding(
            findings,
            "WARN",
            "Guest ACL check skipped because no relevant ACL statements were captured",
        )


def permit_is_only_source(rule: str, allowed_source: str) -> bool:
    """Recognize simple standard or SSH-only permits for one host."""
    escaped_ip = re.escape(allowed_source)
    patterns = (
        rf"permit host {escaped_ip}(?: log)?",
        rf"permit {escaped_ip}(?: 0\.0\.0\.0)?(?: log)?",
        rf"permit tcp host {escaped_ip} any(?: eq (?:22|ssh))?(?: log)?",
        rf"permit tcp {escaped_ip} 0\.0\.0\.0 any(?: eq (?:22|ssh))?(?: log)?",
    )
    return any(re.fullmatch(pattern, rule) for pattern in patterns)


def check_ssh_management(
    requirements: dict[str, Any], config_text: str, findings: list[Finding]
) -> None:
    """Check VTY SSH access-class rules against the sole allowed source."""
    allowed_source = str(
        requirements["security_policy"]["ssh"]["only_allowed_source"]
    )
    vty_blocks = parse_vty_blocks(config_text)
    if not vty_blocks:
        add_finding(
            findings,
            "WARN",
            "SSH management check skipped because no line vty configuration was captured",
        )
        return

    transport_statements: list[str] = []
    ssh_blocks: list[tuple[str, str]] = []
    for line_range, body in vty_blocks:
        transports = re.findall(
            r"(?im)^[ \t]*transport[ \t]+input[ \t]+(.+?)\s*$", body
        )
        transport_statements.extend(transports)
        if any("ssh" in statement.lower().split() for statement in transports):
            ssh_blocks.append((line_range, body))

    if not transport_statements:
        add_finding(
            findings,
            "WARN",
            "SSH management check skipped because transport input statements were not captured",
        )
        return
    if not ssh_blocks:
        add_finding(
            findings,
            "FAIL",
            "VTY lines do not permit SSH",
            f"Observed transport input: {', '.join(transport_statements)}",
        )
        return

    named_acls = parse_named_acls(config_text)
    problems: list[str] = []
    checked_acls: set[str] = set()

    for line_range, body in ssh_blocks:
        inbound_classes = re.findall(
            r"(?im)^[ \t]*access-class[ \t]+(\S+)[ \t]+in[ \t]*$", body
        )
        if not inbound_classes:
            problems.append(f"line vty {line_range} has no inbound access-class")
            continue
        for acl_name in inbound_classes:
            if acl_name.lower() in checked_acls:
                continue
            checked_acls.add(acl_name.lower())
            if not acl_is_defined(config_text, acl_name, named_acls):
                problems.append(f"ACL {acl_name} is referenced but not defined")
                continue
            rules = acl_rule_lines(config_text, acl_name, named_acls)
            permit_rules = [rule for rule in rules if rule.startswith("permit ")]
            allowed_permit = any(
                permit_is_only_source(rule, allowed_source) for rule in permit_rules
            )
            extra_permits = [
                rule
                for rule in permit_rules
                if not permit_is_only_source(rule, allowed_source)
            ]
            if not allowed_permit:
                problems.append(f"ACL {acl_name} does not permit host {allowed_source}")
            if extra_permits:
                problems.append(
                    f"ACL {acl_name} contains additional permit rules: "
                    + "; ".join(extra_permits)
                )

    if problems:
        add_finding(
            findings,
            "FAIL",
            "SSH management restriction is not correctly configured",
            *problems,
            f"Expected only allowed source: {allowed_source}",
        )
    else:
        add_finding(
            findings,
            "PASS",
            f"SSH access to network devices is restricted to {allowed_source}",
        )


def render_results(findings: list[Finding]) -> str:
    """Render findings and the final assurance summary as plain text."""
    lines: list[str] = []
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for status, message, details in findings:
        counts[status] += 1
        lines.append(f"[{status}] {message}")
        lines.extend(f"       {detail}" for detail in details)
        lines.append("")

    separator = "=" * 50
    overall = "FAIL" if counts["FAIL"] else "PASS"
    lines.extend(
        (
            separator,
            "SmartBranch 360 Assurance Summary",
            separator,
            f"Checks passed: {counts['PASS']}",
            f"Warnings:      {counts['WARN']}",
            f"Checks failed: {counts['FAIL']}",
            f"Overall: {overall}",
            separator,
        )
    )
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line parser and documented input overrides."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare SmartBranch360 requirements with captured Cisco Packet "
            "Tracer show-command output. Relative paths are resolved from the "
            "python_checker directory."
        )
    )
    parser.add_argument(
        "--sw1-vlan",
        default="sample_inputs/sw1_vlan.txt",
        help="SW1 show vlan brief capture",
    )
    parser.add_argument(
        "--sw2-vlan",
        default="sample_inputs/sw2_vlan.txt",
        help="SW2 show vlan brief capture",
    )
    parser.add_argument(
        "--sw1-trunk",
        default="sample_inputs/sw1_trunk_good.txt",
        help="SW1 show interfaces trunk capture",
    )
    parser.add_argument(
        "--sw2-trunk",
        default="sample_inputs/sw2_trunk.txt",
        help="SW2 show interfaces trunk capture",
    )
    parser.add_argument(
        "--r1-ip-brief",
        default="sample_inputs/r1_interfaces.txt",
        help="R1 show ip interface brief capture",
    )
    parser.add_argument(
        "--r1-running-config",
        default="sample_inputs/r1_running_config.txt",
        help="R1 show running-config capture",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        help="write the same findings and summary to a plain-text report",
    )
    return parser


def load_capture_set(args: argparse.Namespace) -> dict[str, str]:
    """Resolve and read every mandatory Cisco capture."""
    requested = {
        "sw1_vlan": (args.sw1_vlan, "SW1 show vlan brief"),
        "sw2_vlan": (args.sw2_vlan, "SW2 show vlan brief"),
        "sw1_trunk": (args.sw1_trunk, "SW1 show interfaces trunk"),
        "sw2_trunk": (args.sw2_trunk, "SW2 show interfaces trunk"),
        "r1_ip_brief": (args.r1_ip_brief, "R1 show ip interface brief"),
        "r1_running_config": (args.r1_running_config, "R1 show running-config"),
    }
    return {
        key: read_capture(resolve_script_relative_path(path), label)
        for key, (path, label) in requested.items()
    }


def run_checks(requirements: dict[str, Any], captures: dict[str, str]) -> list[Finding]:
    """Run all mandatory and evidence-dependent assurance checks."""
    findings: list[Finding] = []
    check_vlans(
        requirements,
        {"SW1": captures["sw1_vlan"], "SW2": captures["sw2_vlan"]},
        findings,
    )
    check_trunks(
        requirements,
        {"SW1": captures["sw1_trunk"], "SW2": captures["sw2_trunk"]},
        findings,
    )
    check_router_interfaces(requirements, captures["r1_ip_brief"], findings)
    check_nat(requirements, captures["r1_running_config"], findings)
    check_dhcp(requirements, captures["r1_running_config"], findings)
    check_guest_acl(requirements, captures["r1_running_config"], findings)
    check_ssh_management(requirements, captures["r1_running_config"], findings)
    return findings


def write_report(path_value: str, content: str) -> Path:
    """Write the rendered findings to a user-selected plain-text file."""
    path = resolve_script_relative_path(path_value, for_output=True)
    input_directory = (SCRIPT_DIR / "sample_inputs").resolve()
    protected_files = {Path(__file__).resolve(), REQUIREMENTS_PATH.resolve()}
    try:
        path.relative_to(input_directory)
        inside_input_directory = True
    except ValueError:
        inside_input_directory = False
    if inside_input_directory or path in protected_files or path.suffix.lower() == ".pkt":
        raise InputConfigurationError(
            f"Refusing to overwrite a protected input or project file: {path}"
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
    except OSError as exc:
        raise InputConfigurationError(f"Cannot write report {path}: {exc}") from exc
    return path


def main(argv: list[str] | None = None) -> int:
    """Run the checker and return its documented process exit code."""
    args = build_argument_parser().parse_args(argv)
    try:
        requirements = load_requirements(REQUIREMENTS_PATH)
        captures = load_capture_set(args)
        findings = run_checks(requirements, captures)
        output = render_results(findings)
        print(output)
        if args.report:
            report_path = write_report(args.report, output)
            print(f"\n[INFO] Report written to {report_path}")
    except InputConfigurationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR

    return EXIT_FAIL if any(status == "FAIL" for status, _, _ in findings) else EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
