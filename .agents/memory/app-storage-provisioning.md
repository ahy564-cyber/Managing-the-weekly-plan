---
name: App Storage provisioning
description: Distinguishing an installed Object Storage SDK from a provisioned default bucket
---

Initializing the Replit Object Storage Python client does not prove that the project has a default bucket. An empty bucket ID from the development runtime's default-bucket check means the bucket is not provisioned, even if the package is installed and the application starts.

**Why:** The SDK client initializes lazily, so client construction gave a false impression of readiness while the runtime reported no bucket. The available agent tools did not expose a documented bucket-creation operation in this workspace.

**How to apply:** Verify bucket provisioning separately from package installation. If no supported provisioner is available, state clearly that setup remains incomplete and direct the user to create a bucket in the App Storage tool; do not claim the SDK installed a bucket.