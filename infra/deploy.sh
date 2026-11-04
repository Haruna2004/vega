#!/usr/bin/env bash
# Deploy MEND. Needs: gcloud (logged in), wrangler (CLOUDFLARE_API_TOKEN), and the shared
# engine key in $MEND_ENGINE_KEY (also stored as the Worker secret ENGINE_KEY).
set -euo pipefail
PROJECT=${PROJECT:-mend-road-audit-1104}
REGION=${REGION:-europe-west1}
IMAGE=$REGION-docker.pkg.dev/$PROJECT/mend/engine:latest

# 1. engine image (Cloud Build) + Cloud Run service that scales to zero
gcloud builds submit --project "$PROJECT" --config infra/cloudbuild.yaml .
gcloud run deploy mend-engine --project "$PROJECT" --image "$IMAGE" --region "$REGION" \
  --allow-unauthenticated --min-instances 0 --max-instances 1 --no-cpu-throttling \
  --cpu 2 --memory 4Gi --timeout 3600 --concurrency 30 \
  --set-env-vars "MEND_EDGE_URL=https://mend.harunafaruk.com,MEND_ENGINE_KEY=$MEND_ENGINE_KEY,MEND_PROVIDER=${MEND_PROVIDER:-simulate}"

# 2. frontend + edge Worker (Cloudflare free tier)
(cd frontend && npm ci && npm run build)
(cd api && npm ci && npx wrangler deploy)
