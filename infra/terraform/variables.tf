variable "do_token" {
  description = "DigitalOcean API token. Set via TF_VAR_do_token env var, never committed."
  type        = string
  sensitive   = true
}

variable "ssh_key_fingerprint" {
  description = "Fingerprint of an SSH key already uploaded to your DigitalOcean account (Settings -> Security -> SSH Keys). Required -- there is no password-based fallback here on purpose."
  type        = string
}

variable "region" {
  description = "DigitalOcean region slug (e.g. nyc3, fra1, sgp1)."
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = "DigitalOcean Droplet size slug. s-4vcpu-8gb is a reasonable floor for the full stack (Postgres+pgvector, Redis, MinIO, ClamAV, api, worker, web all on one host) -- see docs/self-hosted-deployment.md's own prerequisites section for why."
  type        = string
  default     = "s-4vcpu-8gb"
}

variable "environment_name" {
  description = "A short name distinguishing this deployment (e.g. \"staging\", \"production\") -- used in resource naming and tags."
  type        = string
}
