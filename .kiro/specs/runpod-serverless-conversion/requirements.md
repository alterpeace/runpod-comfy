# Requirements Document

## Introduction

This feature involves creating a unified ComfyUI deployment system that supports three deployment modes: local development, RunPod Serverless (pay-per-execution), and RunPod Pods (persistent servers). The solution will use a single Docker image that adapts to each environment, package the application using GitHub Container Registry (ghcr.io), and include comprehensive documentation for managing each deployment type. The solution will be organized in a dedicated `runpod-serverless` folder and include all necessary configuration files, build scripts, lifecycle management tools, and documentation.

## Requirements

### Requirement 1: RunPod Serverless Handler Implementation

**User Story:** As a developer, I want to create a RunPod serverless handler that can receive workflow requests and execute them in ComfyUI, so that I can process AI image generation tasks on-demand without maintaining a persistent server.

#### Acceptance Criteria

1. WHEN a serverless job is received THEN the handler SHALL parse the input payload containing ComfyUI workflow JSON
2. WHEN the handler processes a workflow THEN it SHALL execute the workflow using ComfyUI's API
3. WHEN a workflow completes successfully THEN the handler SHALL return the generated output files and metadata
4. WHEN a workflow fails THEN the handler SHALL return appropriate error messages and status codes
5. IF the handler receives invalid input THEN it SHALL validate the payload and return descriptive error messages
6. WHEN the handler starts THEN it SHALL initialize ComfyUI and load required models before accepting requests

### Requirement 2: Docker Image Configuration for RunPod

**User Story:** As a DevOps engineer, I want to build a Docker image optimized for RunPod Serverless that includes ComfyUI and all dependencies, so that the serverless function can execute efficiently in the RunPod environment.

#### Acceptance Criteria

1. WHEN building the Docker image THEN it SHALL use the existing ghcr.io/radiatingreverberations/comfyui-base:latest as the base image
2. WHEN the container starts THEN it SHALL install dependencies from extra-requirements.txt if present
3. WHEN the container initializes THEN it SHALL execute add-dependancies.sh if present
4. WHEN building the image THEN it SHALL include the RunPod Python SDK and handler code
5. WHEN the image is built THEN it SHALL be tagged for GitHub Container Registry (ghcr.io)
6. WHEN the container runs THEN it SHALL support GPU acceleration using NVIDIA drivers
7. WHEN models are needed THEN the container SHALL mount or download models to the appropriate directory structure

### Requirement 3: GitHub Container Registry Integration

**User Story:** As a developer, I want to use GitHub Container Registry (ghcr.io) instead of Docker Hub for storing my container images, so that I can avoid Docker Hub's pricing and leverage GitHub's free container registry.

#### Acceptance Criteria

1. WHEN building images THEN the build script SHALL tag images with ghcr.io/[username]/[image-name]:[tag] format
2. WHEN pushing images THEN the script SHALL authenticate with GitHub Container Registry using a GitHub token
3. WHEN configuring RunPod THEN the deployment SHALL reference the ghcr.io image URL
4. IF the repository is private THEN the configuration SHALL include instructions for providing registry credentials to RunPod
5. WHEN building images THEN the script SHALL support multi-platform builds if needed

### Requirement 4: Project Structure and Organization

**User Story:** As a developer, I want all RunPod serverless files organized in a dedicated folder with clear structure, so that I can easily maintain and understand the serverless deployment configuration.

#### Acceptance Criteria

1. WHEN creating the project THEN all RunPod serverless files SHALL be placed in a `runpod-serverless` directory
2. WHEN organizing files THEN the directory SHALL contain a Dockerfile specific to RunPod serverless
3. WHEN organizing files THEN the directory SHALL contain a handler.py file with the serverless logic
4. WHEN organizing files THEN the directory SHALL contain build and deployment scripts
5. WHEN organizing files THEN the directory SHALL contain a README.md with setup and usage instructions
6. WHEN organizing files THEN the directory SHALL contain a runpod-config.json or similar configuration file

### Requirement 5: Volume and Model Management

**User Story:** As a developer, I want to configure how models and persistent data are handled in the serverless environment, so that my ComfyUI workflows can access necessary models and save outputs appropriately.

