#!/usr/bin/env python3
"""
Data Validation Script for ETA Training Data

Runs comprehensive validation checks on processed ETA training data,
focusing on calculation verification and edge case detection.
"""

import argparse
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


class Severity(IntEnum):
    """Severity levels for validation findings."""
    CRITICAL = 4  # Must fix before training
    HIGH = 3      # Should fix, may affect model quality
    MEDIUM = 2    # Should investigate
    LOW = 1       # Minor issue, informational
    INFO = 0      # Informational only


def _col_contains(col, pattern: str) -> bool:
    """Safely check if column name contains pattern (handles int column names)."""
    try:
        return pattern in str(col).lower()
    except (AttributeError, TypeError):
        return False


def _find_cols(df: pd.DataFrame, *patterns: str) -> list:
    """Find columns matching any of the given patterns."""
    result = []
    for col in df.columns:
        col_str = str(col).lower()
        if any(p in col_str for p in patterns):
            result.append(col)
    return result


@dataclass
class ValidationFinding:
    """A single validation finding."""
    category: str
    check_name: str
    severity: Severity
    message: str
    affected_count: int
    total_count: int
    recommendation: str
    code_location: Optional[str] = None

    @property
    def affected_pct(self) -> float:
        if self.total_count == 0:
            return 0.0
        return 100.0 * self.affected_count / self.total_count


