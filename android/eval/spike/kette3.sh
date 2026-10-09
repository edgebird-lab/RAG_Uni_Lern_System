#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
# SPDX-License-Identifier: GPL-3.0-or-later
set -u
cd "$(dirname "$0")"
./run_embed.sh emb-gpu-768-prefix gpu 768 true 512 16 3012 2400
./run_embed.sh emb-gpu-768-raw gpu 768 false 512 16 3012 2400
./run_embed.sh emb-gpu-256-prefix gpu 256 true 512 16 3012 2400
echo KETTE-FERTIG
