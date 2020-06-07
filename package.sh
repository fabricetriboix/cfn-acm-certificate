#!/bin/bash

set -eu -o pipefail

tmp=$(realpath "$0")
dir=$(dirname "$tmp")
cd "$dir"

rm -f acm-certificate.zip
tmpdir=$(mktemp -d ./pkg-XXXXXX)
if [ -e /etc/debian_version ]; then
    extra_pip_args=--system
else
    extra_pip_args=
fi
pip3 install $extra_pip_args --target "$tmpdir" -r requirements.txt
cd "$tmpdir"
zip -r9 ../acm-certificate.zip .
cd ..
rm -rf "$tmpdir"
zip -g acm-certificate.zip acm-certificate.py
