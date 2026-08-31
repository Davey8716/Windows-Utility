from __future__ import annotations

import subprocess
import webbrowser
from ipaddress import IPv4Address


class RouterService:
    @staticmethod
    def parse_default_gateway(ipconfig_output: str) -> str | None:
        for line in ipconfig_output.splitlines():
            if "Default Gateway" not in line:
                continue
            _label, separator, raw_gateway = line.partition(":")
            if not separator:
                continue
            gateway = raw_gateway.strip()
            try:
                parsed = IPv4Address(gateway)
            except ValueError:
                continue
            if not parsed.is_unspecified:
                return str(parsed)
        return None

    def detect_default_gateway(self) -> str | None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        output = subprocess.check_output(
            "ipconfig", text=True, errors="ignore", startupinfo=startupinfo
        )
        return self.parse_default_gateway(output)

    def open_router_page(self) -> str | None:
        try:
            gateway = self.detect_default_gateway()
            if gateway:
                webbrowser.open(f"http://{gateway}")
                print(f"[ROUTER] Opening router at {gateway}")
                return gateway
            print("[ROUTER] No default gateway found")
            return None
        except Exception as exc:
            print("[ROUTER] Failed:", exc)
            return None
