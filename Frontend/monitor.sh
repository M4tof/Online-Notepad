#!/bin/bash

FILE="file.txt"

if [ ! -f "$FILE" ]; then
	echo "Error: $FILE does not exist."
	exit 1
fi

while true; do
	clear
	echo "Contents of $FILE:"
	echo "------------------------"
	cat "$FILE"
	echo ""
	echo  "------------------------"
	sleep 5
done
