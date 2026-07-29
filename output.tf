output "valkey_endpoint" {
  value = aws_elasticache_replication_group.valkey.primary_endpoint_address
}