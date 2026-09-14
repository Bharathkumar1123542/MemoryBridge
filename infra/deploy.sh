#!/usr/bin/env bash
# infra/deploy.sh
# ─────────────────────────────────────────────────────────────────────────────
# MemoryBridge — one-shot deploy to AWS Fargate (architecture.md §14)
#
# What this script does:
#   1. Creates two ECR repos (if they don't exist).
#   2. Builds and pushes both Docker images with the git-sha tag.
#   3. Registers new ECS task definition revisions.
#   4. Updates both ECS services to deploy the new revisions.
#   5. Waits for the services to stabilise and prints the ALB URL.
#
# Prerequisites (run once, before first deploy):
#   - AWS CLI v2 configured with a profile that has the permissions in
#     infra/iam-policy-deployer.json.
#   - ECS cluster "memorybridge" already exists (create with AWS Console or
#     `aws ecs create-cluster --cluster-name memorybridge`).
#   - Two ECS services already exist: "memorybridge-agent-backend" and
#     "memorybridge-web" (create once from the console or via separate IaC).
#   - The two Secrets Manager secrets referenced in the task defs exist.
#   - CloudWatch log groups /ecs/memorybridge-* exist (auto-created by ECS if
#     you enable the "Auto-configure CloudWatch Logs" option).
#
# Usage:
#   export AWS_PROFILE=memorybridge-deploy   # or set via --profile below
#   bash infra/deploy.sh
#   bash infra/deploy.sh --dry-run           # print commands, don't execute
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
CLUSTER="memorybridge"
GIT_SHA="$(git rev-parse --short HEAD)"

BACKEND_REPO="memorybridge-agent-backend"
WEB_REPO="memorybridge-web"

BACKEND_IMAGE="${ECR_BASE}/${BACKEND_REPO}:${GIT_SHA}"
BACKEND_IMAGE_LATEST="${ECR_BASE}/${BACKEND_REPO}:latest"
WEB_IMAGE="${ECR_BASE}/${WEB_REPO}:${GIT_SHA}"
WEB_IMAGE_LATEST="${ECR_BASE}/${WEB_REPO}:latest"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "[dry-run] Commands will be printed but not executed."
fi

run() {
  if $DRY_RUN; then echo "[dry-run] $*"; else "$@"; fi
}

# ── 1. Authenticate to ECR ────────────────────────────────────────────────────
echo "==> Authenticating with ECR in ${AWS_REGION}..."
run aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_BASE}"

# ── 2. Ensure ECR repos exist ─────────────────────────────────────────────────
for REPO in "${BACKEND_REPO}" "${WEB_REPO}"; do
  echo "==> Ensuring ECR repo: ${REPO}"
  run aws ecr describe-repositories --region "${AWS_REGION}" \
    --repository-names "${REPO}" --output text > /dev/null 2>&1 \
  || run aws ecr create-repository --region "${AWS_REGION}" \
       --repository-name "${REPO}" \
       --image-scanning-configuration scanOnPush=true \
       --output text > /dev/null
done

# ── 3. Build images (from repo root, context = .) ─────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

echo "==> Building agent-backend (git sha: ${GIT_SHA})..."
run docker build \
  --file agent-backend/Dockerfile \
  --tag "${BACKEND_IMAGE}" \
  --tag "${BACKEND_IMAGE_LATEST}" \
  .

echo "==> Building web (git sha: ${GIT_SHA})..."
run docker build \
  --file web/Dockerfile \
  --build-arg NEXT_PUBLIC_APP_NAME=MemoryBridge \
  --tag "${WEB_IMAGE}" \
  --tag "${WEB_IMAGE_LATEST}" \
  .

# ── 4. Push to ECR ────────────────────────────────────────────────────────────
echo "==> Pushing agent-backend..."
run docker push "${BACKEND_IMAGE}"
run docker push "${BACKEND_IMAGE_LATEST}"

echo "==> Pushing web..."
run docker push "${WEB_IMAGE}"
run docker push "${WEB_IMAGE_LATEST}"

# ── 5. Register new ECS task definition revisions ─────────────────────────────
echo "==> Registering agent-backend task definition..."
BACKEND_TASK_DEF="$(
  sed "s|ACCOUNT_ID|${AWS_ACCOUNT_ID}|g; s|REGION|${AWS_REGION}|g" \
    infra/ecs-task-def-agent-backend.json \
  | sed "s|:latest|:${GIT_SHA}|g"
)"
BACKEND_TASK_ARN="$(
  run aws ecs register-task-definition \
    --region "${AWS_REGION}" \
    --cli-input-json "${BACKEND_TASK_DEF}" \
    --query "taskDefinition.taskDefinitionArn" \
    --output text
)"
echo "    Registered: ${BACKEND_TASK_ARN}"

echo "==> Registering web task definition..."
WEB_TASK_DEF="$(
  sed "s|ACCOUNT_ID|${AWS_ACCOUNT_ID}|g; s|REGION|${AWS_REGION}|g" \
    infra/ecs-task-def-web.json \
  | sed "s|:latest|:${GIT_SHA}|g"
)"
WEB_TASK_ARN="$(
  run aws ecs register-task-definition \
    --region "${AWS_REGION}" \
    --cli-input-json "${WEB_TASK_DEF}" \
    --query "taskDefinition.taskDefinitionArn" \
    --output text
)"
echo "    Registered: ${WEB_TASK_ARN}"

# ── 6. Update ECS services ────────────────────────────────────────────────────
echo "==> Updating ECS service: memorybridge-agent-backend..."
run aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER}" \
  --service "memorybridge-agent-backend" \
  --task-definition "${BACKEND_TASK_ARN}" \
  --force-new-deployment \
  --output text > /dev/null

echo "==> Updating ECS service: memorybridge-web..."
run aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${CLUSTER}" \
  --service "memorybridge-web" \
  --task-definition "${WEB_TASK_ARN}" \
  --force-new-deployment \
  --output text > /dev/null

# ── 7. Wait for deployment to stabilise ──────────────────────────────────────
if ! $DRY_RUN; then
  echo "==> Waiting for agent-backend service to stabilise (timeout 5 min)..."
  aws ecs wait services-stable \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER}" \
    --services "memorybridge-agent-backend"

  echo "==> Waiting for web service to stabilise (timeout 5 min)..."
  aws ecs wait services-stable \
    --region "${AWS_REGION}" \
    --cluster "${CLUSTER}" \
    --services "memorybridge-web"
fi

echo ""
echo "✅  Deploy complete — git sha ${GIT_SHA}"
echo ""
echo "    App URL: check your ALB DNS name in the AWS Console → EC2 → Load Balancers"
echo "    Or:  aws elbv2 describe-load-balancers --query 'LoadBalancers[?contains(LoadBalancerName,\`memorybridge\`)].DNSName' --output text"
