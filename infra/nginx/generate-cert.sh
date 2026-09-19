#!/bin/bash

set -e

sudo mkdir -p /etc/nginx/ssl

sudo openssl req \
  -x509 \
  -nodes \
  -days 365 \
  -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/lab.key \
  -out /etc/nginx/ssl/lab.crt \
  -subj "/CN=app.lab.test" \
  -addext "subjectAltName=DNS:app.lab.test,IP:192.168.52.136,IP:192.168.52.137"

echo "Certificate created:"
echo "/etc/nginx/ssl/lab.crt"
echo "/etc/nginx/ssl/lab.key"
