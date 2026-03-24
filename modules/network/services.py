"""Network management services: ports, proxy, connections, firewall."""

import asyncio
import os
import re


async def get_listening_ports() -> list[dict]:
    """Parse `ss -tlnp` output into structured listening port info.

    Returns:
        List of dicts with proto, local_addr, port, pid, process.
    """
    proc = await asyncio.create_subprocess_exec(
        "ss", "-tlnp",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ss command failed: {stderr.decode().strip()}")

    results = []
    lines = stdout.decode().strip().splitlines()

    for line in lines[1:]:  # skip header
        parts = line.split()
        if len(parts) < 5:
            continue

        proto = parts[0]
        local_addr_port = parts[3]

        # Parse address:port - handle IPv6 [::]:port and *:port
        if local_addr_port.startswith("["):
            # IPv6: [::]:8080
            match = re.match(r"\[(.+)\]:(\d+)", local_addr_port)
            if match:
                local_addr = match.group(1)
                port = int(match.group(2))
            else:
                continue
        elif local_addr_port.count(":") == 1:
            addr_part, port_str = local_addr_port.rsplit(":", 1)
            local_addr = addr_part
            port = int(port_str)
        else:
            continue

        # Parse process info from users:(("name",pid=N,...))
        pid = None
        process = None
        users_match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        if users_match:
            process = users_match.group(1)
            pid = int(users_match.group(2))

        results.append({
            "proto": proto,
            "local_addr": local_addr,
            "port": port,
            "pid": pid,
            "process": process,
        })

    return results


async def get_proxy_status() -> dict:
    """Check proxy configuration and clash process status.

    Returns:
        Dict with http_proxy, https_proxy values and clash running status.
    """
    http_proxy = os.environ.get("http_proxy", "")
    https_proxy = os.environ.get("https_proxy", "")

    # Check if clash is running
    proc = await asyncio.create_subprocess_exec(
        "pgrep", "-x", "clash",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    clash_running = proc.returncode == 0
    clash_pid = stdout.decode().strip().splitlines()[0] if clash_running and stdout else None

    return {
        "http_proxy": http_proxy or None,
        "https_proxy": https_proxy or None,
        "proxy_configured": bool(http_proxy or https_proxy),
        "clash_running": clash_running,
        "clash_pid": int(clash_pid) if clash_pid else None,
    }


async def get_connections_summary() -> dict:
    """Parse `ss -s` output for connection statistics.

    Returns:
        Dict with connection type counts.
    """
    proc = await asyncio.create_subprocess_exec(
        "ss", "-s",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ss -s failed: {stderr.decode().strip()}")

    output = stdout.decode()
    summary = {"raw": output}

    # Parse TCP line: TCP: N (estab M, closed K, ...)
    tcp_match = re.search(
        r"TCP:\s+(\d+)\s+\(estab\s+(\d+),\s+closed\s+(\d+),\s+orphaned\s+(\d+),\s+timewait\s+(\d+)\)",
        output,
    )
    if tcp_match:
        summary["tcp"] = {
            "total": int(tcp_match.group(1)),
            "established": int(tcp_match.group(2)),
            "closed": int(tcp_match.group(3)),
            "orphaned": int(tcp_match.group(4)),
            "timewait": int(tcp_match.group(5)),
        }

    # Parse total/UDP/etc
    for proto in ("UDP", "RAW", "FRAG"):
        match = re.search(rf"{proto}:\s+(\d+)", output)
        if match:
            summary[proto.lower()] = {"total": int(match.group(1))}

    return summary


async def get_firewall_rules() -> str:
    """Get iptables firewall rules.

    Returns:
        Raw iptables output text.
    """
    proc = await asyncio.create_subprocess_exec(
        "sudo", "iptables", "-L", "-n", "--line-numbers",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"iptables failed: {stderr.decode().strip()}")

    return stdout.decode()
