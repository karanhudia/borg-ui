#!/bin/bash
# Security vulnerability scanner for borg-ui project
# Usage: ./scripts/security-scan.sh [option]
# Options: all, frontend, backend, docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORT_DIR="$PROJECT_ROOT/security-reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Create report directory
mkdir -p "$REPORT_DIR"

print_header() {
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}\n"
}

print_error() {
    echo -e "${RED}ERROR: $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}WARNING: $1${NC}"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        print_error "$1 is not installed. Install with: $2"
        return 1
    fi
    return 0
}

scan_frontend() {
    print_header "Scanning Frontend Dependencies (npm audit)"

    cd "$PROJECT_ROOT/frontend"

    if npm audit --json > "$REPORT_DIR/npm-audit.json" 2>&1; then
        echo -e "${GREEN}✓ No vulnerabilities found${NC}"
    else
        print_warning "Vulnerabilities found. See $REPORT_DIR/npm-audit.json"
        npm audit
    fi
}

scan_backend_pip_audit() {
    print_header "Scanning Backend Dependencies (pip-audit)"

    if ! check_command "pip-audit" "pip3 install pip-audit"; then
        return 1
    fi

    cd "$PROJECT_ROOT"

    if pip-audit -r requirements.txt --format json > "$REPORT_DIR/pip-audit.json" 2>&1; then
        echo -e "${GREEN}✓ No vulnerabilities found${NC}"
    else
        print_warning "Vulnerabilities found. See $REPORT_DIR/pip-audit.json"
        pip-audit -r requirements.txt
    fi
}

scan_backend_safety() {
    print_header "Scanning Backend Dependencies (safety)"

    if ! check_command "safety" "pip3 install safety"; then
        print_warning "Safety not installed, skipping"
        return 0
    fi

    cd "$PROJECT_ROOT"

    if safety check -r requirements.txt --json > "$REPORT_DIR/safety-check.json" 2>&1; then
        echo -e "${GREEN}✓ No vulnerabilities found${NC}"
    else
        print_warning "Vulnerabilities found. See $REPORT_DIR/safety-check.json"
        safety check -r requirements.txt
    fi
}

scan_trivy() {
    print_header "Scanning Project with Trivy"

    if ! check_command "trivy" "brew install aquasecurity/trivy/trivy"; then
        return 1
    fi

    cd "$PROJECT_ROOT"

    echo "Scanning filesystem..."
    trivy fs --scanners vuln --format json --output "$REPORT_DIR/trivy-full.json" .

    echo "Scanning for HIGH and CRITICAL vulnerabilities only..."
    trivy fs --scanners vuln --severity HIGH,CRITICAL --format table .

    echo -e "\n${GREEN}Full report saved to: $REPORT_DIR/trivy-full.json${NC}"
}

scan_docker_image() {
    print_header "Scanning Docker Image with Trivy"

    if ! check_command "trivy" "brew install aquasecurity/trivy/trivy"; then
        return 1
    fi

    IMAGE_NAME="${1:-borg-ui:latest}"

    echo "Scanning Docker image: $IMAGE_NAME"
    if docker image inspect "$IMAGE_NAME" &> /dev/null; then
        trivy image --format json --output "$REPORT_DIR/trivy-docker.json" "$IMAGE_NAME"
        trivy image --severity HIGH,CRITICAL "$IMAGE_NAME"
        echo -e "\n${GREEN}Full report saved to: $REPORT_DIR/trivy-docker.json${NC}"
    else
        print_error "Docker image '$IMAGE_NAME' not found. Build it first or specify with: $0 docker <image-name>"
        return 1
    fi
}

generate_summary() {
    print_header "Security Scan Summary"

    echo "Reports generated in: $REPORT_DIR"
    echo ""
    ls -lh "$REPORT_DIR/" 2>/dev/null || echo "No reports found"

    echo -e "\n${YELLOW}Recommended Actions:${NC}"
    echo "1. Review reports in $REPORT_DIR/"
    echo "2. Update vulnerable dependencies in package.json and requirements.txt"
    echo "3. Run 'npm audit fix' in frontend/ for auto-fixes"
    echo "4. Run 'pip-audit --fix' for Python auto-fixes (with caution)"
    echo "5. Rebuild Docker images with updated dependencies"
}

# Main script logic
SCAN_TYPE="${1:-all}"

case "$SCAN_TYPE" in
    frontend)
        scan_frontend
        ;;
    backend)
        scan_backend_pip_audit
        scan_backend_safety
        ;;
    trivy)
        scan_trivy
        ;;
    docker)
        scan_docker_image "$2"
        ;;
    all)
        scan_frontend
        scan_backend_pip_audit
        scan_backend_safety
        scan_trivy
        generate_summary
        ;;
    *)
        echo "Usage: $0 {all|frontend|backend|trivy|docker [image-name]}"
        echo ""
        echo "Examples:"
        echo "  $0 all              # Run all scans"
        echo "  $0 frontend         # Scan frontend only"
        echo "  $0 backend          # Scan backend only"
        echo "  $0 trivy            # Run Trivy filesystem scan"
        echo "  $0 docker           # Scan default Docker image"
        echo "  $0 docker myimg:tag # Scan specific Docker image"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Security scan completed!${NC}\n"
