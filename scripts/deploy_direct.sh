#!/bin/bash

# Deploy to Google Cloud Run using buildpacks (no Docker)

PROJECT_ID="damonkemo21"
SERVICE_NAME="hello"
REGION="asia-southeast1"

echo "🚀 Deploying to Google Cloud Run without Docker..."

# Set the project
gcloud config set project $PROJECT_ID

# Deploy using buildpacks (direct Python deployment)
gcloud run deploy $SERVICE_NAME \
  --source . \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 600 \
  --max-instances 3 \
  --concurrency 1000 \
  --min-instances 0 \
  --set-env-vars="PYTHONUNBUFFERED=1" \
  --port 8080

echo "✅ Deployment completed!"
echo "🌐 Service URL:"
gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)'