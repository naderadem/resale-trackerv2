#!/usr/bin/env python3
"""Fail CI if tests/test_db_integration.py skipped instead of actually running.

The Postgres integration test skips cleanly (not a failure) when it can't
reach a database -- that's the right behavior for a local run without
Docker, but in CI it means the Postgres service container is misconfigured
or unreachable, and a green run there would be a false negative: the one
test that verifies the real upsert-not-duplicate behavior against a real
database never ran at all. Parses the junit XML pytest produces and fails
loudly if any testcase from that file has a <skipped> child.
"""
import sys
import xml.etree.ElementTree as ET

TARGET_FILE_MARKER = "test_db_integration"


def main(junit_xml_path: str) -> int:
    tree = ET.parse(junit_xml_path)
    root = tree.getroot()

    skipped = []
    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        file_attr = testcase.get("file", "")
        if TARGET_FILE_MARKER not in classname and TARGET_FILE_MARKER not in file_attr:
            continue
        if testcase.find("skipped") is not None:
            skipped.append(testcase.get("name", "<unknown>"))

    if skipped:
        print(
            f"::error::{len(skipped)} test(s) in tests/{TARGET_FILE_MARKER}.py skipped in CI "
            "-- the Postgres service container must be reachable here. "
            f"Skipped: {', '.join(skipped)}"
        )
        return 1

    print(f"OK: no skipped tests in tests/{TARGET_FILE_MARKER}.py")
    return 0


if __name__ == "__main__":
    junit_path = sys.argv[1] if len(sys.argv) > 1 else "report.xml"
    sys.exit(main(junit_path))