class DistanceValidator:
    """Validates distance calculations."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.findings: list[ValidationFinding] = []

    def check_haversine_fallback_zeros(self) -> ValidationFinding:
        """Check for cases where route distance is zero but haversine is not."""
        route_dist_cols = _find_cols(self.df, 'route_distance')
        haversine_cols = _find_cols(self.df, 'haversine')

        affected = 0
        total = len(self.df)

        if route_dist_cols and haversine_cols:
            for rd_col in route_dist_cols:
                for hv_col in haversine_cols:
                    mask = (self.df[rd_col] == 0) & (self.df[hv_col] > 0)
                    affected += mask.sum()

        finding = ValidationFinding(
            category="Distance",
            check_name="Haversine Fallback Zeros",
            severity=Severity.CRITICAL if affected > 0 else Severity.INFO,
            message=f"Found {affected} records where route_distance=0 but haversine_distance>0",
            affected_count=affected,
            total_count=total,
            recommendation="Check GTFS trip matching in preprocess.py. These records may use incorrect straight-line distances.",
            code_location="src/distance.py:calculate_route_distance()"
        )
        self.findings.append(finding)
        return finding

    def check_circular_route_wraparound(self) -> ValidationFinding:
        """Check for distances exceeding reasonable route total length."""
        dist_cols = [c for c in self.df.columns if _col_contains(c, 'distance') and _col_contains(c, 'stop')]

        # Assume max reasonable single-leg distance is 20km for campus routes
        max_reasonable_dist = 20000  # meters
        affected = 0
        total = len(self.df)

        for col in dist_cols:
            if col in self.df.columns:
                affected += (self.df[col] > max_reasonable_dist).sum()

        finding = ValidationFinding(
            category="Distance",
            check_name="Circular Route Wraparound",
            severity=Severity.HIGH if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with distance > {max_reasonable_dist}m (possible wraparound issue)",
            affected_count=affected,
            total_count=total,
            recommendation="Verify circular route handling in distance calculation. May need modulo arithmetic for route wraparound.",
            code_location="src/distance.py"
        )
        self.findings.append(finding)
        return finding

    def check_missing_gtfs_data(self) -> ValidationFinding:
        """Check for missing or zero route distances indicating GTFS lookup failure."""
        dist_cols = _find_cols(self.df, 'route_distance')

        affected = 0
        total = len(self.df)

        for col in dist_cols:
            if col in self.df.columns:
                affected += (self.df[col].isna() | (self.df[col] == 0)).sum()

        finding = ValidationFinding(
            category="Distance",
            check_name="Missing GTFS Trip Data",
            severity=Severity.HIGH if affected > total * 0.1 else Severity.MEDIUM if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with missing or zero route_distance (GTFS lookup may have failed)",
            affected_count=affected,
            total_count=total,
            recommendation="Check GTFS shapes.txt and trips.txt for coverage. Ensure pattern_id mapping is correct.",
            code_location="src/distance.py:get_shape_distance()"
        )
        self.findings.append(finding)
        return finding

    def run_all(self) -> list[ValidationFinding]:
        """Run all distance validation checks."""
        self.check_haversine_fallback_zeros()
        self.check_circular_route_wraparound()
        self.check_missing_gtfs_data()
        return self.findings


class FeatureValidator:
    """Validates feature calculations."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.findings: list[ValidationFinding] = []

    def check_heading_change_unbounded(self) -> ValidationFinding:
        """Check for unreasonably large heading change values."""
        heading_cols = _find_cols(self.df, 'heading_change')

        # Max reasonable heading change over 300s is a few full rotations
        max_reasonable = 1800  # 5 full rotations in degrees
        affected = 0
        total = len(self.df)

        for col in heading_cols:
            if col in self.df.columns:
                affected += (self.df[col].abs() > max_reasonable).sum()

        finding = ValidationFinding(
            category="Features",
            check_name="Heading Change Unbounded",
            severity=Severity.MEDIUM if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with heading_change > {max_reasonable} degrees",
            affected_count=affected,
            total_count=total,
            recommendation="Consider normalizing heading changes to [-180, 180] or using sin/cos encoding.",
            code_location="src/features.py:calculate_heading_features()"
        )
        self.findings.append(finding)
        return finding

    def check_acceleration_magnitude(self) -> ValidationFinding:
        """Check if acceleration values are within reasonable range."""
        accel_cols = _find_cols(self.df, 'accel')

        affected = 0
        total = len(self.df)

        for col in accel_cols:
            if col in self.df.columns:
                # Check if max acceleration is suspiciously low (< 0.1 mph/s)
                max_accel = self.df[col].abs().max()
                if max_accel < 0.1:
                    affected += len(self.df)

        finding = ValidationFinding(
            category="Features",
            check_name="Acceleration Magnitude",
            severity=Severity.LOW if affected > 0 else Severity.INFO,
            message=f"Max acceleration is very low (<0.1 mph/s)" if affected > 0 else "Acceleration values in expected range",
            affected_count=affected,
            total_count=total,
            recommendation="Verify acceleration calculation uses correct time delta. May be using wrong units.",
            code_location="src/features.py:calculate_motion_features()"
        )
        self.findings.append(finding)
        return finding

    def check_rolling_feature_nan(self) -> ValidationFinding:
        """Check for NaN values in rolling/windowed features."""
        rolling_cols = _find_cols(self.df, 'rolling', 'avg_', 'mean_', 'std_')

        affected = 0
        total = len(self.df) * max(len(rolling_cols), 1)

        for col in rolling_cols:
            if col in self.df.columns:
                affected += self.df[col].isna().sum()

        finding = ValidationFinding(
            category="Features",
            check_name="Rolling Feature NaN",
            severity=Severity.MEDIUM if affected > total * 0.05 else Severity.LOW if affected > 0 else Severity.INFO,
            message=f"Found {affected} NaN values in rolling/windowed features",
            affected_count=affected,
            total_count=total,
            recommendation="Ensure rolling windows have min_periods set correctly. Consider forward-fill for trip starts.",
            code_location="src/features.py"
        )
        self.findings.append(finding)
        return finding

    def run_all(self) -> list[ValidationFinding]:
        """Run all feature validation checks."""
        self.check_heading_change_unbounded()
        self.check_acceleration_magnitude()
        self.check_rolling_feature_nan()
        return self.findings


