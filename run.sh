#!/bin/bash

# Activate the virtual environment
source ~/hackenv/bin/activate

# Navigate to the project directory
cd /home/pi/hackthecityfa24

# Run the server using authbind
authbind python server.py
