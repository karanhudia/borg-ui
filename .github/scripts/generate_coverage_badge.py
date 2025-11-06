#!/usr/bin/env python3
"""
Generate coverage badge data for README
"""
import sys
import xml.etree.ElementTree as ET
import json


def get_coverage_from_xml(xml_file='coverage.xml'):
    """Extract coverage percentage from coverage.xml"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        coverage = float(root.attrib['line-rate']) * 100
        return round(coverage, 1)
    except Exception as e:
        print(f"Error reading coverage: {e}", file=sys.stderr)
        return 0.0


def get_badge_color(coverage):
    """Get badge color based on coverage percentage"""
    if coverage >= 90:
        return 'brightgreen'
    elif coverage >= 80:
        return 'green'
    elif coverage >= 70:
        return 'yellowgreen'
    elif coverage >= 60:
        return 'yellow'
    elif coverage >= 50:
        return 'orange'
    else:
        return 'red'


def generate_badge_url(coverage):
    """Generate shields.io badge URL"""
    color = get_badge_color(coverage)
    return f"https://img.shields.io/badge/coverage-{coverage}%25-{color}"


def main():
    coverage = get_coverage_from_xml()
    color = get_badge_color(coverage)
    badge_url = generate_badge_url(coverage)

    print(f"Coverage: {coverage}%")
    print(f"Color: {color}")
    print(f"Badge URL: {badge_url}")

    # Output for GitHub Actions
    print(f"\n::set-output name=coverage::{coverage}")
    print(f"::set-output name=color::{color}")
    print(f"::set-output name=badge_url::{badge_url}")

    # Also save to file for later use
    with open('coverage_badge.json', 'w') as f:
        json.dump({
            'coverage': coverage,
            'color': color,
            'badge_url': badge_url
        }, f)


if __name__ == '__main__':
    main()