class TemporalValidator:
    """Validates temporal feature calculations."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.findings: list[ValidationFinding] = []

    def check_class_change_midnight(self) -> ValidationFinding:
        """Check for class change flag issues near midnight."""
        class_change_cols = _find_cols(self.df, 'class_change')
        time_cols = _find_cols(self.df, 'time_of_day', 'hour')

        affected = 0
        total = len(self.df)

        # Class changes should only occur during class times (roughly 7am-10pm)
        if class_change_cols and time_cols:
            for cc_col in class_change_cols:
                for time_col in time_cols:
                    if cc_col in self.df.columns and time_col in self.df.columns:
                        # Check for class change flags at unusual hours (midnight-6am)
                        late_night_mask = (self.df[time_col] < 0.25) | (self.df[time_col] > 0.92)  # Normalized time
                        if self.df[time_col].max() > 24:  # Raw hours
                            late_night_mask = (self.df[time_col] < 6) | (self.df[time_col] > 22)
                        affected += (late_night_mask & (self.df[cc_col] == 1)).sum()

        finding = ValidationFinding(
            category="Temporal",
            check_name="Class Change Midnight Wraparound",
            severity=Severity.MEDIUM if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with class_change flag during late night hours",
            affected_count=affected,
            total_count=total,
            recommendation="Verify class change time windows. Should only flag 8am-10pm typical class times.",
            code_location="src/features.py:calculate_temporal_features()"
        )
        self.findings.append(finding)
        return finding

    def check_scheduled_time_nextday(self) -> ValidationFinding:
        """Check for zero scheduled times when stop is in the future."""
        sched_cols = _find_cols(self.df, 'scheduled')

        affected = 0
        total = len(self.df)

        for col in sched_cols:
            if col in self.df.columns:
                # Zero or negative scheduled times are suspicious
                affected += (self.df[col] <= 0).sum()

        finding = ValidationFinding(
            category="Temporal",
            check_name="Scheduled Time Next-Day",
            severity=Severity.HIGH if affected > total * 0.05 else Severity.MEDIUM if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with scheduled_time <= 0 (possible next-day wraparound)",
            affected_count=affected,
            total_count=total,
            recommendation="Check midnight handling in schedule lookup. May need to handle 24+ hour GTFS times.",
            code_location="src/preprocess.py:merge_schedule_data()"
        )
        self.findings.append(finding)
        return finding

    def check_minutes_since_stop_capped(self) -> ValidationFinding:
        """Check for capped time-since-last-stop values."""
        since_stop_cols = [c for c in self.df.columns if _col_contains(c, 'since') and _col_contains(c, 'stop')]

        affected = 0
        total = len(self.df)

        for col in since_stop_cols:
            if col in self.df.columns:
                # Check for exactly 0 values which may indicate capping
                affected += (self.df[col] == 0).sum()

        finding = ValidationFinding(
            category="Temporal",
            check_name="Minutes Since Stop Capped",
            severity=Severity.LOW if affected > total * 0.1 else Severity.INFO,
            message=f"Found {affected} records with minutes_since_stop = 0 (may be capped)",
            affected_count=affected,
            total_count=total,
            recommendation="Verify if zeros represent actual data or capped values from >1 hour gaps.",
            code_location="src/features.py"
        )
        self.findings.append(finding)
        return finding

    def run_all(self) -> list[ValidationFinding]:
        """Run all temporal validation checks."""
        self.check_class_change_midnight()
        self.check_scheduled_time_nextday()
        self.check_minutes_since_stop_capped()
        return self.findings


class LabelValidator:
    """Validates label creation."""

    def __init__(self, df: pd.DataFrame, labels: Optional[np.ndarray] = None):
        self.df = df
        self.labels = labels
        self.findings: list[ValidationFinding] = []

    def check_lookahead_bias(self) -> ValidationFinding:
        """Check for 1-hour lookahead window truncation bias."""
        eta_cols = _find_cols(self.df, 'eta', 'time_to_arrival')

        affected = 0
        total = len(self.df)

        # Check for clustering of values near 3600s (1 hour cutoff)
        for col in eta_cols:
            if col in self.df.columns:
                near_cutoff = ((self.df[col] > 3500) & (self.df[col] <= 3600)).sum()
                affected += near_cutoff

        # Also check labels array if provided
        if self.labels is not None:
            near_cutoff = ((self.labels > 3500) & (self.labels <= 3600)).sum()
            affected += near_cutoff
            total += self.labels.size

        finding = ValidationFinding(
            category="Labels",
            check_name="1-Hour Lookahead Bias",
            severity=Severity.HIGH if affected > 100 else Severity.MEDIUM if affected > 0 else Severity.INFO,
            message=f"Found {affected} labels clustered near 3600s cutoff (possible truncation bias)",
            affected_count=affected,
            total_count=total,
            recommendation="Consider removing samples near the 1-hour boundary or using variable lookahead.",
            code_location="src/preprocess.py:create_labels()"
        )
        self.findings.append(finding)
        return finding

    def check_negative_eta(self) -> ValidationFinding:
        """Check for negative ETA values (should never happen)."""
        eta_cols = _find_cols(self.df, 'eta', 'time_to_arrival')

        affected = 0
        total = len(self.df)

        for col in eta_cols:
            if col in self.df.columns:
                affected += (self.df[col] < 0).sum()

        if self.labels is not None:
            affected += (self.labels < 0).sum()
            total += self.labels.size

        finding = ValidationFinding(
            category="Labels",
            check_name="Negative ETA Values",
            severity=Severity.CRITICAL if affected > 0 else Severity.INFO,
            message=f"Found {affected} negative ETA values (bus already passed stop)",
            affected_count=affected,
            total_count=total,
            recommendation="Filter out passed stops during label creation. Check timestamp ordering.",
            code_location="src/preprocess.py:create_labels()"
        )
        self.findings.append(finding)
        return finding

    def check_join_success_rate(self) -> ValidationFinding:
        """Check telemetry-to-arrival join success rate."""
        # This is harder to detect post-hoc, but we can check for missing labels
        affected = 0
        total = len(self.df)

        if self.labels is not None:
            # Check for NaN or zero labels which may indicate failed joins
            affected = np.isnan(self.labels).sum() + (self.labels == 0).sum()
            total = self.labels.size
        else:
            # Check label columns in dataframe
            label_cols = _find_cols(self.df, 'label', 'target')
            for col in label_cols:
                if col in self.df.columns:
                    affected += self.df[col].isna().sum()

        join_rate = 100.0 * (1 - affected / max(total, 1))

        finding = ValidationFinding(
            category="Labels",
            check_name="Join Success Rate",
            severity=Severity.HIGH if join_rate < 50 else Severity.MEDIUM if join_rate < 80 else Severity.INFO,
            message=f"Label join success rate: {join_rate:.1f}% ({total - affected}/{total} records have labels)",
            affected_count=affected,
            total_count=total,
            recommendation="Check telemetry-arrival temporal join window. May need to widen match window.",
            code_location="src/preprocess.py:join_telemetry_arrivals()"
        )
        self.findings.append(finding)
        return finding

    def check_label_outliers(self) -> ValidationFinding:
        """Check for ETA outliers beyond expected range."""
        eta_cols = _find_cols(self.df, 'eta', 'time_to_arrival')

        affected = 0
        total = len(self.df)

        # ETAs > 1 hour are suspicious for campus transit
        for col in eta_cols:
            if col in self.df.columns:
                affected += (self.df[col] > 3600).sum()

        if self.labels is not None:
            affected += (self.labels > 3600).sum()
            total += self.labels.size

        finding = ValidationFinding(
            category="Labels",
            check_name="Label Outliers",
            severity=Severity.MEDIUM if affected > total * 0.01 else Severity.LOW if affected > 0 else Severity.INFO,
            message=f"Found {affected} labels > 3600s (1 hour) - possible outliers",
            affected_count=affected,
            total_count=total,
            recommendation="Consider capping or removing extreme outliers. May indicate route detours or data issues.",
            code_location="src/preprocess.py"
        )
        self.findings.append(finding)
        return finding

    def run_all(self) -> list[ValidationFinding]:
        """Run all label validation checks."""
        self.check_lookahead_bias()
        self.check_negative_eta()
        self.check_join_success_rate()
        self.check_label_outliers()
        return self.findings


class DataQualityValidator:
    """Validates overall data quality."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.findings: list[ValidationFinding] = []

    def check_vehicle_id_mismatches(self) -> ValidationFinding:
        """Check for vehicle ID inconsistencies."""
        vid_cols = _find_cols(self.df, 'vehicle', 'vid')

        unique_vids = set()
        for col in vid_cols:
            if col in self.df.columns:
                unique_vids.update(self.df[col].dropna().unique())

        # Check for suspiciously high number of unique vehicles
        affected = len(unique_vids) if len(unique_vids) > 50 else 0
        total = len(unique_vids)

        finding = ValidationFinding(
            category="Data Quality",
            check_name="Vehicle ID Mismatches",
            severity=Severity.HIGH if affected > 0 else Severity.INFO,
            message=f"Found {len(unique_vids)} unique vehicle IDs" + (" (unusually high)" if affected > 0 else ""),
            affected_count=affected,
            total_count=total,
            recommendation="Verify vehicle ID consistency across data sources. May have ID format changes.",
            code_location="src/preprocess.py:normalize_vehicle_ids()"
        )
        self.findings.append(finding)
        return finding

    def check_stop_mapping_failures(self) -> ValidationFinding:
        """Check for failed stop name to ID mappings."""
        stop_cols = _find_cols(self.df, 'stop')

        affected = 0
        total = len(self.df)

        for col in stop_cols:
            if col in self.df.columns:
                affected += self.df[col].isna().sum()

        finding = ValidationFinding(
            category="Data Quality",
            check_name="Stop Mapping Failures",
            severity=Severity.MEDIUM if affected > total * 0.05 else Severity.LOW if affected > 0 else Severity.INFO,
            message=f"Found {affected} records with missing stop IDs (mapping failures)",
            affected_count=affected,
            total_count=total,
            recommendation="Check stops.json for completeness. May need to update stop name mappings.",
            code_location="src/preprocess.py:map_stop_names()"
        )
        self.findings.append(finding)
        return finding

    def check_weather_fillna(self) -> ValidationFinding:
        """Check for default weather values that may mask missing data."""
        temp_cols = _find_cols(self.df, 'temp')
        precip_cols = _find_cols(self.df, 'precip')

        affected = 0
        total = len(self.df)

        # Check for suspiciously exact default values
        if temp_cols and precip_cols:
            for temp_col in temp_cols:
                for precip_col in precip_cols:
                    if temp_col in self.df.columns and precip_col in self.df.columns:
                        # Common default: temp=20.0, precip=0.0
                        default_mask = (self.df[temp_col] == 20.0) & (self.df[precip_col] == 0.0)
                        affected += default_mask.sum()

        finding = ValidationFinding(
            category="Data Quality",
            check_name="Weather FillNA Ambiguity",
            severity=Severity.LOW if affected > total * 0.1 else Severity.INFO,
            message=f"Found {affected} records with default weather values (temp=20, precip=0)",
            affected_count=affected,
            total_count=total,
            recommendation="Verify if these are real values or fillna defaults. Consider adding weather data coverage flag.",
            code_location="src/features.py:add_weather_features()"
        )
        self.findings.append(finding)
        return finding

    def check_feature_completeness(self) -> ValidationFinding:
        """Check for overall feature completeness (NaN counts)."""
        nan_counts = self.df.isna().sum()
        total_cells = len(self.df) * len(self.df.columns)
        total_nan = nan_counts.sum()

        # Find columns with highest NaN rates
        nan_pct = (nan_counts / len(self.df) * 100).sort_values(ascending=False)
        high_nan_cols = nan_pct[nan_pct > 10].head(5)

        cols_info = ", ".join([f"{col}: {pct:.1f}%" for col, pct in high_nan_cols.items()])

        finding = ValidationFinding(
            category="Data Quality",
            check_name="Feature Completeness",
            severity=Severity.MEDIUM if total_nan > total_cells * 0.05 else Severity.LOW if total_nan > 0 else Severity.INFO,
            message=f"Total NaN rate: {100*total_nan/total_cells:.2f}%. " + (f"High NaN columns: {cols_info}" if cols_info else "All columns complete."),
            affected_count=total_nan,
            total_count=total_cells,
            recommendation="Investigate columns with >10% missing values. Consider imputation or removal.",
            code_location="src/preprocess.py"
        )
        self.findings.append(finding)
        return finding

    def run_all(self) -> list[ValidationFinding]:
        """Run all data quality validation checks."""
        self.check_vehicle_id_mismatches()
        self.check_stop_mapping_failures()
        self.check_weather_fillna()
        self.check_feature_completeness()
        return self.findings


