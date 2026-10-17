#!/usr/bin/env bash
# Clone the challenge dataset into data/flytbase-dataset
set -euo pipefail
mkdir -p data
[ -d data/flytbase-dataset ] || git clone --depth 1 https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset.git data/flytbase-dataset
