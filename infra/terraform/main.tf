# Infra-as-code skeleton (roadmap step 278) for ONE reference cloud
# target -- DigitalOcean, chosen over AWS/GCP for the same reason this
# project's own docs/self-hosted-deployment.md already picked a plain
# Docker Compose reference deployment over Kubernetes: it matches this
# project's ACTUAL architecture (one host running docker-compose.prod.yml),
# not an aspirational one. A managed-Kubernetes/multi-AZ design would be
# real over-engineering for a stack that is, today, a single Compose file.
#
# Never `terraform apply`'d against a real account -- this project has
# no real cloud credentials anywhere (confirmed repeatedly throughout
# this whole milestone). `terraform validate` IS real, honest
# verification available without one, and was actually run against
# this configuration while writing it.
#
# Provisions the HOST, not the application secrets -- .env.prod (real
# secrets) is deliberately NOT generated or embedded here. Terraform
# state is not a secrets store, and baking real secrets into
# cloud-init user_data would put them in the provider's own API logs
# and this state file in plaintext. The droplet's own first-boot
# script installs Docker and clones the repo; a human still runs
# docs/self-hosted-deployment.md's own real steps (scp .env.prod,
# `docker compose up`) once, the same as any bare-metal host.

resource "digitalocean_droplet" "agentforge" {
  name     = "agentforge-${var.environment_name}"
  region   = var.region
  size     = var.droplet_size
  image    = "ubuntu-24-04-x64"
  ssh_keys = [var.ssh_key_fingerprint]

  user_data = file("${path.module}/cloud-init.yaml")

  tags = ["agentforge", var.environment_name]
}

resource "digitalocean_firewall" "agentforge" {
  name        = "agentforge-${var.environment_name}"
  droplet_ids = [digitalocean_droplet.agentforge.id]

  # SSH -- real deployment/maintenance access.
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # HTTP/HTTPS only -- the real reverse proxy (Caddy/nginx/Traefik,
  # docs/self-hosted-deployment.md's own TLS section) terminates here.
  # Deliberately NOT opening 8000/3000/5432/6379/9000/9001/3310 --
  # every one of those stays internal to the droplet's own Docker
  # network, matching self-hosted-deployment.md's own existing "only
  # expose 80/443" guidance.
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }
  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
