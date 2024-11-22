#!/bin/bash

# Activate the virtual environment
source ~/hackenv/bin/activate

# Navigate to the project directory
cd hackthecityfa24 || { echo "Directory not found!"; exit 1; }

# Run the server using authbind
authbind python server.py
