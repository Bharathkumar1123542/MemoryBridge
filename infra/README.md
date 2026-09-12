# infra/README.md
# MemoryBridge — Infrastructure

This directory contains the ECS Fargate task definitions and the one-shot deploy script.

## Files

| File | Purpose |
|---|---|
| `deploy.sh` | Build, push, register, and deploy both services to ECS Fargate |
| `ecs-task-def-agent-backend.json` | Fargate task definition for the FastAPI + MCP service |
| `ecs-task-def-web.json` | Fargate task definition for the Next.js BFF |
| `iam-policy-deployer.json` | Least-privilege IAM policy for the CI/CD deployer principal |

## One-time bootstrap (before first deploy)

### 1. Create the ECS cluster
```bash
aws ecs create-cluster --cluster-name memorybridge --region us-east-1
```

### 2. Create Secrets Manager secrets
```bash
aws secretsmanager create-secret --name memorybridge/database-url \
  --secret-string "postgresql://user:pass@host/db?sslmode=require"

aws secretsmanager create-secret --name memorybridge/session-secret \
  --secret-string "$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# Only needed if you want web to resolve agent-backend by ALB DNS
aws secretsmanager create-secret --name memorybridge/internal-api-base-url \
  --secret-string "http://<internal-alb-dns-name>"
```

### 3. Create IAM roles

**Execution role** (used by ECS to pull images and fetch secrets):
```bash
aws iam create-role --role-name memorybridge-ecs-execution-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name memorybridge-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Allow fetching the two Secrets Manager secrets
aws iam put-role-policy --role-name memorybridge-ecs-execution-role \
  --policy-name AllowSecretsAccess \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"secretsmanager:GetSecretValue","Resource":"arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:memorybridge/*"}]}'
```

**Agent-backend task role** (used by the running container to call Bedrock):
```bash
aws iam create-role --role-name memorybridge-agent-backend-task-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam put-role-policy --role-name memorybridge-agent-backend-task-role \
  --policy-name BedrockInvokeModel \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],"Resource":"arn:aws:bedrock:us-east-1::foundation-model/*"}]}'
```

**Web task role** (no special permissions needed — web only calls agent-backend internally):
```bash
aws iam create-role --role-name memorybridge-web-task-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

### 4. Create ECS services
Create both services via the AWS Console (Fargate launch type, `memorybridge` cluster, use the task definitions registered by `deploy.sh`).

> **Networking:** `agent-backend` should be in a private subnet with no public IP; `web` should be behind a public ALB on port 80/443, with a target group pointing to port 3000.

### 5. Deploy
```bash
export AWS_PROFILE=memorybridge-deploy
bash infra/deploy.sh
```

## Dry-run (CI test without pushing)
```bash
bash infra/deploy.sh --dry-run
```
