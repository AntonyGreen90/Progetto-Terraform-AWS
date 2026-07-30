output "bucket_id" {
    description = "Id of the created bucket"
    value= module.frontend.bucket_id
}

output "website_endpoint" {
    description = "Endpoint to visit bucket website"
    value= module.frontend.website_endpoint
}

output "valkey_endpoint" {
  value = aws_elasticache_replication_group.valkey.primary_endpoint_address
}

output "cloudfront_domain" {
  description = "Cloudfront domain without DNS"
  value = module.frontend.cloudfront_domain
}