#!/usr/bin/env bash
# Create a free, self-signed code-signing certificate in the login keychain.
#
# Why: an ad-hoc signature ("-") has no stable signing identity, so macOS TCC
# will NOT persist microphone / Accessibility / Input-Monitoring grants across
# relaunches — the app re-prompts (or auto-denies) every launch. A self-signed
# code-signing cert gives codesign a stable identity to anchor the bundle's
# Designated Requirement to, so TCC remembers the grant. It is local-only (not
# trusted by Gatekeeper / not distributable) — perfect for a personal machine.
#
# Idempotent: does nothing if the identity already exists. Free, no Apple account.
set -euo pipefail

CERT_NAME="Whispy Local Signing"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if security find-identity -p codesigning 2>/dev/null | grep -q "$CERT_NAME"; then
    echo "[OK] Code-signing identity already present: $CERT_NAME"
    exit 0
fi

echo "Creating self-signed code-signing certificate: $CERT_NAME"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/cfg" <<EOF
[req]
distinguished_name=dn
x509_extensions=ext
prompt=no
[dn]
CN=$CERT_NAME
[ext]
keyUsage=critical,digitalSignature
extendedKeyUsage=critical,codeSigning
basicConstraints=critical,CA:false
EOF

openssl req -x509 -newkey rsa:2048 -keyout "$TMP/key.pem" -out "$TMP/cert.pem" \
    -days 3650 -nodes -config "$TMP/cfg" >/dev/null 2>&1

# Legacy PKCS12 algorithms (SHA1/3DES): OpenSSL 3's modern defaults fail macOS
# `security import` with "MAC verification failed".
openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" -out "$TMP/id.p12" \
    -passout pass:whispy -legacy -macalg sha1 \
    -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -name "$CERT_NAME" >/dev/null 2>&1

# -A lets codesign use the key without a per-sign keychain prompt.
security import "$TMP/id.p12" -k "$KEYCHAIN" -P "whispy" -T /usr/bin/codesign -A

echo "[OK] Imported $CERT_NAME (untrusted self-signed — fine for local TCC)."
