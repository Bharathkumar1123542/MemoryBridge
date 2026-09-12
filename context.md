# System Handover Context: MemoryBridge

**Current Phase:** Step 3B - AWS Fargate Deployment Setup
**System Status:** Local development and containerization (Step 3A) are 100% complete and verified. 

## Architectural Overview
MemoryBridge is a two-tier system:
1. **Next.js Web Frontend (BFF):** Handles authentication (`iron-session`), serves the caregiver console and `/today` view, and proxies requests securely.
2. **FastAPI Agent Backend:** Orchestrates Bedrock models (Strands Agents SDK), enforces the deterministic safety gate, and runs an internal MCP server as a subprocess for database operations. 
*Both services are containerized with optimized, multi-stage Dockerfiles.*

## Completed Work (Do Not Modify)
* **Application Code:** All features are implemented. 65/65 Python tests pass. Next.js builds clean (0 errors, standalone output).
* **Local Infra:** `docker-compose.yml` is fully functional for local testing.
* **AWS IaC Scaffolding:** The `infra/` directory is fully populated with:
  * Task definitions for both Fargate services (`ecs-task-def-*.json`).
  * A deployment script (`deploy.sh`) to build, push to ECR, and update ECS.
  * A least-privilege IAM policy (`iam-policy-deployer.json`).
  * A bootstrap guide (`infra/README.md`).

## Where We Stopped (Your Next Steps)
We stopped at **Step 3B (Deploy to AWS Fargate)** because we lacked configured AWS credentials in the local environment.

**To resume the deployment, follow these exact steps:**
1. **Configure AWS Credentials:** Setup your `~/.aws/credentials` (or AWS SSO) with permissions to provision ECS/ECR resources. Export `AWS_PROFILE` if necessary.
2. **One-Time Bootstrap:** Follow `infra/README.md` to manually create the foundational AWS resources:
   * Create the ECS cluster (`memorybridge`).
   * Create the required Secrets Manager entries (`DATABASE_URL`, `SESSION_SECRET`, `INTERNAL_API_BASE_URL`).
   * Create the IAM roles (Execution Role, Agent Backend Task Role, Web Task Role) and attach the specified policies.
   * Create the two ECS services in the AWS Console (Fargate launch type, attached to an ALB for the web service).
3. **Execute Deployment:** 
   * Run `bash infra/deploy.sh --dry-run` to validate your ECR/ECS setup without pushing images.
   * Run `bash infra/deploy.sh` to perform the actual build, push, and service update.
4. **Validation:** Verify the Fargate deployment is healthy and accessible via the ALB DNS name.

*Note: The application relies on Neon PostgreSQL and AWS Bedrock. Ensure your Secrets Manager entries point to valid instances.*
