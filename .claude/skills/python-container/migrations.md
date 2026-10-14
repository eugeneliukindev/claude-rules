# Migrations

### The migration runs once per deploy as a one-shot container of the release's image and tag

**Why:** the image that serves the release is the one that holds its revisions, so the step runs
`docker run --rm IMAGE:TAG` with the migration command, or a Kubernetes `Job` from the same image
and tag, before the rollout; an init container runs once per pod, not once per deploy, and a
migration in the start command runs in every replica and turns a failing revision into a crash
loop.
