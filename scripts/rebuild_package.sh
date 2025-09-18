#!/bin/bash
# rebuild_package.sh - Rebuild aiops-utils package
# Usage: ./scripts/rebuild_package.sh

set -e

echo "🔧 aiops-utils Package Rebuild Script"
echo "====================================="

# Ensure we're in the project root
if [[ ! -f "pyproject.toml" ]]; then
    echo "❌ Error: Run this script from the project root directory"
    echo "   Usage: ./scripts/rebuild_package.sh"
    exit 1
fi

# Show current version
CURRENT_VERSION=$(grep 'version = ' pyproject.toml | cut -d'"' -f2)
echo "📊 Current version: $CURRENT_VERSION"

# Version options
echo ""
echo "🔢 Version options:"
echo "   1) Keep current version ($CURRENT_VERSION)"
echo "   2) Auto-increment patch version"
echo "   3) Exit to manually edit pyproject.toml"
echo ""
read -p "Choose option (1/2/3): " -n 1 -r
echo ""

case $REPLY in
    1)
        echo "✅ Using current version: $CURRENT_VERSION"
        ;;
    2)
        NEW_VERSION=$(echo $CURRENT_VERSION | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g')
        echo "🔄 Auto-incrementing: $CURRENT_VERSION → $NEW_VERSION"

        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
        else
            sed -i "s/version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml
        fi

        echo "✅ Updated pyproject.toml to version $NEW_VERSION"
        ;;
    3)
        echo "⏸️  Exiting. Edit pyproject.toml manually and run again."
        exit 0
        ;;
    *)
        echo "❌ Invalid option. Exiting."
        exit 1
        ;;
esac

# Check for required tools
if ! command -v python &> /dev/null; then
    echo "❌ Python not found. Please install Python ≥3.10"
    exit 1
fi

# Install/upgrade build tools
echo ""
echo "🔧 Ensuring build tools are up to date..."
pip install --upgrade build wheel setuptools

# Clean previous builds
echo "🧹 Cleaning build artifacts..."
rm -rf dist/ build/ src/aiops_utils.egg-info/

# Build package
echo "🔨 Building package..."
python -m build

# Show results
FINAL_VERSION=$(grep 'version = ' pyproject.toml | cut -d'"' -f2)
echo ""
echo "✅ Build complete for version $FINAL_VERSION!"
echo "📦 Generated files:"
ls -la dist/

echo ""
echo "🔍 Wheel contents:"
python -m zipfile -l dist/*.whl

echo ""
echo "🚀 Next steps:"
echo "   1. Review build output above"
echo "   2. git add . && git commit -m 'Release version $FINAL_VERSION'"
echo "   3. git push origin main"
echo "   4. Create GitHub release (optional)"
echo ""
echo "💡 Production apps will get v$FINAL_VERSION on next deployment!"
