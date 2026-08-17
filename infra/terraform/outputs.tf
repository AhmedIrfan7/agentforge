output "droplet_ip" {
  description = "Real public IPv4 address of the provisioned host. Point your DNS A record and .env.prod's PUBLIC_API_URL/APP_BASE_URL at this."
  value       = digitalocean_droplet.agentforge.ipv4_address
}

output "droplet_id" {
  value = digitalocean_droplet.agentforge.id
}