#### Acceptance Criteria

1. WHEN the handler starts THEN it SHALL support loading models from RunPod network volumes
2. WHEN workflows generate outputs THEN the handler SHALL support three storage options: network volume storage, cloud storage upload, or return in response
3. WHEN STORAGE_TYPE is set to "volume" THEN outputs SHALL be saved to the configured network volume path
4. WHEN STORAGE_TYPE is set to "s3" THEN outputs SHALL be uploaded to S3-compatible storage and URLs returned
5. WHEN STORAGE_TYPE is not configured THEN outputs SHALL be base64 encoded and returned in the API response
6. WHEN custom nodes are needed THEN the configuration SHALL support including custom_nodes in the image or volume
7. IF models are large THEN the documentation SHALL provide guidance on using RunPod network volumes
8. WHEN the handler processes a job THEN it SHALL clean up temporary files after completion

### Requirement 6: Build and Deployment Automation

**User Story:** As a developer, I want automated scripts for building and deploying the RunPod serverless function, so that I can easily update and redeploy my serverless application.

#### Acceptance Criteria

1. WHEN running the build script THEN it SHALL build the Docker image with appropriate tags
2. WHEN running the build script THEN it SHALL push the image to GitHub Container Registry
3. WHEN deploying THEN the script SHALL provide the necessary RunPod configuration or API commands
4. WHEN building THEN the script SHALL validate that required files and dependencies are present
5. IF authentication fails THEN the script SHALL provide clear error messages about token requirements

### Requirement 7: Configuration and Environment Variables

**User Story:** As a developer, I want to configure the serverless function using environment variables and configuration files, so that I can customize behavior without modifying code.

#### Acceptance Criteria

1. WHEN configuring the handler THEN it SHALL support environment variables for ComfyUI arguments (e.g., --lowvram, --use-sage-attention)
2. WHEN configuring deployment THEN it SHALL support specifying GPU type and count requirements
3. WHEN configuring the handler THEN it SHALL support custom timeout values
4. WHEN configuring storage THEN it SHALL support environment variables for network volume storage, S3, or cloud storage credentials
5. WHEN configuring storage THEN it SHALL support STORAGE_TYPE variable to choose between volume, s3, or response output methods
6. IF configuration is missing THEN the handler SHALL use sensible defaults

### Requirement 8: Multi-Mode Operation (Local, Serverless, and Pods)

**User Story:** As a developer, I want to run the same ComfyUI setup in three different modes - locally for development, on RunPod Serverless for pay-per-execution workloads, and on RunPod Pods for persistent servers - so that I can choose the most cost-effective deployment for my use case.

#### Acceptance Criteria

1. WHEN running locally THEN the system SHALL support Docker Compose deployment with the same configuration
2. WHEN running locally THEN the system SHALL use local volume mounts for models and outputs
3. WHEN running on RunPod Serverless THEN the system SHALL use the serverless handler for job processing
4. WHEN running on RunPod Pods THEN the system SHALL run as a persistent server with continuous WebUI access
5. WHEN switching between modes THEN the configuration SHALL use environment variables to determine the mode
6. WHEN running in any mode THEN the ComfyUI WebUI SHALL be accessible and browsable on a configurable port
7. WHEN running in serverless mode THEN the ComfyUI WebUI SHALL remain accessible while the handler processes jobs
8. WHEN running in local or pods mode THEN the ComfyUI WebUI SHALL be the primary interface for workflow development
9. WHEN running in any mode THEN the system SHALL use the same base Docker image
10. WHEN running in any mode THEN the system SHALL start ComfyUI server with --listen 0.0.0.0 to allow external access
11. WHEN running in pods mode THEN the system SHALL NOT start the serverless handler
12. WHEN running in pods mode THEN the system SHALL keep the container running indefinitely

### Requirement 9: OpenZiti Tunnel Integration

**User Story:** As a developer, I want to use OpenZiti to tunnel HTTP and SSH servers back to my local network when a configuration file is present, so that I can securely access RunPod instances without exposing public endpoints.

#### Acceptance Criteria

