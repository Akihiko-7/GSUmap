#!/usr/bin/env bash
# Serve over https on the local network so phones allow GPS, camera and install.
# The certificate is self-signed: on the phone tap "Advanced" then "Proceed" once.
set -e
cd "$(dirname "$0")"
IP=$(hostname -I | awk '{print $1}')
mkdir -p certs
if [ ! -f certs/cert.pem ] || ! openssl x509 -in certs/cert.pem -noout -text | grep -q "IP Address:$IP"; then
  openssl req -x509 -newkey rsa:2048 -nodes -keyout certs/key.pem -out certs/cert.pem -days 30 \
    -subj "/CN=gsu-compass" -addext "subjectAltName=IP:$IP,DNS:localhost" 2>/dev/null
fi
echo "Open on your phone:  https://$IP:8443   (demo: https://$IP:8443/demo)"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
