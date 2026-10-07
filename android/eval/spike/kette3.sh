#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
./run_embed.sh emb-gpu-768-prefix gpu 768 true 512 16 3012 2400
./run_embed.sh emb-gpu-768-raw gpu 768 false 512 16 3012 2400
./run_embed.sh emb-gpu-256-prefix gpu 256 true 512 16 3012 2400
echo KETTE-FERTIG
