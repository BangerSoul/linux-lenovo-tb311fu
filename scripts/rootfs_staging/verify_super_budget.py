#!/usr/bin/env python3
"""
rootfs_staging/verify_super_budget.py - Dynamic Super Partition Headroom & Budget Auditor
Target: Lenovo Tab M11 (TB311FU / poplar, MediaTek Helio G88 / MT8786 / MT6768)

Validates:
- 4.0 GiB (4,294,967,296 bytes) system_a allocation fits within 6.57 GB dynamic headroom in main_a.
- Minimum safety margin >= 2.0 GB (actual: ~2.57 GB remaining).
- Total logical partitions fit inside physical 11.81 GB super partition.
- Strict sector (512-byte) and page (4096-byte) alignment.
- Preservation of stock product_a (~1.71 GB) partition.
"""

from dataclasses import dataclass, field
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

SECTOR_SIZE = 512
PAGE_SIZE = 4096

# Physical Super & Group Geometry (from device lpdump & scatter)
SUPER_PHYSICAL_BYTES = 11811160064       # 11.00 GiB / 11.81 GB (23,068,672 sectors)
GROUP_MAIN_A_MAX_BYTES = 11809062912     # 11.00 GiB (23,064,576 sectors)
INITIAL_UNALLOCATED_HEADROOM = 7050133504 # ~6.566 GiB / ~6.57 GB (13,769,792 sectors)
ALT_INITIAL_HEADROOM = 7055745024        # ~6.571 GB (13,780,752 sectors)

SYSTEM_A_TARGET_BYTES = 4294967296       # 4.0 GiB exact (8,388,608 sectors, 1,048,576 4K blocks)
PRODUCT_A_PRESERVED_BYTES = 1836695552   # ~1.71 GB (3,587,296 sectors)
MIN_HEADROOM_SAFETY_MARGIN = 2000000000  # 2.00 GB mandatory minimum safety margin


@dataclass
class SuperBudgetReport:
    physical_super_bytes: int
    group_main_a_max_bytes: int
    initial_headroom_bytes: int
    target_system_a_bytes: int
    product_a_bytes: int
    remaining_headroom_bytes: int
    remaining_margin_gib: float
    total_allocated_bytes: int
    sector_aligned: bool
    page_aligned: bool
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "physical_super_bytes": self.physical_super_bytes,
            "physical_super_gib": round(self.physical_super_bytes / (1024**3), 3),
            "group_main_a_max_bytes": self.group_main_a_max_bytes,
            "initial_headroom_bytes": self.initial_headroom_bytes,
            "initial_headroom_gib": round(self.initial_headroom_bytes / (1024**3), 3),
            "target_system_a_bytes": self.target_system_a_bytes,
            "target_system_a_gib": round(self.target_system_a_bytes / (1024**3), 3),
            "product_a_bytes": self.product_a_bytes,
            "product_a_gib": round(self.product_a_bytes / (1024**3), 3),
            "remaining_headroom_bytes": self.remaining_headroom_bytes,
            "remaining_margin_gib": self.remaining_margin_gib,
            "total_allocated_bytes": self.total_allocated_bytes,
            "sector_aligned": self.sector_aligned,
            "page_aligned": self.page_aligned,
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def audit_super_budget(
    target_system_a_bytes: int = SYSTEM_A_TARGET_BYTES,
    initial_headroom_bytes: int = INITIAL_UNALLOCATED_HEADROOM,
    physical_super_bytes: int = SUPER_PHYSICAL_BYTES,
    group_max_bytes: int = GROUP_MAIN_A_MAX_BYTES,
    product_a_bytes: int = PRODUCT_A_PRESERVED_BYTES,
    min_safety_margin: int = MIN_HEADROOM_SAFETY_MARGIN
) -> SuperBudgetReport:
    """Audit dynamic super partition budget and headroom constraints."""
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Alignment verification
    sector_aligned = (target_system_a_bytes % SECTOR_SIZE == 0)
    if not sector_aligned:
        errors.append(f"Target system_a size ({target_system_a_bytes}) is not 512-byte sector aligned")

    page_aligned = (target_system_a_bytes % PAGE_SIZE == 0)
    if not page_aligned:
        errors.append(f"Target system_a size ({target_system_a_bytes}) is not 4096-byte page aligned")

    # 2. Capacity verification
    if target_system_a_bytes > physical_super_bytes:
        errors.append(f"Target system_a size ({target_system_a_bytes}) exceeds physical super capacity ({physical_super_bytes})")

    if target_system_a_bytes > initial_headroom_bytes:
        errors.append(f"Target system_a size ({target_system_a_bytes}) overflows available dynamic headroom ({initial_headroom_bytes})")

    # 3. Headroom & safety margin arithmetic
    remaining_headroom = initial_headroom_bytes - target_system_a_bytes
    remaining_margin_gib = round(remaining_headroom / (1024**3), 3)

    if remaining_headroom < min_safety_margin:
        errors.append(
            f"Insufficient safety headroom: {remaining_headroom} bytes remaining "
            f"({remaining_margin_gib} GiB), minimum required is {min_safety_margin} bytes"
        )

    # 4. Total logical partitions fit in super
    total_allocated = target_system_a_bytes + product_a_bytes
    if total_allocated > physical_super_bytes:
        errors.append(f"Total allocated partitions ({total_allocated}) exceeds physical super ({physical_super_bytes})")

    # 5. Product_a preservation
    if product_a_bytes < 1700000000:
        errors.append(f"Stock product_a partition ({product_a_bytes} bytes) is below minimum threshold (1.70 GB)")

    is_valid = (len(errors) == 0)

    return SuperBudgetReport(
        physical_super_bytes=physical_super_bytes,
        group_main_a_max_bytes=group_max_bytes,
        initial_headroom_bytes=initial_headroom_bytes,
        target_system_a_bytes=target_system_a_bytes,
        product_a_bytes=product_a_bytes,
        remaining_headroom_bytes=remaining_headroom,
        remaining_margin_gib=remaining_margin_gib,
        total_allocated_bytes=total_allocated,
        sector_aligned=sector_aligned,
        page_aligned=page_aligned,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )


