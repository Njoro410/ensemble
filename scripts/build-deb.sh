#!/usr/bin/env bash
# Build an installable .deb from the current working tree.
# Usage: PYTHON=/path/to/python ./scripts/build-deb.sh
set -euo pipefail

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_DIR"

PYTHON=${PYTHON:-python3}
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -n1)
if [ -z "$VERSION" ]; then
    echo "could not read version from pyproject.toml" >&2
    exit 1
fi

for tool in dpkg-deb "$PYTHON"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "required tool not found: $tool" >&2
        exit 1
    fi
done

WORK=$(mktemp -d)
PKG="$WORK/ensemble"
DIST="$PROJECT_DIR/dist"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/bin" \
         "$PKG/usr/lib/python3/dist-packages" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/doc/ensemble" \
         "$WORK/wheels" \
         "$DIST"

echo "building wheel for ensemble $VERSION"
"$PYTHON" -m pip wheel --no-deps --wheel-dir "$WORK/wheels" "$PROJECT_DIR"

WHEEL=$(find "$WORK/wheels" -maxdepth 1 -name "ensemble-${VERSION}-*.whl" | head -n1)
if [ -z "$WHEEL" ]; then
    echo "wheel not produced" >&2
    exit 1
fi
"$PYTHON" -m zipfile -e "$WHEEL" "$PKG/usr/lib/python3/dist-packages"

cat > "$PKG/usr/bin/ensemble" <<'EOF'
#!/usr/bin/python3
from ensemble.cli import main

raise SystemExit(main())
EOF
cat > "$PKG/usr/bin/ensemble-peer" <<'EOF'
#!/usr/bin/python3
from ensemble.peer import main

raise SystemExit(main())
EOF
chmod 0755 "$PKG/usr/bin/ensemble" "$PKG/usr/bin/ensemble-peer"

install -Dm644 packaging/ensemble.desktop \
    "$PKG/usr/share/applications/ensemble.desktop"
install -Dm644 src/ensemble/data/ensemble.svg \
    "$PKG/usr/share/icons/hicolor/scalable/apps/ensemble.svg"
install -Dm644 README.md "$PKG/usr/share/doc/ensemble/README.md"
install -Dm644 CHANGELOG.md "$PKG/usr/share/doc/ensemble/CHANGELOG.md"
install -Dm644 LICENSE "$PKG/usr/share/doc/ensemble/LICENSE"

{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: ensemble"
    echo "Source: https://github.com/Njoro410/ensemble"
    echo
    echo "Files: *"
    echo "Copyright: 2026 Njoro410"
    echo "License: MIT"
    sed 's/^/ /' LICENSE
} > "$PKG/usr/share/doc/ensemble/copyright"

{
    echo "ensemble (${VERSION}) unstable; urgency=medium"
    echo
    echo "  * Initial public release."
    echo
    echo " -- Njoro410 <95216451+Njoro410@users.noreply.github.com>  $(date -Ru)"
} > "$WORK/debian-changelog"
gzip -9n -c "$WORK/debian-changelog" \
    > "$PKG/usr/share/doc/ensemble/changelog.gz"

SIZE=$(du -sk "$PKG" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: ensemble
Version: $VERSION
Section: devel
Priority: optional
Architecture: all
Maintainer: Njoro410 <95216451+Njoro410@users.noreply.github.com>
Installed-Size: $SIZE
Homepage: https://github.com/Njoro410/ensemble
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-keyring, libsecret-1-0
Recommends: gnome-terminal, nodejs
Description: Claude Code multi-agent control plane
 Ensemble runs Claude Code as an orchestrator with 13 read-only
 specialist roles through opencode. It provides provider presets,
 per-key model discovery, an OS-keyring secret store, a GTK control
 panel, and an adaptive goal workflow.
 .
 Claude Code and opencode are external prerequisites; install them
 separately.
EOF

find "$PKG" -type d -exec chmod 0755 {} +
find "$PKG" -type f -exec chmod 0644 {} +
chmod 0755 "$PKG/usr/bin/ensemble" "$PKG/usr/bin/ensemble-peer" "$PKG/DEBIAN"

OUTPUT="$DIST/ensemble_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$PKG" "$OUTPUT" >/dev/null
echo "$OUTPUT"