@dataclass
class ValidationReport:
    """Collects and formats validation findings."""

    findings: list[ValidationFinding] = field(default_factory=list)
    dataset_info: dict = field(default_factory=dict)

    def add_finding(self, finding: ValidationFinding):
        self.findings.append(finding)

    def add_findings(self, findings: list[ValidationFinding]):
        self.findings.extend(findings)

    def generate_summary(self) -> dict:
        """Generate summary statistics by category and severity."""
        summary = {}
        for finding in self.findings:
            if finding.category not in summary:
                summary[finding.category] = {s.name: 0 for s in Severity}
            summary[finding.category][finding.severity.name] += 1
        return summary

    def write_markdown(self, output_path: str):
        """Write validation report to markdown file."""
        lines = []

        # Header
        lines.append("# Data Validation Report")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Executive Summary
        lines.append("## Executive Summary\n")
        summary = self.generate_summary()

        lines.append("| Category | Critical | High | Medium | Low | Info |")
        lines.append("|----------|----------|------|--------|-----|------|")

        totals = {s.name: 0 for s in Severity}
        for category, counts in sorted(summary.items()):
            row = f"| {category} |"
            for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
                count = counts.get(sev, 0)
                totals[sev] += count
                row += f" {count} |"
            lines.append(row)

        # Totals row
        lines.append(f"| **Total** | **{totals['CRITICAL']}** | **{totals['HIGH']}** | **{totals['MEDIUM']}** | **{totals['LOW']}** | **{totals['INFO']}** |")
        lines.append("")

        # Dataset Overview
        if self.dataset_info:
            lines.append("## Dataset Overview\n")
            lines.append("| Split | Records | Label Coverage |")
            lines.append("|-------|---------|----------------|")
            for split, info in self.dataset_info.items():
                lines.append(f"| {split} | {info.get('records', 'N/A')} | {info.get('coverage', 'N/A')} |")
            lines.append("")

        # Detailed Findings by Category
        lines.append("## Detailed Findings\n")

        categories = sorted(set(f.category for f in self.findings))
        for category in categories:
            lines.append(f"### {category}\n")

            cat_findings = [f for f in self.findings if f.category == category]
            cat_findings.sort(key=lambda x: x.severity, reverse=True)

            for finding in cat_findings:
                sev_emoji = {
                    Severity.CRITICAL: "🔴",
                    Severity.HIGH: "🟠",
                    Severity.MEDIUM: "🟡",
                    Severity.LOW: "🟢",
                    Severity.INFO: "⚪"
                }.get(finding.severity, "⚪")

                lines.append(f"#### {sev_emoji} {finding.check_name}")
                lines.append(f"**Severity:** {finding.severity.name}")
                lines.append(f"**Affected:** {finding.affected_count:,} / {finding.total_count:,} ({finding.affected_pct:.2f}%)")
                lines.append(f"\n{finding.message}\n")
                if finding.code_location:
                    lines.append(f"**Code Location:** `{finding.code_location}`")
                lines.append(f"**Recommendation:** {finding.recommendation}\n")

        # Recommendations Summary
        lines.append("## Recommendations Summary\n")

        critical = [f for f in self.findings if f.severity == Severity.CRITICAL]
        high = [f for f in self.findings if f.severity == Severity.HIGH]
        medium = [f for f in self.findings if f.severity == Severity.MEDIUM]

        if critical:
            lines.append("### Critical (Must Fix)")
            for f in critical:
                lines.append(f"- **{f.check_name}**: {f.recommendation}")
            lines.append("")

        if high:
            lines.append("### High Priority")
            for f in high:
                lines.append(f"- **{f.check_name}**: {f.recommendation}")
            lines.append("")

        if medium:
            lines.append("### Medium Priority")
            for f in medium:
                lines.append(f"- **{f.check_name}**: {f.recommendation}")
            lines.append("")

        if not (critical or high or medium):
            lines.append("No critical, high, or medium priority issues found. Data quality looks good!\n")

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return output_path


