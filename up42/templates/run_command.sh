#!/bin/bash

# turn on bash's job control
set -m

# Start the primary process and put it in the background
${*:6} &

# Start the helper process
cd /block/ && python3 run.py --port $1 --process_route $2 --healthcheck_route $3 --type $4  --resolution $5

# Kill the process that runs in background when helper process completed
kill -STOP %1