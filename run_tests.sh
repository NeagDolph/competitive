#!/bin/bash

# Test runner script for competitive analysis project
# Usage: ./run_tests.sh [option]

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Competitive Analysis Test Runner${NC}"
echo "======================================"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest is not installed. Installing test dependencies...${NC}"
    pip install -r test_requirements.txt
fi

# Function to run tests with timing
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    
    echo -e "\n${YELLOW}Running $test_name...${NC}"
    start_time=$(date +%s)
    
    if eval "$test_cmd"; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo -e "${GREEN}✅ $test_name completed in ${duration}s${NC}"
    else
        echo -e "${RED}❌ $test_name failed${NC}"
        exit 1
    fi
}

case "${1:-all}" in
    "all")
        echo -e "${BLUE}Running all tests with coverage...${NC}"
        run_test "Full Test Suite" "pytest test_competitive_analysis.py --cov=. --cov-report=html --cov-report=term-missing"
        echo -e "\n${GREEN}📊 Coverage report generated in htmlcov/index.html${NC}"
        ;;
    
    "quick")
        echo -e "${BLUE}Running quick tests (no coverage)...${NC}"
        run_test "Quick Test Suite" "pytest test_competitive_analysis.py -x --tb=short"
        ;;
    
    "unit")
        echo -e "${BLUE}Running unit tests only...${NC}"
        run_test "Unit Tests" "pytest test_competitive_analysis.py -m unit -v"
        ;;
    
    "integration")
        echo -e "${BLUE}Running integration tests only...${NC}"
        run_test "Integration Tests" "pytest test_competitive_analysis.py -m integration -v"
        ;;
    
    "verbose")
        echo -e "${BLUE}Running all tests with verbose output...${NC}"
        run_test "Verbose Test Suite" "pytest test_competitive_analysis.py -v -s --tb=short"
        ;;
    
    "url")
        echo -e "${BLUE}Running URL helper tests...${NC}"
        run_test "URL Helper Tests" "pytest test_competitive_analysis.py::TestURLHelpers -v"
        ;;
    
    "html")
        echo -e "${BLUE}Running HTML cleaning tests...${NC}"
        run_test "HTML Cleaning Tests" "pytest test_competitive_analysis.py::TestHTMLCleaning -v"
        ;;
    
    "filters")
        echo -e "${BLUE}Running content filter tests...${NC}"
        run_test "Content Filter Tests" "pytest test_competitive_analysis.py::TestContentFilters -v"
        ;;
    
    "db")
        echo -e "${BLUE}Running database tests...${NC}"
        run_test "Database Tests" "pytest test_competitive_analysis.py::TestDatabase -v"
        ;;
    
    "products")
        echo -e "${BLUE}Running product extractor tests...${NC}"
        run_test "Product Extractor Tests" "pytest test_competitive_analysis.py::TestProductExtractor -v"
        ;;
    
    "categories")
        echo -e "${BLUE}Running category finder tests...${NC}"
        run_test "Category Finder Tests" "pytest test_competitive_analysis.py::TestCategoryLinkFinder -v"
        ;;
    
    "main")
        echo -e "${BLUE}Running main application tests...${NC}"
        run_test "Main Application Tests" "pytest test_competitive_analysis.py::TestMainApplication -v"
        ;;
    
    "playwright")
        echo -e "${BLUE}Running Playwright integration tests...${NC}"
        run_test "Playwright Integration Tests" "pytest test_competitive_analysis.py::TestPlaywrightIntegration -v"
        ;;
    
    "watch")
        echo -e "${BLUE}Running tests in watch mode...${NC}"
        echo -e "${YELLOW}Press Ctrl+C to stop watching${NC}"
        pytest-watch test_competitive_analysis.py
        ;;
    
    "install")
        echo -e "${BLUE}Installing test dependencies...${NC}"
        pip install -r test_requirements.txt
        echo -e "${GREEN}✅ Test dependencies installed${NC}"
        ;;
    
    "help"|"--help"|"-h")
        echo -e "${BLUE}Available options:${NC}"
        echo "  all         - Run all tests with coverage (default)"
        echo "  quick       - Run tests quickly without coverage"
        echo "  unit        - Run unit tests only"
        echo "  integration - Run integration tests only"
        echo "  verbose     - Run all tests with verbose output"
        echo "  url         - Run URL helper tests"
        echo "  html        - Run HTML cleaning tests"
        echo "  filters     - Run content filter tests"
        echo "  db          - Run database tests"
        echo "  products    - Run product extractor tests"
        echo "  categories  - Run category finder tests"
        echo "  main        - Run main application tests"
        echo "  playwright  - Run Playwright integration tests"
        echo "  watch       - Run tests in watch mode (requires pytest-watch)"
        echo "  install     - Install test dependencies"
        echo "  help        - Show this help message"
        echo ""
        echo -e "${YELLOW}Examples:${NC}"
        echo "  ./run_tests.sh              # Run all tests with coverage"
        echo "  ./run_tests.sh quick        # Quick test run"
        echo "  ./run_tests.sh db           # Test database operations only"
        echo "  ./run_tests.sh verbose      # Verbose output"
        ;;
    
    *)
        echo -e "${RED}❌ Unknown option: $1${NC}"
        echo -e "${YELLOW}Use './run_tests.sh help' to see available options${NC}"
        exit 1
        ;;
esac

echo -e "\n${GREEN}🎉 Test execution completed!${NC}" 