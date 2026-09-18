#!/bin/sh
# Cháº¡y Streamlit (ná»™i bá»™, khÃ´ng expose) + nginx (foreground, expose 8080) â€”
# nginx phÃ­a trÆ°á»›c lo route /health + reverse proxy, xem deploy/nginx-ui.conf.
set -e

streamlit run ui/app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true &

nginx -g "daemon off;"
