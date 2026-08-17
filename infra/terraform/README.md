# Terraform: DigitalOcean reference target

Roadmap step 278. Provisions ONE host matching this project's own actual
architecture — a single Droplet running Docker, meant to run
[`docker-compose.prod.yml`](../../docker-compose.prod.yml) exactly as
[`docs/self-hosted-deployment.md`](../../docs/self-hosted-deployment.md)
already documents. Not a Kubernetes/multi-AZ design — that would be real
over-engineering for a stack that is, today, a single Compose file.

**Never `terraform apply`'d against a real account** — this project has no
real DigitalOcean credentials anywhere. `terraform validate` and
`terraform fmt -check` were both actually run against this configuration
(both real, offline, no credentials needed) and both pass clean; that's the
honest limit of what's verifiable without a real account.

## What this provisions

- One Droplet (`digitalocean_droplet.agentforge`), Ubuntu 24.04, Docker
  Engine + the Compose plugin installed via cloud-init on first boot, this
  repo cloned to `/opt/agentforge`.
- One Firewall (`digitalocean_firewall.agentforge`) allowing inbound
  SSH (22) and HTTP/HTTPS (80/443) only — everything else (the API's own
  8000, web's 3000, Postgres/Redis/MinIO/ClamAV) stays internal to the
  Droplet's own Docker network, matching `docs/self-hosted-deployment.md`'s
  own existing "only expose 80/443" guidance.

**Deliberately does NOT provision `.env.prod`** (real application secrets)
— Terraform state and cloud-init `user_data` are not secret stores, and
DigitalOcean's own API can log `user_data` in plaintext. A human still runs
`docs/self-hosted-deployment.md`'s own real remaining steps (`scp .env.prod`
to the host, `docker compose up`) once the Droplet exists — the same as any
bare-metal host.

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars
# fill in ssh_key_fingerprint (an SSH key already uploaded to your
# DigitalOcean account) and any other real values

export TF_VAR_do_token="dop_v1_..."  # never write this to a file

terraform init
terraform plan
terraform apply
```

Then follow `docs/self-hosted-deployment.md` against the real IP
`terraform apply`'s own output prints.
