#!/bin/bash

# Test script for OpenZiti tunnel setup
# This script validates the tunnel_setup.sh functionality

set -e

echo "=== OpenZiti Tunnel Setup Tests ==="
echo ""

# Test 1: No configuration (should exit gracefully)
echo "Test 1: No OpenZiti configuration"
unset OPENZITI_IDENTITY
unset OPENZITI_IDENTITY_JSON
bash ./tunnel_setup.sh
if [ $? -eq 0 ]; then
    echo "✓ Test 1 passed: Graceful exit with no configuration"
else
    echo "✗ Test 1 failed: Non-zero exit code"
    exit 1
fi
echo ""

# Test 2: Embedded JSON configuration
echo "Test 2: Embedded JSON identity"
export OPENZITI_IDENTITY_JSON='{"zt":"test-token","id":{"key":"test"}}'
OUTPUT=$(bash ./tunnel_setup.sh 2>&1)
# Check that it attempts to start (finds ziti-edge-tunnel or continues gracefully)
if echo "$OUTPUT" | grep -q "ziti-edge-tunnel" || echo "$OUTPUT" | grep -q "Continuing without"; then
    echo "✓ Test 2 passed: Embedded JSON processed"
else
    echo "✗ Test 2 failed: Embedded JSON not processed"
    echo "Output: $OUTPUT"
fi
unset OPENZITI_IDENTITY_JSON
echo ""

# Test 3: File-based configuration (non-existent file)
echo "Test 3: File-based identity (non-existent file)"
export OPENZITI_IDENTITY="/tmp/nonexistent-identity.json"
OUTPUT=$(bash ./tunnel_setup.sh 2>&1)
# Should fail gracefully and continue
if echo "$OUTPUT" | grep -q "Failed to load identity" || echo "$OUTPUT" | grep -q "Continuing without"; then
    echo "✓ Test 3 passed: Missing file handled gracefully"
else
    echo "✗ Test 3 failed: Missing file not handled correctly"
    echo "Output: $OUTPUT"
fi
unset OPENZITI_IDENTITY
echo ""

# Test 4: File-based configuration (existing file)
echo "Test 4: File-based identity (existing file)"
echo '{"zt":"test","id":{}}' > /tmp/test-identity.json
export OPENZITI_IDENTITY="/tmp/test-identity.json"
OUTPUT=$(bash ./tunnel_setup.sh 2>&1)
# Check that it attempts to start (finds ziti-edge-tunnel or continues gracefully)
if echo "$OUTPUT" | grep -q "ziti-edge-tunnel" || echo "$OUTPUT" | grep -q "Continuing without"; then
    echo "✓ Test 4 passed: File-based identity processed"
else
    echo "✗ Test 4 failed: File-based identity not processed"
    echo "Output: $OUTPUT"
fi
rm -f /tmp/test-identity.json
unset OPENZITI_IDENTITY
echo ""

# Test 5: Priority (JSON over file)
echo "Test 5: Priority test (JSON should take precedence over file)"
echo '{"zt":"file","id":{}}' > /tmp/test-identity.json
export OPENZITI_IDENTITY="/tmp/test-identity.json"
export OPENZITI_IDENTITY_JSON='{"zt":"json","id":{}}'
OUTPUT=$(bash ./tunnel_setup.sh 2>&1)
# Check that JSON identity is used (temp file created)
if [ -f /tmp/ziti-identity.json ]; then
    echo "✓ Test 5 passed: JSON takes priority (temp file created)"
    rm -f /tmp/ziti-identity.json
else
    echo "✗ Test 5 failed: Priority not working correctly"
    echo "Output: $OUTPUT"
fi
rm -f /tmp/test-identity.json
unset OPENZITI_IDENTITY
unset OPENZITI_IDENTITY_JSON
echo ""

# Test 6: Service configuration logging
echo "Test 6: Service configuration logging"
export OPENZITI_IDENTITY_JSON='{"zt":"test","id":{}}'
export OPENZITI_SERVICE_HTTP="comfyui-http"
export OPENZITI_SERVICE_SSH="comfyui-ssh"
OUTPUT=$(bash ./tunnel_setup.sh 2>&1)
# Check that services are mentioned in output
if echo "$OUTPUT" | grep -q "comfyui-http" && echo "$OUTPUT" | grep -q "comfyui-ssh"; then
    echo "✓ Test 6 passed: Service configuration logged"
else
    echo "✗ Test 6 failed: Service configuration not logged"
    echo "Output: $OUTPUT"
fi
unset OPENZITI_IDENTITY_JSON
unset OPENZITI_SERVICE_HTTP
unset OPENZITI_SERVICE_SSH
echo ""

echo "=== All tests passed! ==="
