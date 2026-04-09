#!/bin/bash
set -a
source /root/.openclaw/.env
set +a
export PYTHONUNBUFFERED=1
cd /root/str-stack/prompts
python3 str_pipeline.py "$@" 2>&1
