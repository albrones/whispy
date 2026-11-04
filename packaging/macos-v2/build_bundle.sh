#!/usr/bin/env bash
# Build, assemble and sign "Whispy V2.app" (the Rust V2 menu bar app).
#
# Produces dist/Whispy V2.app: the release binary plus every non-system dylib
# it loads, all resolved through @executable_path so the bundle runs without
# the v2/target build tree. Signed like V1 (see packaging/macos/build_app.sh).
#
# Usage (from anywhere):  ./packaging/macos-v2/build_bundle.sh
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
V1_PKG="$REPO_ROOT/packaging/macos"
TARGET_DIR="$REPO_ROOT/v2/target/release"
APP="$REPO_ROOT/dist/Whispy V2.app"
MACOS_DIR="$APP/Contents/MacOS"
BIN_NAME="whispy2"

die() { echo -e "${RED}[FAIL] $*${NC}" >&2; exit 1; }

echo -e "${YELLOW}=== Whispy V2.app build ===${NC}"

# 1. Release build.
echo -e "${YELLOW}Building whispy2 (cargo, release)...${NC}"
(cd "$REPO_ROOT/v2" && cargo build --release -p whispy2)
[ -x "$TARGET_DIR/$BIN_NAME" ] || die "$TARGET_DIR/$BIN_NAME not found after build."

# 2. Layout.
rm -rf "$APP"
mkdir -p "$MACOS_DIR" "$APP/Contents/Resources"
cp "$SCRIPT_DIR/Info.plist" "$APP/Contents/Info.plist"
cp "$V1_PKG/whispy.icns" "$APP/Contents/Resources/whispy.icns"
cp "$TARGET_DIR/$BIN_NAME" "$MACOS_DIR/$BIN_NAME"
BIN="$MACOS_DIR/$BIN_NAME"

# 3. Dylibs. `ort` with copy-dylibs drops libonnxruntime*.dylib next to the
#    binary in target/release when it links dynamically; with a static link
#    there is none. Either way, resolve from what the binary actually loads:
#    every non-system dependency goes into the bundle.
is_system() { case "$1" in /System/*|/usr/lib/*) return 0 ;; *) return 1 ;; esac; }

find_dylib() { # name -> path on stdout
    local name="$1" d
    for d in "$TARGET_DIR" "$TARGET_DIR/deps"; do
        [ -f "$d/$name" ] && { echo "$d/$name"; return 0; }
    done
    return 1
}

# Pass 1: copy-dylibs output that sits next to the binary.
for f in "$TARGET_DIR"/libonnxruntime*.dylib; do
    [ -e "$f" ] && cp -L "$f" "$MACOS_DIR/"
done

# Pass 2: follow load commands (transitively) for anything non-system.
bundled=()
queue=("$BIN")
while [ ${#queue[@]} -gt 0 ]; do
    cur="${queue[0]}"; queue=("${queue[@]:1}")
    while read -r dep; do
        is_system "$dep" && continue
        name="$(basename "$dep")"
        # @rpath/@loader_path/@executable_path/absolute: resolve by file name.
        if [ ! -f "$MACOS_DIR/$name" ]; then
            src="$(find_dylib "$name")" || die "$cur needs $dep, not found in $TARGET_DIR."
            cp -L "$src" "$MACOS_DIR/$name"
            queue+=("$MACOS_DIR/$name")
            bundled+=("$name")
        fi
        # Point the load command at the bundle copy.
        install_name_tool -change "$dep" "@executable_path/$name" "$cur"
    done < <(otool -L "$cur" | tail -n +2 | awk '{print $1}')
done
# Dylibs copied in pass 1 also need a bundle-relative id.
for f in "$MACOS_DIR"/*.dylib; do
    [ -e "$f" ] || continue
    install_name_tool -id "@executable_path/$(basename "$f")" "$f"
done

# Strip any LC_RPATH that points into the build tree, and make sure the binary
# can find bundled dylibs through @executable_path.
while read -r rp; do
    case "$rp" in
        */target/*) install_name_tool -delete_rpath "$rp" "$BIN" ;;
    esac
done < <(otool -l "$BIN" | awk '/cmd LC_RPATH/{f=1} f&&/path /{print $2; f=0}')
if ls "$MACOS_DIR"/*.dylib >/dev/null 2>&1 \
    && ! otool -l "$BIN" | grep -A2 LC_RPATH | grep -q '@executable_path'; then
    install_name_tool -add_rpath "@executable_path" "$BIN"
fi
echo "  bundled dylibs: ${bundled[*]:-$(cd "$MACOS_DIR" && ls *.dylib 2>/dev/null | tr '\n' ' ')}"
[ -z "$(cd "$MACOS_DIR" && ls *.dylib 2>/dev/null)" ] && echo "  (none: the binary links only system libraries)"

# Nothing may point back into the build tree.
leaks="$( { for f in "$MACOS_DIR"/*; do otool -L "$f" | tail -n +2; otool -l "$f" | grep -A2 LC_RPATH; done; } | grep '/target/' || true)"
[ -z "$leaks" ] || die "load commands still reference the build tree:
$leaks"

# 4. Sign exactly like V1 (stable identity so TCC grants persist).
CERT_NAME="Whispy Local Signing"
"$V1_PKG/create_signing_cert.sh" || true
if security find-identity -p codesigning 2>/dev/null | grep -q "$CERT_NAME"; then
    SIGN_ID="$CERT_NAME"
    echo -e "${YELLOW}Code-signing with '$CERT_NAME' (stable identity, TCC persists)...${NC}"
else
    SIGN_ID="-"
    echo -e "${RED}No '$CERT_NAME' identity — falling back to ad-hoc (TCC will NOT persist).${NC}"
fi
codesign --force --deep --options runtime \
    --entitlements "$SCRIPT_DIR/whispy2.entitlements" \
    --sign "$SIGN_ID" "$APP"

# 5. Verify.
echo -e "${YELLOW}Verifying signature...${NC}"
codesign --verify --strict --verbose=2 "$APP"
codesign -dv --verbose=4 "$APP" 2>&1 | grep -E "Identifier|Signature|flags" || true

echo -e "${GREEN}[OK] Built and signed: $APP${NC}"
