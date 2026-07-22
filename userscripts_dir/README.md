# Userscripts Directory

This directory contains optional scripts that run at container startup.

## How it works

1. Place executable `.sh` scripts in this directory
2. Mount this directory to `/userscripts_dir` in the container
3. Scripts run in alphanumeric order (e.g., `10-first.sh` before `20-second.sh`)
4. Only executable scripts run (`chmod +x script.sh`)

## Example docker-compose mount

```yaml
volumes:
  - ./userscripts_dir:/userscripts_dir
```

## Available example scripts

- `10-example-sageattention.sh` - Example for compiling SageAttention (disabled by default)

## Notes

- Scripts have access to the container's environment variables
- Scripts run BEFORE ComfyUI starts
- Failed scripts log a warning but don't stop the container
- Use `chmod -x script.sh` to disable a script without deleting it
