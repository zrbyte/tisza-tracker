# Secrets directory

This folder is copied to `~/.tisza_tracker/secrets` on first run.

Place sensitive configuration files here (e.g. an API key file for the LLM
classifier when you prefer not to use an environment variable).

Files placed here are not tracked by git when copied to your home directory. Be
sure to tighten file permissions manually if needed.