def format_markdown_report(report: SuperBudgetReport) -> str:
    status_str = "PASS" if report.is_valid else "FAIL"
    lines = [
        f"# Dynamic Super Partition Budget Audit Report — {status_str}",
        "",
        "## Summary Metrics",
        f"- **Physical Super Capacity**: {report.physical_super_bytes:,} bytes ({round(report.physical_super_bytes / (1024**3), 2)} GiB)",
        f"- **Dynamic Group main_a Max**: {report.group_main_a_max_bytes:,} bytes ({round(report.group_main_a_max_bytes / (1024**3), 2)} GiB)",
        f"- **Initial Dynamic Unallocated Headroom**: {report.initial_headroom_bytes:,} bytes ({round(report.initial_headroom_bytes / (1024**3), 2)} GiB)",
        f"- **PostmarketOS Plasma Mobile (system_a)**: {report.target_system_a_bytes:,} bytes ({round(report.target_system_a_bytes / (1024**3), 2)} GiB)",
        f"- **Preserved Stock product_a**: {report.product_a_bytes:,} bytes ({round(report.product_a_bytes / (1024**3), 2)} GiB)",
        f"- **Post-Flash Remaining Headroom**: {report.remaining_headroom_bytes:,} bytes ({report.remaining_margin_gib} GiB)",
        f"- **Safety Margin Standard**: >= 2.00 GB (Actual: {report.remaining_margin_gib} GiB)",
        f"- **Sector Aligned (512 B)**: {'YES' if report.sector_aligned else 'NO'}",
        f"- **Page Aligned (4096 B)**: {'YES' if report.page_aligned else 'NO'}",
        f"- **Audit Status**: **{status_str}**",
        ""
    ]
    if report.errors:
        lines.append("## Errors")
        for err in report.errors:
            lines.append(f"- [FAIL] {err}")
        lines.append("")
    if report.warnings:
        lines.append("## Warnings")
        for warn in report.warnings:
            lines.append(f"- [WARN] {warn}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Audit Dynamic Super Partition Budget")
    parser.add_argument("--target-size", type=int, default=SYSTEM_A_TARGET_BYTES, help="Target system_a size in bytes")
    parser.add_argument("--json", dest="emit_json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    report = audit_super_budget(target_system_a_bytes=args.target_size)
    if args.emit_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_markdown_report(report))

    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