def load_data(data_dir: str) -> tuple[Optional[pd.DataFrame], Optional[np.ndarray]]:
    """Load processed data from directory."""
    data_dir = Path(data_dir)
    df = None
    labels = None

    # Try to load features dataframe
    for name in ['features.parquet', 'features.csv', 'train.parquet', 'train.csv']:
        path = data_dir / name
        if path.exists():
            if path.suffix == '.parquet':
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
            print(f"Loaded features from {path}")
            break

    # Try to load from numpy files
    if df is None:
        features_path = data_dir / 'features.npy'
        if features_path.exists():
            features = np.load(features_path)
            df = pd.DataFrame(features)
            print(f"Loaded features from {features_path}")

    # Try to load labels
    labels_path = data_dir / 'labels.npy'
    if labels_path.exists():
        labels = np.load(labels_path)
        print(f"Loaded labels from {labels_path}")

    return df, labels


def main():
    parser = argparse.ArgumentParser(
        description='Validate processed ETA training data for calculation errors and edge cases.'
    )
    parser.add_argument(
        '--data-dir', '-d',
        required=True,
        help='Directory containing processed data (features.npy, labels.npy, etc.)'
    )
    parser.add_argument(
        '--output', '-o',
        default='validation_report.md',
        help='Output path for validation report (default: validation_report.md)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print verbose output during validation'
    )

    args = parser.parse_args()

    print(f"Loading data from {args.data_dir}...")
    df, labels = load_data(args.data_dir)

    if df is None:
        print("ERROR: Could not load features data. Please check the data directory.")
        print(f"Looked for: features.parquet, features.csv, train.parquet, train.csv, features.npy")
        return 1

    print(f"Loaded {len(df)} records with {len(df.columns)} features")
    if labels is not None:
        print(f"Labels shape: {labels.shape}")

    # Initialize report
    report = ValidationReport()
    report.dataset_info = {
        'All': {
            'records': f"{len(df):,}",
            'coverage': f"{100 * (1 - df.isna().any(axis=1).sum() / len(df)):.1f}%"
        }
    }

    # Run all validators
    print("\nRunning validation checks...")

    print("  - Distance validation...")
    dist_validator = DistanceValidator(df)
    report.add_findings(dist_validator.run_all())

    print("  - Feature validation...")
    feat_validator = FeatureValidator(df)
    report.add_findings(feat_validator.run_all())

    print("  - Temporal validation...")
    temp_validator = TemporalValidator(df)
    report.add_findings(temp_validator.run_all())

    print("  - Label validation...")
    label_validator = LabelValidator(df, labels)
    report.add_findings(label_validator.run_all())

    print("  - Data quality validation...")
    quality_validator = DataQualityValidator(df)
    report.add_findings(quality_validator.run_all())

    # Generate and write report
    print(f"\nWriting report to {args.output}...")
    report.write_markdown(args.output)

    # Print summary
    summary = report.generate_summary()
    total_critical = sum(c.get('CRITICAL', 0) for c in summary.values())
    total_high = sum(c.get('HIGH', 0) for c in summary.values())
    total_medium = sum(c.get('MEDIUM', 0) for c in summary.values())

    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    print(f"  Critical issues: {total_critical}")
    print(f"  High priority:   {total_high}")
    print(f"  Medium priority: {total_medium}")
    print("=" * 50)

    if total_critical > 0:
        print("\n[!] CRITICAL issues found! Review report before training.")
        return 2
    elif total_high > 0:
        print("\n[!] High priority issues found. Review report and consider fixing.")
        return 1
    else:
        print("\n[OK] No critical or high priority issues found.")
        return 0


if __name__ == '__main__':
    exit(main())