1. WHEN a `.env` file with OpenZiti configuration exists in network storage THEN the system SHALL initialize an OpenZiti tunnel
2. WHEN the OpenZiti tunnel is active THEN it SHALL forward the ComfyUI HTTP server to the configured network
3. WHEN the OpenZiti tunnel is active THEN it SHALL forward the SSH server to the configured network
4. IF no `.env` file with OpenZiti configuration exists THEN the system SHALL skip tunnel initialization
5. WHEN the tunnel fails to initialize THEN the system SHALL log the error and continue without tunneling
6. WHEN running locally THEN the system SHALL support OpenZiti tunnel for local development access

### Requirement 10: SSH Server for Development and Debugging

**User Story:** As a developer, I want SSH access to RunPod instances for debugging, installing packages, and managing network storage, so that I can troubleshoot issues and customize the environment.

#### Acceptance Criteria

1. WHEN SSH access is enabled THEN the system SHALL start an SSH server in the container
2. WHEN SSH is configured THEN it SHALL support public key authentication
3. WHEN SSH is enabled THEN it SHALL provide access to the network storage folder
4. WHEN SSH is enabled THEN it SHALL allow installation of Python packages to the network storage
5. IF OpenZiti tunnel is configured THEN SSH SHALL be accessible via the tunnel
6. IF OpenZiti tunnel is not configured THEN SSH SHALL be accessible via RunPod's SSH endpoint
7. WHEN SSH is not needed THEN it SHALL be possible to disable it via environment variable

### Requirement 11: RunPod Lifecycle Management

**User Story:** As a developer, I want clear instructions and scripts for managing RunPod Serverless endpoints and Pods (start, stop, terminate), so that I can control my deployments and minimize costs effectively.

#### Acceptance Criteria

1. WHEN managing serverless endpoints THEN the documentation SHALL explain how to create, start, and stop endpoints via RunPod UI and API
2. WHEN managing pods THEN the documentation SHALL explain how to create, start, stop, and terminate pods via RunPod UI and API
3. WHEN stopping a pod THEN the documentation SHALL clearly warn that billing continues and termination is required to stop charges
4. WHEN creating pods THEN the documentation SHALL explain spot vs on-demand pricing and interruption risks
5. WHEN terminating pods THEN the documentation SHALL explain that network storage persists and can be reattached
6. WHEN creating helper scripts THEN they SHALL support pod lifecycle operations (create, start, stop, terminate, status)
7. WHEN creating helper scripts THEN they SHALL support serverless endpoint operations (create, update, delete, invoke)
8. WHEN using the API THEN the scripts SHALL handle authentication with RunPod API keys
9. WHEN checking status THEN the scripts SHALL display current state, costs, and resource usage
10. IF a pod is stopped THEN the documentation SHALL provide instructions to resume it without data loss

### Requirement 12: Documentation and Examples

**User Story:** As a developer, I want comprehensive documentation and example workflows, so that I can understand how to use all three deployment modes and manage their lifecycles effectively.

#### Acceptance Criteria

1. WHEN reading documentation THEN it SHALL explain the differences between Local, RunPod Serverless, and RunPod Pods deployments
2. WHEN reading documentation THEN it SHALL provide a decision matrix for choosing between deployment modes based on use case and cost
3. WHEN reading documentation THEN it SHALL provide step-by-step instructions for building and deploying to each mode
4. WHEN reading documentation THEN it SHALL include example API calls for triggering serverless jobs
5. WHEN reading documentation THEN it SHALL explain how to configure GitHub Container Registry authentication
6. WHEN reading documentation THEN it SHALL provide example ComfyUI workflow JSON payloads
7. WHEN reading documentation THEN it SHALL explain cost considerations and optimization tips for each RunPod mode
8. WHEN reading documentation THEN it SHALL explain OpenZiti tunnel setup and configuration for all modes
9. WHEN reading documentation THEN it SHALL explain SSH server setup for development and debugging in all modes
10. WHEN reading documentation THEN it SHALL provide complete pod lifecycle management instructions (create, start, stop, terminate)
11. WHEN reading documentation THEN it SHALL provide complete serverless endpoint management instructions (create, invoke, delete)
12. WHEN reading documentation THEN it SHALL explain how to use network storage across pod lifecycles
13. WHEN reading documentation THEN it SHALL provide cost comparison examples for different usage patterns
